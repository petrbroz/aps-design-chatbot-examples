"""
Tests for Model Properties tool registry integration.
"""

import pytest
from agent_core.tool_registry import ToolRegistry, ToolCategory
from agent_core.tools.registry_setup import register_model_properties_tools
from agent_core.tools.model_properties import (
    CreateIndexTool,
    ListIndexPropertiesTool,
    QueryIndexTool,
    ExecuteJQQueryTool
)


class TestModelPropertiesRegistry:
    """Test cases for Model Properties tool registry integration."""
    
    @pytest.fixture
    def registry(self):
        """Create a test registry."""
        return ToolRegistry()
    
    def test_register_model_properties_tools(self, registry):
        """Test registering all Model Properties tools."""
        register_model_properties_tools(registry)
        
        # Check that all tools are registered
        stats = registry.get_registry_stats()
        assert stats["total_tools"] == 4
        assert stats["enabled_tools"] == 4
        
        # Check specific tools
        assert registry.is_tool_enabled("create_index")
        assert registry.is_tool_enabled("list_index_properties")
        assert registry.is_tool_enabled("query_index")
        assert registry.is_tool_enabled("execute_jq_query")
    
    def test_tool_categories(self, registry):
        """Test that tools are assigned to correct categories."""
        register_model_properties_tools(registry)
        
        # Check categories
        data_access_tools = registry.get_tools_by_category(ToolCategory.DATA_ACCESS)
        query_tools = registry.get_tools_by_category(ToolCategory.QUERY_EXECUTION)
        transform_tools = registry.get_tools_by_category(ToolCategory.TRANSFORMATION)
        
        assert "create_index" in data_access_tools
        assert "list_index_properties" in data_access_tools
        assert "query_index" in query_tools
        assert "execute_jq_query" in transform_tools
    
    def test_agent_type_assignment(self, registry):
        """Test that tools are assigned to correct agent types."""
        register_model_properties_tools(registry)
        
        # Get tools for model_properties agent
        mp_tools = registry.get_tools_for_agent("model_properties")
        mp_tool_names = [tool.name for tool in mp_tools]
        
        assert "create_index" in mp_tool_names
        assert "list_index_properties" in mp_tool_names
        assert "query_index" in mp_tool_names
        assert "execute_jq_query" in mp_tool_names
        
        # Check that execute_jq_query is also available to other agents
        aec_tools = registry.get_tools_for_agent("aec_data_model")
        aec_tool_names = [tool.name for tool in aec_tools]
        assert "execute_jq_query" in aec_tool_names
        
        deriv_tools = registry.get_tools_for_agent("model_derivatives")
        deriv_tool_names = [tool.name for tool in deriv_tools]
        assert "execute_jq_query" in deriv_tool_names
    
    def test_tool_dependencies(self, registry):
        """Test that tool dependencies are correctly set."""
        register_model_properties_tools(registry)
        
        # Check dependencies
        list_deps = registry.get_tool_dependencies("list_index_properties")
        query_deps = registry.get_tool_dependencies("query_index")
        jq_deps = registry.get_tool_dependencies("execute_jq_query")
        create_deps = registry.get_tool_dependencies("create_index")
        
        assert "create_index" in list_deps
        assert "create_index" in query_deps
        assert len(jq_deps) == 0  # No dependencies
        assert len(create_deps) == 0  # No dependencies
    
    def test_tool_metadata(self, registry):
        """Test that tool metadata is correctly set."""
        register_model_properties_tools(registry)
        
        # Check create_index metadata
        create_meta = registry.get_tool_metadata("create_index")
        assert create_meta.name == "create_index"
        assert "Model Properties index" in create_meta.description
        assert create_meta.category == ToolCategory.DATA_ACCESS
        assert "model_properties" in create_meta.agent_types
        assert "autodesk" in create_meta.tags
        assert "construction" in create_meta.tags
        
        # Check execute_jq_query metadata
        jq_meta = registry.get_tool_metadata("execute_jq_query")
        assert jq_meta.name == "execute_jq_query"
        assert "jq query" in jq_meta.description
        assert jq_meta.category == ToolCategory.TRANSFORMATION
        assert len(jq_meta.agent_types) == 3  # Available to 3 agent types
        assert "json" in jq_meta.tags
        assert "jq" in jq_meta.tags
    
    def test_tool_instances(self, registry):
        """Test that tool instances can be created."""
        register_model_properties_tools(registry)
        
        # Test creating instances
        create_tool = registry.get_tool_instance("create_index")
        assert isinstance(create_tool, CreateIndexTool)
        assert create_tool.name == "create_index"
        
        list_tool = registry.get_tool_instance("list_index_properties")
        assert isinstance(list_tool, ListIndexPropertiesTool)
        assert list_tool.name == "list_index_properties"
        
        query_tool = registry.get_tool_instance("query_index")
        assert isinstance(query_tool, QueryIndexTool)
        assert query_tool.name == "query_index"
        
        jq_tool = registry.get_tool_instance("execute_jq_query")
        assert isinstance(jq_tool, ExecuteJQQueryTool)
        assert jq_tool.name == "execute_jq_query"
    
    def test_tool_search(self, registry):
        """Test searching for tools."""
        register_model_properties_tools(registry)
        
        # Search by query
        index_tools = registry.search_tools("index")
        assert "create_index" in index_tools
        assert "list_index_properties" in index_tools
        assert "query_index" in index_tools
        
        # Search by category
        data_tools = registry.search_tools("", category=ToolCategory.DATA_ACCESS)
        assert "create_index" in data_tools
        assert "list_index_properties" in data_tools
        
        # Search by agent type
        mp_tools = registry.search_tools("", agent_type="model_properties")
        assert len(mp_tools) == 4
        
        # Search by tags
        autodesk_tools = registry.search_tools("", tags=["autodesk"])
        assert "create_index" in autodesk_tools
        assert "list_index_properties" in autodesk_tools
        assert "query_index" in autodesk_tools
    
    def test_dependency_validation(self, registry):
        """Test dependency validation."""
        register_model_properties_tools(registry)
        
        # All dependencies should be satisfied
        assert registry.validate_dependencies("create_index")
        assert registry.validate_dependencies("list_index_properties")
        assert registry.validate_dependencies("query_index")
        assert registry.validate_dependencies("execute_jq_query")
        
        # Test with missing dependency
        registry.disable_tool("create_index")
        assert not registry.validate_dependencies("list_index_properties")
        assert not registry.validate_dependencies("query_index")
        
        # Re-enable and check again
        registry.enable_tool("create_index")
        assert registry.validate_dependencies("list_index_properties")
        assert registry.validate_dependencies("query_index")


if __name__ == "__main__":
    pytest.main([__file__])