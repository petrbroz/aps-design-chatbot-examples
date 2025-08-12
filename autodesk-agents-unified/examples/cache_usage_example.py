"""
Example demonstrating how to use the unified cache manager with agents.
"""

import asyncio
import tempfile
import shutil
import sys
import os

# Add the parent directory to the path so we can import agent_core
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_core.cache import CacheManager, CacheStrategy, CacheKeyGenerator


async def demonstrate_cache_usage():
    """Demonstrate various cache usage patterns."""
    
    # Create a temporary cache directory for this example
    temp_dir = tempfile.mkdtemp()
    print(f"Using cache directory: {temp_dir}")
    
    try:
        # Initialize cache manager
        cache_manager = CacheManager(
            cache_directory=temp_dir,
            default_ttl=3600,  # 1 hour default TTL
            max_memory_entries=1000,
            cleanup_interval=300  # 5 minutes
        )
        
        print("Cache manager initialized")
        
        # Example 1: Agent instance caching
        print("\n=== Agent Instance Caching ===")
        
        # Simulate caching an agent instance
        agent_data = {
            "type": "model_properties",
            "urn": "test_urn_123",
            "initialized_at": "2024-01-01T00:00:00Z",
            "tools": ["create_index", "query_properties"]
        }
        
        await cache_manager.cache_agent_instance(
            "model_properties", 
            "test_urn_123", 
            agent_data,
            ttl_seconds=7200  # 2 hours for agent instances
        )
        
        # Retrieve the cached agent
        cached_agent = await cache_manager.get_agent_instance("model_properties", "test_urn_123")
        print(f"Cached agent: {cached_agent}")
        
        # Example 2: Index caching
        print("\n=== Index Caching ===")
        
        index_data = {
            "properties": [
                {"id": 1, "name": "Height", "category": "Dimensions"},
                {"id": 2, "name": "Width", "category": "Dimensions"},
                {"id": 3, "name": "Material", "category": "Materials"}
            ],
            "total_count": 3,
            "created_at": "2024-01-01T00:00:00Z"
        }
        
        await cache_manager.cache_index("project_123", "version_456", index_data)
        cached_index = await cache_manager.get_index("project_123", "version_456")
        print(f"Cached index has {cached_index['total_count']} properties")
        
        # Example 3: Property query caching
        print("\n=== Property Query Caching ===")
        
        query = {
            "filter": "category=Walls",
            "properties": ["Height", "Material"],
            "limit": 50
        }
        
        query_results = {
            "results": [
                {"objectId": 1, "Height": "3000mm", "Material": "Concrete"},
                {"objectId": 2, "Height": "2800mm", "Material": "Brick"}
            ],
            "total": 2,
            "query_time_ms": 45
        }
        
        await cache_manager.cache_properties("test_urn_123", query, query_results)
        cached_results = await cache_manager.get_properties("test_urn_123", query)
        print(f"Cached query returned {len(cached_results['results'])} results")
        
        # Example 4: Database path caching
        print("\n=== Database Path Caching ===")
        
        db_path = f"{temp_dir}/model_data.db"
        await cache_manager.cache_database("test_urn_123", db_path)
        cached_db_path = await cache_manager.get_database("test_urn_123")
        print(f"Cached database path: {cached_db_path}")
        
        # Example 5: Vector search results caching
        print("\n=== Vector Search Caching ===")
        
        vector_query = {
            "text": "structural elements",
            "similarity_threshold": 0.8,
            "max_results": 10
        }
        
        vector_results = {
            "documents": [
                {"id": "elem_1", "text": "Steel beam", "score": 0.95},
                {"id": "elem_2", "text": "Concrete column", "score": 0.87}
            ],
            "search_time_ms": 120
        }
        
        await cache_manager.cache_vector_results("group_789", vector_query, vector_results)
        cached_vector_results = await cache_manager.get_vector_results("group_789", vector_query)
        print(f"Cached vector search returned {len(cached_vector_results['documents'])} documents")
        
        # Example 6: Cache strategies
        print("\n=== Cache Strategies ===")
        
        # Memory only (fast access, doesn't persist)
        await cache_manager.set("temp", "session_data", {"user_id": 123}, 
                               strategy=CacheStrategy.MEMORY_ONLY, ttl_seconds=300)
        
        # File only (persists but slower access)
        await cache_manager.set("persistent", "config_data", {"theme": "dark"}, 
                               strategy=CacheStrategy.FILE_ONLY, ttl_seconds=86400)
        
        # Both memory and file (best of both worlds)
        await cache_manager.set("hybrid", "user_preferences", {"language": "en"}, 
                               strategy=CacheStrategy.MEMORY_AND_FILE, ttl_seconds=3600)
        
        print("Set data with different cache strategies")
        
        # Example 7: Cache statistics and monitoring
        print("\n=== Cache Statistics ===")
        
        stats = await cache_manager.get_cache_stats()
        print(f"Memory entries: {stats['memory_entries']}")
        print(f"File entries: {stats['file_entries']}")
        print(f"Total cache size: {stats['total_size_mb']} MB")
        print(f"Namespaces: {list(stats['namespace_stats'].keys())}")
        
        # Example 8: Cache invalidation patterns
        print("\n=== Cache Invalidation ===")
        
        # Add some test data
        await cache_manager.set("users", "user:123:profile", {"name": "John"})
        await cache_manager.set("users", "user:123:settings", {"theme": "dark"})
        await cache_manager.set("users", "user:456:profile", {"name": "Jane"})
        
        # Invalidate all data for user 123
        invalidated = await cache_manager.invalidate_pattern("users:user:123:*")
        print(f"Invalidated {invalidated} entries for user 123")
        
        # Example 9: Namespace management
        print("\n=== Namespace Management ===")
        
        namespaces = await cache_manager.get_namespaces()
        print(f"Active namespaces: {namespaces}")
        
        # Clear a specific namespace
        cleared = await cache_manager.clear_namespace("temp")
        print(f"Cleared {cleared} entries from 'temp' namespace")
        
        # Example 10: Cleanup operations
        print("\n=== Cleanup Operations ===")
        
        # Manual cleanup of expired entries
        cleaned = await cache_manager.cleanup_expired()
        print(f"Cleaned up {cleaned} expired entries")
        
        # Final statistics
        final_stats = await cache_manager.get_cache_stats()
        print(f"Final cache state: {final_stats['memory_entries']} memory, {final_stats['file_entries']} file entries")
        
    finally:
        # Always shutdown the cache manager properly
        await cache_manager.shutdown()
        shutil.rmtree(temp_dir, ignore_errors=True)
        print("\nCache manager shutdown complete")


