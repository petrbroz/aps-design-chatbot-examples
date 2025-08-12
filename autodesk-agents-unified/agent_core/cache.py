"""
Unified caching system for AgentCore framework.
"""

import os
import json
import hashlib
import pickle
import logging
from typing import Any, Optional, Dict, List, Set, Union
from pathlib import Path
from datetime import datetime, timedelta
import asyncio
import aiofiles
from enum import Enum


class CacheStrategy(Enum):
    """Cache strategy types."""
    MEMORY_ONLY = "memory_only"
    FILE_ONLY = "file_only"
    MEMORY_AND_FILE = "memory_and_file"


class CacheKeyGenerator:
    """Generates cache keys with different strategies."""
    
    @staticmethod
    def generate_agent_key(agent_type: str, identifier: str) -> str:
        """Generate cache key for agent instances."""
        return f"agent:{agent_type}:{identifier}"
    
    @staticmethod
    def generate_index_key(project_id: str, version_id: str) -> str:
        """Generate cache key for model property indexes."""
        return f"index:{project_id}:{version_id}"
    
    @staticmethod
    def generate_properties_key(urn: str, query_hash: str) -> str:
        """Generate cache key for property queries."""
        return f"properties:{urn}:{query_hash}"
    
    @staticmethod
    def generate_database_key(urn: str) -> str:
        """Generate cache key for SQLite databases."""
        return f"database:{urn}"
    
    @staticmethod
    def generate_vector_key(element_group_id: str, query_hash: str) -> str:
        """Generate cache key for vector search results."""
        return f"vector:{element_group_id}:{query_hash}"
    
    @staticmethod
    def generate_custom_key(namespace: str, *components: str) -> str:
        """Generate custom cache key with namespace and components."""
        key_parts = [namespace] + list(components)
        return ":".join(key_parts)
    
    @staticmethod
    def hash_query(query: Union[str, Dict[str, Any]]) -> str:
        """Generate hash for query parameters."""
        if isinstance(query, dict):
            query_str = json.dumps(query, sort_keys=True)
        else:
            query_str = str(query)
        return hashlib.sha256(query_str.encode()).hexdigest()[:16]


