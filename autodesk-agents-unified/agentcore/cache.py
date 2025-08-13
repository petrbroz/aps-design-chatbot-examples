"""
Unified Cache Manager for AgentCore

Provides centralized caching for all agents with support for
different storage backends and automatic cleanup.
"""

import asyncio
import json
import hashlib
import time
from typing import Any, Optional, Dict, List
from pathlib import Path
from dataclasses import dataclass, asdict
import aiofiles
import sqlite3
from datetime import datetime, timedelta


@dataclass
class CacheEntry:
    """Cache entry with metadata."""
    key: str
    value: Any
    created_at: datetime
    expires_at: Optional[datetime] = None
    access_count: int = 0
    last_accessed: Optional[datetime] = None
    size_bytes: int = 0


class CacheManager:
    """
    Unified cache manager for all AgentCore agents.
    
    Provides file-based and memory-based caching with automatic
    cleanup, expiration, and size management.
    """
    
    def __init__(self, cache_directory: Path, logger=None, max_memory_mb: int = 100):
        """Initialize cache manager."""
        self.cache_directory = cache_directory
        self.logger = logger
        self.max_memory_bytes = max_memory_mb * 1024 * 1024
        
        # Memory cache
        self._memory_cache: Dict[str, CacheEntry] = {}
        self._memory_size = 0
        
        # Database for persistent cache metadata
        self.db_path = cache_directory / "cache.db"
        
        # Cleanup task
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False
    
    async def initialize(self) -> None:
        """Initialize cache manager."""
        # Create cache directory
        self.cache_directory.mkdir(parents=True, exist_ok=True)
        
        # Initialize database
        await self._init_database()
        
        # Start cleanup task
        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        if self.logger:
            self.logger.info("Cache manager initialized", extra={
                "cache_directory": str(self.cache_directory),
                "max_memory_mb": self.max_memory_bytes / (1024 * 1024)
            })
    
    async def shutdown(self) -> None:
        """Shutdown cache manager."""
        self._running = False
        
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        if self.logger:
            self.logger.info("Cache manager shutdown")
    
    async def _init_database(self) -> None:
        """Initialize SQLite database for cache metadata."""
        def init_db():
            conn = sqlite3.connect(self.db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache_entries (
                    key TEXT PRIMARY KEY,
                    created_at TEXT,
                    expires_at TEXT,
                    access_count INTEGER DEFAULT 0,
                    last_accessed TEXT,
                    size_bytes INTEGER DEFAULT 0,
                    file_path TEXT
                )
            """)
            conn.commit()
            conn.close()
        
        # Run in thread pool to avoid blocking
        await asyncio.get_event_loop().run_in_executor(None, init_db)
    
    def _generate_cache_key(self, namespace: str, key: str) -> str:
        """Generate cache key with namespace."""
        combined = f"{namespace}:{key}"
        return hashlib.sha256(combined.encode()).hexdigest()
    
    async def get(self, namespace: str, key: str) -> Optional[Any]:
        """Get value from cache."""
        cache_key = self._generate_cache_key(namespace, key)
        
        # Check memory cache first
        if cache_key in self._memory_cache:
            entry = self._memory_cache[cache_key]
            
            # Check expiration
            if entry.expires_at and datetime.utcnow() > entry.expires_at:
                await self._remove_from_memory(cache_key)
                return None
            
            # Update access info
            entry.access_count += 1
            entry.last_accessed = datetime.utcnow()
            
            return entry.value
        
        # Check file cache
        return await self._get_from_file(cache_key)
    
    async def set(self, namespace: str, key: str, value: Any, 
                 ttl_seconds: Optional[int] = None, persist: bool = False) -> None:
        """Set value in cache."""
        cache_key = self._generate_cache_key(namespace, key)
        
        # Calculate expiration
        expires_at = None
        if ttl_seconds:
            expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
        
        # Serialize value
        serialized = json.dumps(value, default=str)
        size_bytes = len(serialized.encode())
        
        # Create cache entry
        entry = CacheEntry(
            key=cache_key,
            value=value,
            created_at=datetime.utcnow(),
            expires_at=expires_at,
            size_bytes=size_bytes
        )
        
        if persist:
            # Store in file cache
            await self._set_in_file(cache_key, entry, serialized)
        else:
            # Store in memory cache
            await self._set_in_memory(cache_key, entry)
        
        if self.logger:
            self.logger.debug("Cache entry set", extra={
                "namespace": namespace,
                "key": key,
                "size_bytes": size_bytes,
                "persist": persist,
                "ttl_seconds": ttl_seconds
            })
    
    async def _set_in_memory(self, cache_key: str, entry: CacheEntry) -> None:
        """Set entry in memory cache."""
        # Check if we need to free memory
        if self._memory_size + entry.size_bytes > self.max_memory_bytes:
            await self._evict_memory_entries(entry.size_bytes)
        
        # Remove existing entry if present
        if cache_key in self._memory_cache:
            old_entry = self._memory_cache[cache_key]
            self._memory_size -= old_entry.size_bytes
        
        # Add new entry
        self._memory_cache[cache_key] = entry
        self._memory_size += entry.size_bytes
    
    async def _set_in_file(self, cache_key: str, entry: CacheEntry, serialized: str) -> None:
        """Set entry in file cache."""
        file_path = self.cache_directory / f"{cache_key}.json"
        
        # Write file
        async with aiofiles.open(file_path, 'w') as f:
            await f.write(serialized)
        
        # Update database
        def update_db():
            conn = sqlite3.connect(self.db_path)
            conn.execute("""
                INSERT OR REPLACE INTO cache_entries 
                (key, created_at, expires_at, size_bytes, file_path)
                VALUES (?, ?, ?, ?, ?)
            """, (
                cache_key,
                entry.created_at.isoformat(),
                entry.expires_at.isoformat() if entry.expires_at else None,
                entry.size_bytes,
                str(file_path)
            ))
            conn.commit()
            conn.close()
        
        await asyncio.get_event_loop().run_in_executor(None, update_db)
    
    async def _get_from_file(self, cache_key: str) -> Optional[Any]:
        """Get entry from file cache."""
        def get_metadata():
            conn = sqlite3.connect(self.db_path)
            cursor = conn.execute(
                "SELECT created_at, expires_at, file_path FROM cache_entries WHERE key = ?",
                (cache_key,)
            )
            row = cursor.fetchone()
            conn.close()
            return row
        
        # Get metadata from database
        metadata = await asyncio.get_event_loop().run_in_executor(None, get_metadata)
        if not metadata:
            return None
        
        created_at_str, expires_at_str, file_path_str = metadata
        
        # Check expiration
        if expires_at_str:
            expires_at = datetime.fromisoformat(expires_at_str)
            if datetime.utcnow() > expires_at:
                await self._remove_from_file(cache_key)
                return None
        
        # Read file
        file_path = Path(file_path_str)
        if not file_path.exists():
            return None
        
        try:
            async with aiofiles.open(file_path, 'r') as f:
                content = await f.read()
            
            value = json.loads(content)
            
            # Update access count
            def update_access():
                conn = sqlite3.connect(self.db_path)
                conn.execute("""
                    UPDATE cache_entries 
                    SET access_count = access_count + 1, last_accessed = ?
                    WHERE key = ?
                """, (datetime.utcnow().isoformat(), cache_key))
                conn.commit()
                conn.close()
            
            await asyncio.get_event_loop().run_in_executor(None, update_access)
            
            return value
            
        except Exception as e:
            if self.logger:
                self.logger.error("Failed to read cache file", extra={
                    "cache_key": cache_key,
                    "file_path": str(file_path),
                    "error": str(e)
                })
            return None
    
    async def delete(self, namespace: str, key: str) -> bool:
        """Delete entry from cache."""
        cache_key = self._generate_cache_key(namespace, key)
        
        # Remove from memory
        removed_memory = await self._remove_from_memory(cache_key)
        
        # Remove from file
        removed_file = await self._remove_from_file(cache_key)
        
        return removed_memory or removed_file
    
    async def _remove_from_memory(self, cache_key: str) -> bool:
        """Remove entry from memory cache."""
        if cache_key in self._memory_cache:
            entry = self._memory_cache.pop(cache_key)
            self._memory_size -= entry.size_bytes
            return True
        return False
    
    async def _remove_from_file(self, cache_key: str) -> bool:
        """Remove entry from file cache."""
        def remove_from_db():
            conn = sqlite3.connect(self.db_path)
            cursor = conn.execute(
                "SELECT file_path FROM cache_entries WHERE key = ?",
                (cache_key,)
            )
            row = cursor.fetchone()
            
            if row:
                file_path = Path(row[0])
                if file_path.exists():
                    file_path.unlink()
                
                conn.execute("DELETE FROM cache_entries WHERE key = ?", (cache_key,))
                conn.commit()
                conn.close()
                return True
            
            conn.close()
            return False
        
        return await asyncio.get_event_loop().run_in_executor(None, remove_from_db)
    
    async def _evict_memory_entries(self, needed_bytes: int) -> None:
        """Evict entries from memory cache to free space."""
        # Sort by last accessed (LRU)
        entries = sorted(
            self._memory_cache.items(),
            key=lambda x: x[1].last_accessed or x[1].created_at
        )
        
        freed_bytes = 0
        for cache_key, entry in entries:
            if freed_bytes >= needed_bytes:
                break
            
            await self._remove_from_memory(cache_key)
            freed_bytes += entry.size_bytes
    
    async def _cleanup_loop(self) -> None:
        """Cleanup expired entries periodically."""
        while self._running:
            try:
                await self._cleanup_expired()
                await asyncio.sleep(300)  # Run every 5 minutes
            except asyncio.CancelledError:
                break
            except Exception as e:
                if self.logger:
                    self.logger.error("Error in cache cleanup", extra={
                        "error": str(e),
                        "error_type": type(e).__name__
                    })
                await asyncio.sleep(300)
    
    async def _cleanup_expired(self) -> None:
        """Clean up expired cache entries."""
        now = datetime.utcnow()
        
        # Clean memory cache
        expired_keys = [
            key for key, entry in self._memory_cache.items()
            if entry.expires_at and now > entry.expires_at
        ]
        
        for key in expired_keys:
            await self._remove_from_memory(key)
        
        # Clean file cache
        def cleanup_files():
            conn = sqlite3.connect(self.db_path)
            cursor = conn.execute("""
                SELECT key, file_path FROM cache_entries 
                WHERE expires_at IS NOT NULL AND expires_at < ?
            """, (now.isoformat(),))
            
            expired_files = cursor.fetchall()
            
            for key, file_path in expired_files:
                # Remove file
                path = Path(file_path)
                if path.exists():
                    path.unlink()
                
                # Remove from database
                conn.execute("DELETE FROM cache_entries WHERE key = ?", (key,))
            
            conn.commit()
            conn.close()
            
            return len(expired_files)
        
        cleaned_count = await asyncio.get_event_loop().run_in_executor(None, cleanup_files)
        
        if cleaned_count > 0 and self.logger:
            self.logger.info("Cache cleanup completed", extra={
                "expired_entries": cleaned_count
            })
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        def get_file_stats():
            conn = sqlite3.connect(self.db_path)
            cursor = conn.execute("SELECT COUNT(*), SUM(size_bytes) FROM cache_entries")
            file_count, file_size = cursor.fetchone()
            conn.close()
            return file_count or 0, file_size or 0
        
        file_count, file_size = await asyncio.get_event_loop().run_in_executor(None, get_file_stats)
        
        return {
            "memory_cache": {
                "entries": len(self._memory_cache),
                "size_bytes": self._memory_size,
                "size_mb": round(self._memory_size / (1024 * 1024), 2),
                "max_size_mb": round(self.max_memory_bytes / (1024 * 1024), 2)
            },
            "file_cache": {
                "entries": file_count,
                "size_bytes": file_size,
                "size_mb": round(file_size / (1024 * 1024), 2)
            },
            "total_entries": len(self._memory_cache) + file_count
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """Health check for cache manager."""
        try:
            stats = await self.get_stats()
            
            return {
                "status": "healthy",
                "cache_directory": str(self.cache_directory),
                "directory_exists": self.cache_directory.exists(),
                "database_exists": self.db_path.exists(),
                **stats
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "error_type": type(e).__name__
            }