async def demonstrate_key_generation():
    """Demonstrate cache key generation strategies."""
    
    print("\n=== Cache Key Generation Examples ===")
    
    # Agent keys
    agent_key = CacheKeyGenerator.generate_agent_key("model_properties", "urn_123")
    print(f"Agent key: {agent_key}")
    
    # Index keys
    index_key = CacheKeyGenerator.generate_index_key("project_456", "version_789")
    print(f"Index key: {index_key}")
    
    # Properties keys with query hashing
    query = {"filter": "category=Walls", "limit": 100}
    query_hash = CacheKeyGenerator.hash_query(query)
    props_key = CacheKeyGenerator.generate_properties_key("urn_123", query_hash)
    print(f"Properties key: {props_key} (query hash: {query_hash})")
    
    # Database keys
    db_key = CacheKeyGenerator.generate_database_key("urn_456")
    print(f"Database key: {db_key}")
    
    # Vector keys
    vector_query = {"text": "find structural elements", "threshold": 0.8}
    vector_hash = CacheKeyGenerator.hash_query(vector_query)
    vector_key = CacheKeyGenerator.generate_vector_key("group_789", vector_hash)
    print(f"Vector key: {vector_key} (query hash: {vector_hash})")
    
    # Custom keys
    custom_key = CacheKeyGenerator.generate_custom_key("analytics", "user_123", "daily_report", "2024-01-01")
    print(f"Custom key: {custom_key}")


if __name__ == "__main__":
    print("Unified Cache Manager Usage Examples")
    print("=" * 50)
    
    # Run the demonstrations
    asyncio.run(demonstrate_key_generation())
    asyncio.run(demonstrate_cache_usage())