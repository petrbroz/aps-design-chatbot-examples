"""
Simple unit tests for the unified caching system.
"""

import pytest
import asyncio
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import MagicMock

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
    
    def test_hash_query_string(self):
        """Test query hashing with string input."""
        hash1 = CacheKeyGenerator.hash_query("test query")
        hash2 = CacheKeyGenerator.hash_query("test query")
        hash3 = CacheKeyGenerator.hash_query("different query")
        
        assert hash1 == hash2
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
async def test_get_default_value():
    """Test getting non-existent key returns default."""
    manager, temp_dir = await create_test_cache_manager()
    try:
        result = await manager.get("test", "nonexistent", "default")
        assert result == "default"
    finally:
        await cleanup_test_cache_manager(manager, temp_dir)


@pytest.mark.asyncio
async def test_cache_strategies():
    """Test different cache strategies."""
    manager, temp_dir = await create_test_cache_manager()
    try:
        # Memory only
        await manager.set("test", "memory_key", "memory_value", 
                         strategy=CacheStrategy.MEMORY_ONLY)
        result = await manager.get("test", "memory_key", 
                                 strategy=CacheStrategy.MEMORY_ONLY)
        assert result == "memory_value"
        
        # Should not be in file cache
        result = await manager.get("test", "memory_key", 
                                 strategy=CacheStrategy.FILE_ONLY)
        assert result is None
        
        # File only
        await manager.set("test", "file_key", "file_value", 
                         strategy=CacheStrategy.FILE_ONLY)
        result = await manager.get("test", "file_key", 
                                 strategy=CacheStrategy.FILE_ONLY)
        assert result == "file_value"
        
        # Should not be in memory cache initially
        result = await manager.get("test", "file_key", 
                                 strategy=CacheStrategy.MEMORY_ONLY)
        assert result is None
    finally:
        await cleanup_test_cache_manager(manager, temp_dir)


@pytest.mark.asyncio
async def test_ttl_expiration():
    """Test TTL expiration."""
    manager, temp_dir = await create_test_cache_manager()
    try:
        # Set with very short TTL
        await manager.set("test", "expire_key", "expire_value", ttl_seconds=1)
        
        # Should be available immediately
        result = await manager.get("test", "expire_key")
        assert result == "expire_value"
        
        # Wait for expiration
        await asyncio.sleep(1.1)
        
        # Should be expired
        result = await manager.get("test", "expire_key")
        assert result is None
    finally:
        await cleanup_test_cache_manager(manager, temp_dir)


@pytest.mark.asyncio
async def test_delete():
    """Test cache deletion."""
    manager, temp_dir = await create_test_cache_manager()
    try:
        await manager.set("test", "delete_key", "delete_value")
        
        # Verify it exists
        result = await manager.get("test", "delete_key")
        assert result == "delete_value"
        
        # Delete it
        deleted = await manager.delete("test", "delete_key")
        assert deleted is True
        
        # Verify it's gone
        result = await manager.get("test", "delete_key")
        assert result is None
        
        # Delete non-existent key
        deleted = await manager.delete("test", "nonexistent")
        assert deleted is False
    finally:
        await cleanup_test_cache_manager(manager, temp_dir)


@pytest.mark.asyncio
async def test_clear_namespace():
    """Test clearing entire namespace."""
    manager, temp_dir = await create_test_cache_manager()
    try:
        # Set multiple keys in different namespaces
        await manager.set("ns1", "key1", "value1")
        await manager.set("ns1", "key2", "value2")
        await manager.set("ns2", "key1", "value3")
        
        # Clear namespace 1
        cleared = await manager.clear_namespace("ns1")
        assert cleared >= 2  # Could be more due to memory + file cache
        
        # Verify ns1 keys are gone
        assert await manager.get("ns1", "key1") is None
        assert await manager.get("ns1", "key2") is None
        
        # Verify ns2 key still exists
        assert await manager.get("ns2", "key1") == "value3"
    finally:
        await cleanup_test_cache_manager(manager, temp_dir)


@pytest.mark.asyncio
async def test_cleanup_expired():
    """Test cleanup of expired entries."""
    manager, temp_dir = await create_test_cache_manager()
    try:
        # Set some entries with different TTLs
        await manager.set("test", "keep", "keep_value", ttl_seconds=3600)
        await manager.set("test", "expire1", "expire_value1", ttl_seconds=1)
        await manager.set("test", "expire2", "expire_value2", ttl_seconds=1)
        
        # Wait for expiration
        await asyncio.sleep(1.1)
        
        # Run cleanup
        cleaned = await manager.cleanup_expired()
        assert cleaned >= 2  # Could be more due to memory + file cache
        
        # Verify only non-expired entry remains
        assert await manager.get("test", "keep") == "keep_value"
        assert await manager.get("test", "expire1") is None
        assert await manager.get("test", "expire2") is None
    finally:
        await cleanup_test_cache_manager(manager, temp_dir)


@pytest.mark.asyncio
async def test_convenience_methods():
    """Test convenience methods for specific agent patterns."""
    manager, temp_dir = await create_test_cache_manager()
    try:
        # Test agent instance caching
        mock_agent = MagicMock()
        await manager.cache_agent_instance("model_properties", "urn123", mock_agent)
        retrieved_agent = await manager.get_agent_instance("model_properties", "urn123")
        assert retrieved_agent == mock_agent
        
        # Test index caching
        index_data = {"properties": ["prop1", "prop2"]}
        await manager.cache_index("project123", "version456", index_data)
        retrieved_index = await manager.get_index("project123", "version456")
        assert retrieved_index == index_data
        
        # Test properties caching
        properties_data = {"results": [{"id": 1, "name": "test"}]}
        query = {"filter": "category=wall"}
        await manager.cache_properties("urn123", query, properties_data)
        retrieved_properties = await manager.get_properties("urn123", query)
        assert retrieved_properties == properties_data
        
        # Test database caching
        db_path = "/path/to/database.db"
        await manager.cache_database("urn123", db_path)
        retrieved_path = await manager.get_database("urn123")
        assert retrieved_path == db_path
        
        # Test vector results caching
        vector_results = {"documents": ["doc1", "doc2"], "scores": [0.9, 0.8]}
        vector_query = {"text": "find similar elements"}
        await manager.cache_vector_results("group123", vector_query, vector_results)
        retrieved_results = await manager.get_vector_results("group123", vector_query)
        assert retrieved_results == vector_results
    finally:
        await cleanup_test_cache_manager(manager, temp_dir)


@pytest.mark.asyncio
async def test_cache_stats():
    """Test cache statistics."""
    manager, temp_dir = await create_test_cache_manager()
    try:
        await manager.set("test1", "key1", "value1")
        await manager.set("test2", "key2", "value2")
        
        stats = await manager.get_cache_stats()
        
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
    finally:
        await cleanup_test_cache_manager(manager, temp_dir)


if __name__ == "__main__":
    pytest.main([__file__])