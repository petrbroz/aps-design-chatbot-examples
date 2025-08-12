"""
Unit tests for the unified caching system.
"""

import pytest
import asyncio
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from agent_core.cache import CacheManager, CacheStrategy, CacheKeyGenerator


class TestCacheKeyGenerator:
    """Test cache key generation strategies."""
    
    def test_generate_agent_key(self):
        """Test agent key generation."""
        key = CacheKeyGenerator.generate_agent_key("model_properties", "test_urn")
        assert key == "agent:model_properties:test_urn"
    
    def test_generate_index_key(self):
        """Test index key generation."""
        key = CacheKeyGenerator.generate_index_key("project123", "version456")
        assert key == "index:project123:version456"
    
    def test_generate_properties_key(self):
        """Test properties key generation."""
        key = CacheKeyGenerator.generate_properties_key("urn123", "hash456")
        assert key == "properties:urn123:hash456"
    
    def test_generate_database_key(self):
        """Test database key generation."""
        key = CacheKeyGenerator.generate_database_key("urn123")
        assert key == "database:urn123"
    
    def test_generate_vector_key(self):
        """Test vector key generation."""
        key = CacheKeyGenerator.generate_vector_key("group123", "hash456")
        assert key == "vector:group123:hash456"
    
    def test_generate_custom_key(self):
        """Test custom key generation."""
        key = CacheKeyGenerator.generate_custom_key("custom", "part1", "part2", "part3")
        assert key == "custom:part1:part2:part3"
    
    def test_hash_query_string(self):
        """Test query hashing with string input."""
        hash1 = CacheKeyGenerator.hash_query("test query")
        hash2 = CacheKeyGenerator.hash_query("test query")
        hash3 = CacheKeyGenerator.hash_query("different query")
        
        assert hash1 == hash2
        assert hash1 != hash3
        assert len(hash1) == 16
    
    def test_hash_query_dict(self):
        """Test query hashing with dictionary input."""
        query1 = {"key1": "value1", "key2": "value2"}
        query2 = {"key2": "value2", "key1": "value1"}  # Different order
        query3 = {"key1": "value1", "key2": "different"}
        
        hash1 = CacheKeyGenerator.hash_query(query1)
        hash2 = CacheKeyGenerator.hash_query(query2)
        hash3 = CacheKeyGenerator.hash_query(query3)
        
        assert hash1 == hash2  # Order shouldn't matter
        assert hash1 != hash3
        assert len(hash1) == 16


async def create_test_cache_manager():
    """Helper to create a test cache manager."""
    temp_dir = tempfile.mkdtemp()
    manager = CacheManager(
        cache_directory=temp_dir,
        default_ttl=3600,
        max_memory_entries=10,
        cleanup_interval=60
    )
    return manager, temp_dir


async def cleanup_test_cache_manager(manager, temp_dir):
    """Helper to cleanup test cache manager."""
    await manager.shutdown()
    shutil.rmtree(temp_dir, ignore_errors=True)
    