class CacheManager:
    """Manages unified caching across all agents."""
    
    def __init__(self, 
                 cache_directory: str = "/tmp/agent_cache",
                 default_ttl: int = 3600,
                 max_memory_entries: int = 1000,
                 cleanup_interval: int = 300):
        self.cache_directory = Path(cache_directory)
        self.cache_directory.mkdir(parents=True, exist_ok=True)
        self.default_ttl = default_ttl
        self.max_memory_entries = max_memory_entries
        self.cleanup_interval = cleanup_interval
        
        self._memory_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_lock = asyncio.Lock()
        self._access_times: Dict[str, datetime] = {}
        self._cleanup_task: Optional[asyncio.Task] = None
        self._logger = logging.getLogger(__name__)
        
        # Start background cleanup task
        self._start_cleanup_task()
    
    def _start_cleanup_task(self):
        """Start the background cleanup task."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
    
    async def _periodic_cleanup(self):
        """Periodically clean up expired cache entries."""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval)
                cleaned = await self.cleanup_expired()
                if cleaned > 0:
                    self._logger.info(f"Cleaned up {cleaned} expired cache entries")
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(f"Error in periodic cleanup: {e}")
    
    def _generate_cache_key(self, namespace: str, key: str) -> str:
        """Generate a cache key with namespace."""
        combined = f"{namespace}:{key}"
        return hashlib.md5(combined.encode()).hexdigest()
    
    def _get_cache_file_path(self, cache_key: str) -> Path:
        """Get the file path for a cache key."""
        # Create subdirectories based on first two characters of hash for better file distribution
        subdir = cache_key[:2]
        cache_subdir = self.cache_directory / subdir
        cache_subdir.mkdir(exist_ok=True)
        return cache_subdir / f"{cache_key}.cache"
    
    def _evict_lru_entries(self):
        """Evict least recently used entries if memory cache is full."""
        if len(self._memory_cache) <= self.max_memory_entries:
            return
        
        # Sort by access time and remove oldest entries
        sorted_keys = sorted(
            self._access_times.items(),
            key=lambda x: x[1]
        )
        
        entries_to_remove = len(self._memory_cache) - self.max_memory_entries + 1
        for cache_key, _ in sorted_keys[:entries_to_remove]:
            if cache_key in self._memory_cache:
                del self._memory_cache[cache_key]
            if cache_key in self._access_times:
                del self._access_times[cache_key]
    
    async def get(self, namespace: str, key: str, default: Any = None, 
                  strategy: CacheStrategy = CacheStrategy.MEMORY_AND_FILE) -> Any:
        """Get value from cache with specified strategy."""
        cache_key = self._generate_cache_key(namespace, key)
        
        async with self._cache_lock:
            # Check memory cache first (if strategy allows)
            if strategy in [CacheStrategy.MEMORY_ONLY, CacheStrategy.MEMORY_AND_FILE]:
                if cache_key in self._memory_cache:
                    cache_entry = self._memory_cache[cache_key]
                    if self._is_cache_valid(cache_entry):
                        # Update access time for LRU
                        self._access_times[cache_key] = datetime.utcnow()
                        self._logger.debug(f"Cache hit (memory): {namespace}:{key}")
                        return cache_entry['value']
                    else:
                        # Remove expired entry
                        del self._memory_cache[cache_key]
                        if cache_key in self._access_times:
                            del self._access_times[cache_key]
            
            # Check file cache (if strategy allows)
            if strategy in [CacheStrategy.FILE_ONLY, CacheStrategy.MEMORY_AND_FILE]:
                cache_file = self._get_cache_file_path(cache_key)
                if cache_file.exists():
                    try:
                        async with aiofiles.open(cache_file, 'rb') as f:
                            content = await f.read()
                            cache_entry = pickle.loads(content)
                            
                            if self._is_cache_valid(cache_entry):
                                # Load into memory cache if strategy allows
                                if strategy == CacheStrategy.MEMORY_AND_FILE:
                                    self._evict_lru_entries()
                                    self._memory_cache[cache_key] = cache_entry
                                    self._access_times[cache_key] = datetime.utcnow()
                                
                                self._logger.debug(f"Cache hit (file): {namespace}:{key}")
                                return cache_entry['value']
                            else:
                                # Remove expired file
                                cache_file.unlink()
                                
                    except Exception as e:
                        self._logger.error(f"Error reading cache file {cache_file}: {e}")
            
            self._logger.debug(f"Cache miss: {namespace}:{key}")
            return default
    
    async def set(self, namespace: str, key: str, value: Any, 
                  ttl_seconds: Optional[int] = None,
                  strategy: CacheStrategy = CacheStrategy.MEMORY_AND_FILE) -> None:
        """Set value in cache with TTL and strategy."""
        cache_key = self._generate_cache_key(namespace, key)
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl
        expires_at = datetime.utcnow() + timedelta(seconds=ttl) if ttl > 0 else None
        
        cache_entry = {
            'value': value,
            'expires_at': expires_at,
            'created_at': datetime.utcnow(),
            'namespace': namespace,
            'key': key,
            'ttl_seconds': ttl
        }
        
        async with self._cache_lock:
            # Store in memory cache (if strategy allows)
            if strategy in [CacheStrategy.MEMORY_ONLY, CacheStrategy.MEMORY_AND_FILE]:
                self._evict_lru_entries()
                self._memory_cache[cache_key] = cache_entry
                self._access_times[cache_key] = datetime.utcnow()
            
            # Store in file cache (if strategy allows)
            if strategy in [CacheStrategy.FILE_ONLY, CacheStrategy.MEMORY_AND_FILE]:
                cache_file = self._get_cache_file_path(cache_key)
                try:
                    async with aiofiles.open(cache_file, 'wb') as f:
                        content = pickle.dumps(cache_entry)
                        await f.write(content)
                except Exception as e:
                    self._logger.error(f"Error writing cache file {cache_file}: {e}")
            
            self._logger.debug(f"Cache set: {namespace}:{key} (TTL: {ttl}s, Strategy: {strategy.value})")
    
    async def delete(self, namespace: str, key: str) -> bool:
        """Delete value from cache."""
        cache_key = self._generate_cache_key(namespace, key)
        
        async with self._cache_lock:
            deleted = False
            
            # Remove from memory cache
            if cache_key in self._memory_cache:
                del self._memory_cache[cache_key]
                deleted = True
            
            # Remove access time tracking
            if cache_key in self._access_times:
                del self._access_times[cache_key]
            
            # Remove from file cache
            cache_file = self._get_cache_file_path(cache_key)
            if cache_file.exists():
                try:
                    cache_file.unlink()
                    deleted = True
                except Exception as e:
                    self._logger.error(f"Error deleting cache file {cache_file}: {e}")
            
            if deleted:
                self._logger.debug(f"Cache deleted: {namespace}:{key}")
            
            return deleted
    
    async def clear_namespace(self, namespace: str) -> int:
        """Clear all cache entries for a namespace."""
        cleared_count = 0
        
        async with self._cache_lock:
            # Clear from memory cache
            keys_to_remove = []
            for cache_key, cache_entry in self._memory_cache.items():
                if cache_entry.get('namespace') == namespace:
                    keys_to_remove.append(cache_key)
            
            for key in keys_to_remove:
                del self._memory_cache[key]
                if key in self._access_times:
                    del self._access_times[key]
                cleared_count += 1
            
            # Clear from file cache - search in all subdirectories
            files_to_remove = []
            for subdir in self.cache_directory.iterdir():
                if subdir.is_dir():
                    for cache_file in subdir.glob("*.cache"):
                        try:
                            async with aiofiles.open(cache_file, 'rb') as f:
                                content = await f.read()
                                cache_entry = pickle.loads(content)
                                
                                if cache_entry.get('namespace') == namespace:
                                    files_to_remove.append(cache_file)
                                    
                        except Exception:
                            continue
            
            # Also check root directory for legacy cache files
            for cache_file in self.cache_directory.glob("*.cache"):
                try:
                    async with aiofiles.open(cache_file, 'rb') as f:
                        content = await f.read()
                        cache_entry = pickle.loads(content)
                        
                        if cache_entry.get('namespace') == namespace:
                            files_to_remove.append(cache_file)
                            
                except Exception:
                    continue
            
            for cache_file in files_to_remove:
                try:
                    cache_file.unlink()
                    cleared_count += 1
                except Exception as e:
                    self._logger.error(f"Error deleting cache file {cache_file}: {e}")
        
        if cleared_count > 0:
            self._logger.info(f"Cleared {cleared_count} cache entries for namespace: {namespace}")
        
        return cleared_count
    
    async def cleanup_expired(self) -> int:
        """Clean up expired cache entries."""
        cleaned_count = 0
        
        async with self._cache_lock:
            # Clean memory cache
            expired_keys = []
            for cache_key, cache_entry in self._memory_cache.items():
                if not self._is_cache_valid(cache_entry):
                    expired_keys.append(cache_key)
            
            for key in expired_keys:
                del self._memory_cache[key]
                if key in self._access_times:
                    del self._access_times[key]
                cleaned_count += 1
            
            # Clean file cache - check all subdirectories
            cache_files_to_check = []
            
            # Check subdirectories
            for subdir in self.cache_directory.iterdir():
                if subdir.is_dir():
                    cache_files_to_check.extend(subdir.glob("*.cache"))
            
            # Check root directory for legacy files
            cache_files_to_check.extend(self.cache_directory.glob("*.cache"))
            
            for cache_file in cache_files_to_check:
                try:
                    async with aiofiles.open(cache_file, 'rb') as f:
                        content = await f.read()
                        cache_entry = pickle.loads(content)
                        
                        if not self._is_cache_valid(cache_entry):
                            cache_file.unlink()
                            cleaned_count += 1
                            
                except Exception:
                    # If we can't read the file, consider it corrupted and remove it
                    try:
                        cache_file.unlink()
                        cleaned_count += 1
                    except Exception as e:
                        self._logger.error(f"Error removing corrupted cache file {cache_file}: {e}")
        
        return cleaned_count
    
    def _is_cache_valid(self, cache_entry: Dict[str, Any]) -> bool:
        """Check if a cache entry is still valid."""
        expires_at = cache_entry.get('expires_at')
        if expires_at is None:
            return True  # No expiration
        
        return datetime.utcnow() < expires_at
    
    async def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate cache entries matching a pattern."""
        invalidated_count = 0
        
        async with self._cache_lock:
            # Invalidate from memory cache
            keys_to_remove = []
            for cache_key, cache_entry in self._memory_cache.items():
                cache_full_key = f"{cache_entry.get('namespace', '')}:{cache_entry.get('key', '')}"
                if self._matches_pattern(cache_full_key, pattern):
                    keys_to_remove.append(cache_key)
            
            for key in keys_to_remove:
                del self._memory_cache[key]
                if key in self._access_times:
                    del self._access_times[key]
                invalidated_count += 1
            
            # Invalidate from file cache
            cache_files_to_check = []
            
            # Check subdirectories
            for subdir in self.cache_directory.iterdir():
                if subdir.is_dir():
                    cache_files_to_check.extend(subdir.glob("*.cache"))
            
            # Check root directory
            cache_files_to_check.extend(self.cache_directory.glob("*.cache"))
            
            files_to_remove = []
            for cache_file in cache_files_to_check:
                try:
                    async with aiofiles.open(cache_file, 'rb') as f:
                        content = await f.read()
                        cache_entry = pickle.loads(content)
                        
                        cache_full_key = f"{cache_entry.get('namespace', '')}:{cache_entry.get('key', '')}"
                        if self._matches_pattern(cache_full_key, pattern):
                            files_to_remove.append(cache_file)
                            
                except Exception:
                    continue
            
            for cache_file in files_to_remove:
                try:
                    cache_file.unlink()
                    invalidated_count += 1
                except Exception as e:
                    self._logger.error(f"Error deleting cache file {cache_file}: {e}")
        
        if invalidated_count > 0:
            self._logger.info(f"Invalidated {invalidated_count} cache entries matching pattern: {pattern}")
        
        return invalidated_count
    
    def _matches_pattern(self, key: str, pattern: str) -> bool:
        """Check if a key matches a pattern (supports wildcards)."""
        import fnmatch
        return fnmatch.fnmatch(key, pattern)
    
    async def get_namespaces(self) -> Set[str]:
        """Get all cache namespaces."""
        namespaces = set()
        
        async with self._cache_lock:
            # Get from memory cache
            for cache_entry in self._memory_cache.values():
                namespace = cache_entry.get('namespace')
                if namespace:
                    namespaces.add(namespace)
            
            # Get from file cache
            cache_files_to_check = []
            
            # Check subdirectories
            for subdir in self.cache_directory.iterdir():
                if subdir.is_dir():
                    cache_files_to_check.extend(subdir.glob("*.cache"))
            
            # Check root directory
            cache_files_to_check.extend(self.cache_directory.glob("*.cache"))
            
            for cache_file in cache_files_to_check:
                try:
                    async with aiofiles.open(cache_file, 'rb') as f:
                        content = await f.read()
                        cache_entry = pickle.loads(content)
                        
                        namespace = cache_entry.get('namespace')
                        if namespace:
                            namespaces.add(namespace)
                            
                except Exception:
                    continue
        
        return namespaces
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics."""
        async with self._cache_lock:
            memory_count = len(self._memory_cache)
            
            # Count file entries in all subdirectories
            file_count = 0
            total_size = 0
            
            # Check subdirectories
            for subdir in self.cache_directory.iterdir():
                if subdir.is_dir():
                    subdir_files = list(subdir.glob("*.cache"))
                    file_count += len(subdir_files)
                    for cache_file in subdir_files:
                        try:
                            total_size += cache_file.stat().st_size
                        except Exception:
                            continue
            
            # Check root directory
            root_files = list(self.cache_directory.glob("*.cache"))
            file_count += len(root_files)
            for cache_file in root_files:
                try:
                    total_size += cache_file.stat().st_size
                except Exception:
                    continue
            
            # Get namespace statistics
            namespace_stats = {}
            for cache_entry in self._memory_cache.values():
                namespace = cache_entry.get('namespace', 'unknown')
                if namespace not in namespace_stats:
                    namespace_stats[namespace] = 0
                namespace_stats[namespace] += 1
            
            return {
                "memory_entries": memory_count,
                "file_entries": file_count,
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "cache_directory": str(self.cache_directory),
                "namespace_stats": namespace_stats,
                "max_memory_entries": self.max_memory_entries,
                "default_ttl": self.default_ttl,
                "cleanup_interval": self.cleanup_interval
            }
    
    async def shutdown(self):
        """Shutdown the cache manager and cleanup resources."""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        self._logger.info("Cache manager shutdown complete")
    
    # Convenience methods for specific agent caching patterns
    
    async def cache_agent_instance(self, agent_type: str, identifier: str, agent_instance: Any, ttl_seconds: int = 7200) -> None:
        """Cache an agent instance."""
        key = CacheKeyGenerator.generate_agent_key(agent_type, identifier)
        await self.set("agents", key, agent_instance, ttl_seconds, CacheStrategy.MEMORY_ONLY)
    
    async def get_agent_instance(self, agent_type: str, identifier: str) -> Any:
        """Get cached agent instance."""
        key = CacheKeyGenerator.generate_agent_key(agent_type, identifier)
        return await self.get("agents", key, strategy=CacheStrategy.MEMORY_ONLY)
    
    async def cache_index(self, project_id: str, version_id: str, index_data: Any, ttl_seconds: int = 86400) -> None:
        """Cache model property index."""
        key = CacheKeyGenerator.generate_index_key(project_id, version_id)
        await self.set("indexes", key, index_data, ttl_seconds)
    
    async def get_index(self, project_id: str, version_id: str) -> Any:
        """Get cached model property index."""
        key = CacheKeyGenerator.generate_index_key(project_id, version_id)
        return await self.get("indexes", key)
    
    async def cache_properties(self, urn: str, query: Union[str, Dict[str, Any]], properties_data: Any, ttl_seconds: int = 3600) -> None:
        """Cache property query results."""
        query_hash = CacheKeyGenerator.hash_query(query)
        key = CacheKeyGenerator.generate_properties_key(urn, query_hash)
        await self.set("properties", key, properties_data, ttl_seconds)
    
    async def get_properties(self, urn: str, query: Union[str, Dict[str, Any]]) -> Any:
        """Get cached property query results."""
        query_hash = CacheKeyGenerator.hash_query(query)
        key = CacheKeyGenerator.generate_properties_key(urn, query_hash)
        return await self.get("properties", key)
    
    async def cache_database(self, urn: str, database_path: str, ttl_seconds: int = 86400) -> None:
        """Cache database file path."""
        key = CacheKeyGenerator.generate_database_key(urn)
        await self.set("databases", key, database_path, ttl_seconds)
    
    async def get_database(self, urn: str) -> Optional[str]:
        """Get cached database file path."""
        key = CacheKeyGenerator.generate_database_key(urn)
        return await self.get("databases", key)
    
    async def cache_vector_results(self, element_group_id: str, query: Union[str, Dict[str, Any]], results: Any, ttl_seconds: int = 1800) -> None:
        """Cache vector search results."""
        query_hash = CacheKeyGenerator.hash_query(query)
        key = CacheKeyGenerator.generate_vector_key(element_group_id, query_hash)
        await self.set("vectors", key, results, ttl_seconds)
    
    async def get_vector_results(self, element_group_id: str, query: Union[str, Dict[str, Any]]) -> Any:
        """Get cached vector search results."""
        query_hash = CacheKeyGenerator.hash_query(query)
        key = CacheKeyGenerator.generate_vector_key(element_group_id, query_hash)
        return await self.get("vectors", key)