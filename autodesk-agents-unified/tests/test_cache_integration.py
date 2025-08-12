"""
Integration tests for cache manager with agent core.
"""

import pytest
import tempfile
import shutil
from unittest.mock import MagicMock

from agent_core.cache import CacheManager, CacheKeyGenerator


@pytest.mark.asyncio
async def test_cache_manager_integration():
    """Test cache manager integration with agent patterns."""
    temp_dir = tempfile.mkdtemp()
    
    try:
        # Create cache manager
        cache_manager = CacheManager(
            cache_directory=temp_dir,
            default_ttl=3600,
            max_memory_entries=100,
            cleanup_interval=300
        )
        
        # Test agent instance caching (simulating agent lifecycle)
        mock_agent = MagicMock()
        mock_agent.agent_type = "model_properties"
        mock_agent.identifier = "test_urn_123"
        
        # Cache the agent
        await cache_manager.cache_agent_instance(
            mock_agent.agent_type, 
            mock_agent.identifier, 
            mock_agent,
            ttl_seconds=7200
        )
        
        # Retrieve the agent
        cached_agent = await cache_manager.get_agent_instance(
            mock_agent.agent_type,
            mock_agent.identifier
        )
        
        assert cached_agent == mock_agent
        assert cached_agent.agent_type == "model_properties"
        
        # Test index caching (simulating model properties workflow)
        project_id = "test_project_123"
        version_id = "test_version_456"
        index_data = {
            "properties": [
                {"id": 1, "name": "Wall Height", "category": "Dimensions"},
                {"id": 2, "name": "Material", "category": "Materials"}
            ],
            "metadata": {
                "total_count": 2,
                "indexed_at": "2024-01-01T00:00:00Z"
            }
        }
        
        # Cache the index
        await cache_manager.cache_index(project_id, version_id, index_data)
        
        # Retrieve the index
        cached_index = await cache_manager.get_index(project_id, version_id)
        assert cached_index == index_data
        assert cached_index["metadata"]["total_count"] == 2
        
        # Test property query caching
        urn = "test_urn_789"
        query = {
            "filter": "category=Walls",
            "properties": ["Height", "Material"],
            "limit": 100
        }
        
        properties_result = {
            "results": [
                {"objectId": 1, "Height": "3000mm", "Material": "Concrete"},
                {"objectId": 2, "Height": "2800mm", "Material": "Brick"}
            ],
            "total": 2
        }
        
        # Cache the properties
        await cache_manager.cache_properties(urn, query, properties_result)
        
        # Retrieve the properties
        cached_properties = await cache_manager.get_properties(urn, query)
        assert cached_properties == properties_result
        assert len(cached_properties["results"]) == 2
        
        # Test database path caching (simulating SQLite agent workflow)
        db_urn = "test_db_urn_456"
        db_path = f"{temp_dir}/database_{db_urn}.db"
        
        # Cache the database path
        await cache_manager.cache_database(db_urn, db_path)
        
        # Retrieve the database path
        cached_db_path = await cache_manager.get_database(db_urn)
        assert cached_db_path == db_path
        
        # Test vector search caching (simulating AEC Data Model workflow)
        element_group_id = "test_group_789"
        vector_query = {
            "text": "find all structural elements",
            "similarity_threshold": 0.8,
            "max_results": 10
        }
        
        vector_results = {
            "documents": [
                {"id": "elem_1", "text": "Structural beam", "score": 0.95},
                {"id": "elem_2", "text": "Load bearing wall", "score": 0.87}
            ],
            "metadata": {
                "query_time_ms": 150,
                "total_documents": 2
            }
        }
        
        # Cache the vector results
        await cache_manager.cache_vector_results(element_group_id, vector_query, vector_results)
        
        # Retrieve the vector results
        cached_vector_results = await cache_manager.get_vector_results(element_group_id, vector_query)
        assert cached_vector_results == vector_results
        assert len(cached_vector_results["documents"]) == 2
        
        # Test cache statistics
        stats = await cache_manager.get_cache_stats()
        assert stats["memory_entries"] > 0
        assert stats["file_entries"] > 0
        assert "agents" in stats["namespace_stats"]
        assert "indexes" in stats["namespace_stats"]
        assert "properties" in stats["namespace_stats"]
        assert "databases" in stats["namespace_stats"]
        assert "vectors" in stats["namespace_stats"]
        
        # Test namespace clearing (simulating cleanup scenarios)
        cleared_agents = await cache_manager.clear_namespace("agents")
        assert cleared_agents > 0
        
        # Verify agent is no longer cached
        cached_agent_after_clear = await cache_manager.get_agent_instance(
            mock_agent.agent_type,
            mock_agent.identifier
        )
        assert cached_agent_after_clear is None
        
        # But other namespaces should still have data
        cached_index_after_clear = await cache_manager.get_index(project_id, version_id)
        assert cached_index_after_clear == index_data
        
        # Test pattern-based invalidation
        # Add some test data with patterns
        await cache_manager.set("test", "user:123:profile", "profile_data")
        await cache_manager.set("test", "user:123:settings", "settings_data")
        await cache_manager.set("test", "user:456:profile", "other_profile")
        
        # Invalidate all user:123 entries
        invalidated = await cache_manager.invalidate_pattern("test:user:123:*")
        assert invalidated >= 2
        
        # Verify pattern invalidation worked
        assert await cache_manager.get("test", "user:123:profile") is None
        assert await cache_manager.get("test", "user:123:settings") is None
        assert await cache_manager.get("test", "user:456:profile") == "other_profile"
        
    finally:
        await cache_manager.shutdown()
        shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_cache_key_generation_consistency():
    """Test that cache key generation is consistent across different scenarios."""
    
    # Test agent keys
    key1 = CacheKeyGenerator.generate_agent_key("model_properties", "urn123")
    key2 = CacheKeyGenerator.generate_agent_key("model_properties", "urn123")
    key3 = CacheKeyGenerator.generate_agent_key("aec_data_model", "urn123")
    
    assert key1 == key2  # Same inputs should generate same key
    assert key1 != key3  # Different agent types should generate different keys
    
    # Test query hashing consistency
    query1 = {"filter": "category=walls", "limit": 100}
    query2 = {"limit": 100, "filter": "category=walls"}  # Different order
    query3 = {"filter": "category=doors", "limit": 100}  # Different content
    
    hash1 = CacheKeyGenerator.hash_query(query1)
    hash2 = CacheKeyGenerator.hash_query(query2)
    hash3 = CacheKeyGenerator.hash_query(query3)
    
    assert hash1 == hash2  # Order shouldn't matter
    assert hash1 != hash3  # Different content should generate different hash
    
    # Test properties key generation
    props_key1 = CacheKeyGenerator.generate_properties_key("urn123", hash1)
    props_key2 = CacheKeyGenerator.generate_properties_key("urn123", hash2)
    props_key3 = CacheKeyGenerator.generate_properties_key("urn456", hash1)
    
    assert props_key1 == props_key2  # Same URN and equivalent queries
    assert props_key1 != props_key3  # Different URNs


if __name__ == "__main__":
    pytest.main([__file__])