@pytest.mark.asyncio
async def test_basic_set_get():
    """Test basic cache set and get operations."""
    manager, temp_dir = await create_test_cache_manager()
    try:
        await manager.set("test", "key1", "value1")
        result = await manager.get("test", "key1")
        assert result == "value1"
    finally:
        await cleanup_test_cache_manager(manager, temp_dir)
    
    @pytest.mark.asyncio
    async def test_get_default_value(self, cache_manager):
        """Test getting non-existent key returns default."""
        result = await cache_manager.get("test", "nonexistent", "default")
        assert result == "default"
    
    @pytest.mark.asyncio
    async def test_cache_strategies(self, cache_manager):
        """Test different cache strategies."""
        # Memory only
        await cache_manager.set("test", "memory_key", "memory_value", 
                               strategy=CacheStrategy.MEMORY_ONLY)
        result = await cache_manager.get("test", "memory_key", 
                                       strategy=CacheStrategy.MEMORY_ONLY)
        assert result == "memory_value"
        
        # Should not be in file cache
        result = await cache_manager.get("test", "memory_key", 
                                       strategy=CacheStrategy.FILE_ONLY)
        assert result is None
        
        # File only
        await cache_manager.set("test", "file_key", "file_value", 
                               strategy=CacheStrategy.FILE_ONLY)
        result = await cache_manager.get("test", "file_key", 
                                       strategy=CacheStrategy.FILE_ONLY)
        assert result == "file_value"
        
        # Should not be in memory cache initially
        result = await cache_manager.get("test", "file_key", 
                                       strategy=CacheStrategy.MEMORY_ONLY)
        assert result is None
    
    @pytest.mark.asyncio
    async def test_ttl_expiration(self, cache_manager):
        """Test TTL expiration."""
        # Set with very short TTL
        await cache_manager.set("test", "expire_key", "expire_value", ttl_seconds=1)
        
        # Should be available immediately
        result = await cache_manager.get("test", "expire_key")
        assert result == "expire_value"
        
        # Wait for expiration
        await asyncio.sleep(1.1)
        
        # Should be expired
        result = await cache_manager.get("test", "expire_key")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_delete(self, cache_manager):
        """Test cache deletion."""
        await cache_manager.set("test", "delete_key", "delete_value")
        
        # Verify it exists
        result = await cache_manager.get("test", "delete_key")
        assert result == "delete_value"
        
        # Delete it
        deleted = await cache_manager.delete("test", "delete_key")
        assert deleted is True
        
        # Verify it's gone
        result = await cache_manager.get("test", "delete_key")
        assert result is None
        
        # Delete non-existent key
        deleted = await cache_manager.delete("test", "nonexistent")
        assert deleted is False
    
    @pytest.mark.asyncio
    async def test_clear_namespace(self, cache_manager):
        """Test clearing entire namespace."""
        # Set multiple keys in different namespaces
        await cache_manager.set("ns1", "key1", "value1")
        await cache_manager.set("ns1", "key2", "value2")
        await cache_manager.set("ns2", "key1", "value3")
        
        # Clear namespace 1
        cleared = await cache_manager.clear_namespace("ns1")
        assert cleared == 2
        
        # Verify ns1 keys are gone
        assert await cache_manager.get("ns1", "key1") is None
        assert await cache_manager.get("ns1", "key2") is None
        
        # Verify ns2 key still exists
        assert await cache_manager.get("ns2", "key1") == "value3"
    
    @pytest.mark.asyncio
    async def test_cleanup_expired(self, cache_manager):
        """Test cleanup of expired entries."""
        # Set some entries with different TTLs
        await cache_manager.set("test", "keep", "keep_value", ttl_seconds=3600)
        await cache_manager.set("test", "expire1", "expire_value1", ttl_seconds=1)
        await cache_manager.set("test", "expire2", "expire_value2", ttl_seconds=1)
        
        # Wait for expiration
        await asyncio.sleep(1.1)
        
        # Run cleanup
        cleaned = await cache_manager.cleanup_expired()
        assert cleaned == 2
        
        # Verify only non-expired entry remains
        assert await cache_manager.get("test", "keep") == "keep_value"
        assert await cache_manager.get("test", "expire1") is None
        assert await cache_manager.get("test", "expire2") is None
    
    @pytest.mark.asyncio
    async def test_invalidate_pattern(self, cache_manager):
        """Test pattern-based cache invalidation."""
        # Set various keys
        await cache_manager.set("test", "user:123:profile", "profile1")
        await cache_manager.set("test", "user:123:settings", "settings1")
        await cache_manager.set("test", "user:456:profile", "profile2")
        await cache_manager.set("test", "product:123", "product1")
        
        # Invalidate all user:123 entries
        invalidated = await cache_manager.invalidate_pattern("test:user:123:*")
        assert invalidated == 2
        
        # Verify correct entries were invalidated
        assert await cache_manager.get("test", "user:123:profile") is None
        assert await cache_manager.get("test", "user:123:settings") is None
        assert await cache_manager.get("test", "user:456:profile") == "profile2"
        assert await cache_manager.get("test", "product:123") == "product1"
    
    @pytest.mark.asyncio
    async def test_lru_eviction(self, cache_manager):
        """Test LRU eviction when memory cache is full."""
        # Fill cache beyond max_memory_entries (10)
        for i in range(15):
            await cache_manager.set("test", f"key{i}", f"value{i}", 
                                   strategy=CacheStrategy.MEMORY_ONLY)
        
        # Should only have max_memory_entries in memory
        stats = await cache_manager.get_cache_stats()
        assert stats["memory_entries"] <= cache_manager.max_memory_entries
        
        # Oldest entries should be evicted
        assert await cache_manager.get("test", "key0", strategy=CacheStrategy.MEMORY_ONLY) is None
        assert await cache_manager.get("test", "key14", strategy=CacheStrategy.MEMORY_ONLY) == "value14"
    
    @pytest.mark.asyncio
    async def test_get_namespaces(self, cache_manager):
        """Test getting all cache namespaces."""
        await cache_manager.set("ns1", "key1", "value1")
        await cache_manager.set("ns2", "key2", "value2")
        await cache_manager.set("ns3", "key3", "value3")
        
        namespaces = await cache_manager.get_namespaces()
        assert "ns1" in namespaces
        assert "ns2" in namespaces
        assert "ns3" in namespaces
    
    @pytest.mark.asyncio
    async def test_cache_stats(self, cache_manager):
        """Test cache statistics."""
        await cache_manager.set("test1", "key1", "value1")
        await cache_manager.set("test2", "key2", "value2")
        
        stats = await cache_manager.get_cache_stats()
        
        assert "memory_entries" in stats
        assert "file_entries" in stats
        assert "total_size_bytes" in stats
        assert "total_size_mb" in stats
        assert "cache_directory" in stats
        assert "namespace_stats" in stats
        assert "max_memory_entries" in stats
        assert "default_ttl" in stats
        assert "cleanup_interval" in stats
        
        assert stats["memory_entries"] >= 2
        assert stats["namespace_stats"]["test1"] >= 1
        assert stats["namespace_stats"]["test2"] >= 1
    
    @pytest.mark.asyncio
    async def test_convenience_methods(self, cache_manager):
        """Test convenience methods for specific agent patterns."""
        # Test agent instance caching
        mock_agent = MagicMock()
        await cache_manager.cache_agent_instance("model_properties", "urn123", mock_agent)
        retrieved_agent = await cache_manager.get_agent_instance("model_properties", "urn123")
        assert retrieved_agent == mock_agent
        
        # Test index caching
        index_data = {"properties": ["prop1", "prop2"]}
        await cache_manager.cache_index("project123", "version456", index_data)
        retrieved_index = await cache_manager.get_index("project123", "version456")
        assert retrieved_index == index_data
        
        # Test properties caching
        properties_data = {"results": [{"id": 1, "name": "test"}]}
        query = {"filter": "category=wall"}
        await cache_manager.cache_properties("urn123", query, properties_data)
        retrieved_properties = await cache_manager.get_properties("urn123", query)
        assert retrieved_properties == properties_data
        
        # Test database caching
        db_path = "/path/to/database.db"
        await cache_manager.cache_database("urn123", db_path)
        retrieved_path = await cache_manager.get_database("urn123")
        assert retrieved_path == db_path
        
        # Test vector results caching
        vector_results = {"documents": ["doc1", "doc2"], "scores": [0.9, 0.8]}
        vector_query = {"text": "find similar elements"}
        await cache_manager.cache_vector_results("group123", vector_query, vector_results)
        retrieved_results = await cache_manager.get_vector_results("group123", vector_query)
        assert retrieved_results == vector_results
    
    @pytest.mark.asyncio
    async def test_file_corruption_handling(self, cache_manager):
        """Test handling of corrupted cache files."""
        # Create a corrupted cache file
        cache_key = cache_manager._generate_cache_key("test", "corrupted")
        cache_file = cache_manager._get_cache_file_path(cache_key)
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Write invalid data
        with open(cache_file, 'w') as f:
            f.write("invalid pickle data")
        
        # Should handle corruption gracefully
        result = await cache_manager.get("test", "corrupted")
        assert result is None
        
        # Cleanup should remove corrupted files
        cleaned = await cache_manager.cleanup_expired()
        assert cleaned >= 1
        assert not cache_file.exists()
    
    @pytest.mark.asyncio
    async def test_concurrent_access(self, cache_manager):
        """Test concurrent cache access."""
        async def set_values(start_idx, count):
            for i in range(start_idx, start_idx + count):
                await cache_manager.set("concurrent", f"key{i}", f"value{i}")
        
        async def get_values(start_idx, count):
            results = []
            for i in range(start_idx, start_idx + count):
                result = await cache_manager.get("concurrent", f"key{i}")
                results.append(result)
            return results
        
        # Run concurrent operations
        await asyncio.gather(
            set_values(0, 10),
            set_values(10, 10),
            set_values(20, 10)
        )
        
        # Verify all values were set correctly
        results = await get_values(0, 30)
        expected = [f"value{i}" for i in range(30)]
        assert results == expected
    
    @pytest.mark.asyncio
    async def test_shutdown(self, cache_manager):
        """Test cache manager shutdown."""
        # Verify cleanup task is running
        assert cache_manager._cleanup_task is not None
        assert not cache_manager._cleanup_task.done()
        
        # Shutdown
        await cache_manager.shutdown()
        
        # Verify cleanup task is cancelled
        assert cache_manager._cleanup_task.done()


@pytest.mark.asyncio
async def test_periodic_cleanup():
    """Test periodic cleanup functionality."""
    temp_dir = tempfile.mkdtemp()
    
    try:
        # Create cache manager with very short cleanup interval
        cache_manager = CacheManager(
            cache_directory=temp_dir,
            cleanup_interval=1  # 1 second
        )
        
        # Set entries with short TTL
        await cache_manager.set("test", "expire1", "value1", ttl_seconds=1)
        await cache_manager.set("test", "expire2", "value2", ttl_seconds=1)
        await cache_manager.set("test", "keep", "value3", ttl_seconds=3600)
        
        # Wait for entries to expire and cleanup to run
        await asyncio.sleep(2.5)
        
        # Verify expired entries were cleaned up
        assert await cache_manager.get("test", "expire1") is None
        assert await cache_manager.get("test", "expire2") is None
        assert await cache_manager.get("test", "keep") == "value3"
        
        await cache_manager.shutdown()
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    pytest.main([__file__])