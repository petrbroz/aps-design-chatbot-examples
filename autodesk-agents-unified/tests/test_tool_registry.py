"""
Unit tests for the ToolRegistry system.
"""

import pytest
import asyncio
from datetime import datetime
from typing import Dict, Any
from unittest.mock import Mock, AsyncMock

from agent_core.tool_registry import (
    ToolRegistry, 
    ToolCategory, 
    ToolMetadata, 
    ToolRegistration
)
from agent_core.base_agent import BaseTool
from agent_core.models import ToolResult
from agent_core.logging import StructuredLogger


class MockTool(BaseTool):
    """Mock tool for testing."""
    
    def __init__(self, name: str, description: str, should_fail: bool = False):
        super().__init__(name, description)
        self.should_fail = should_fail
        self.initialized = False
        self.shutdown_called = False
        self.execute_count = 0
    
    async def initialize(self):
        """Mock initialization."""
        if self.should_fail:
            raise Exception("Initialization failed")
        self.initialized = True
    
    async def shutdown(self):
        """Mock shutdown."""
        self.shutdown_called = True
    
    async def execute(self, **kwargs) -> ToolResult:
        """Mock execution."""
        self.execute_count += 1
        if self.should_fail:
            raise Exception("Execution failed")
        
        return ToolResult(
            tool_name=self.name,
            success=True,
            result={"executed": True, "kwargs": kwargs}
        )
    
    def _get_parameters_schema(self) -> Dict[str, Any]:
        """Mock parameter schema."""
        return {
            "type": "object",
            "properties": {
                "test_param": {"type": "string", "description": "Test parameter"}
            }
        }


class TestToolRegistry:
    """Test cases for ToolRegistry."""
    
    @pytest.fixture
    def mock_logger(self):
        """Create a mock logger."""
        logger = Mock(spec=StructuredLogger)
        logger.info = Mock()
        logger.debug = Mock()
        logger.error = Mock()
        return logger
    
    @pytest.fixture
    def registry(self, mock_logger):
        """Create a ToolRegistry instance."""
        return ToolRegistry(logger=mock_logger)
    
    @pytest.fixture
    def sample_tool_class(self):
        """Create a sample tool class."""
        return MockTool
    
    def test_registry_initialization(self, mock_logger):
        """Test registry initialization."""
        registry = ToolRegistry(logger=mock_logger)
        
        assert registry.logger == mock_logger
        assert registry._tools == {}
        assert len(registry._categories) == len(ToolCategory)
        assert registry._agent_tools == {}
        assert registry._tool_dependencies == {}
        assert not registry._initialized
        
        mock_logger.info.assert_called_with("ToolRegistry initialized")
    
    def test_registry_initialization_without_logger(self):
        """Test registry initialization without logger."""
        registry = ToolRegistry()
        
        assert registry.logger is None
        assert registry._tools == {}
        assert not registry._initialized
    
    @pytest.mark.asyncio
    async def test_registry_async_initialization(self, registry, sample_tool_class):
        """Test async initialization of registry."""
        # Register a tool first
        registry.register_tool(
            tool_class=sample_tool_class,
            name="test_tool",
            description="Test tool",
            category=ToolCategory.GENERAL
        )
        
        # Get instance to trigger creation
        tool = registry.get_tool_instance("test_tool")
        
        await registry.initialize()
        
        assert registry._initialized
        assert tool.initialized
        registry.logger.info.assert_called()
    
    @pytest.mark.asyncio
    async def test_registry_shutdown(self, registry, sample_tool_class):
        """Test registry shutdown."""
        # Register and initialize
        registry.register_tool(
            tool_class=sample_tool_class,
            name="test_tool",
            description="Test tool",
            category=ToolCategory.GENERAL
        )
        
        tool = registry.get_tool_instance("test_tool")
        await registry.initialize()
        
        # Shutdown
        await registry.shutdown()
        
        assert not registry._initialized
        assert tool.shutdown_called
        registry.logger.info.assert_called()
    
    def test_register_tool_basic(self, registry, sample_tool_class):
        """Test basic tool registration."""
        registry.register_tool(
            tool_class=sample_tool_class,
            name="test_tool",
            description="Test tool description",
            category=ToolCategory.DATA_ACCESS
        )
        
        assert "test_tool" in registry._tools
        assert "test_tool" in registry._categories[ToolCategory.DATA_ACCESS]
        
        registration = registry._tools["test_tool"]
        assert registration.tool_class == sample_tool_class
        assert registration.metadata.name == "test_tool"
        assert registration.metadata.description == "Test tool description"
        assert registration.metadata.category == ToolCategory.DATA_ACCESS
        assert registration.metadata.enabled
        
        registry.logger.info.assert_called()
    
    def test_register_tool_with_all_options(self, registry, sample_tool_class):
        """Test tool registration with all options."""
        registry.register_tool(
            tool_class=sample_tool_class,
            name="advanced_tool",
            description="Advanced tool",
            category=ToolCategory.QUERY_EXECUTION,
            agent_types=["agent1", "agent2"],
            dependencies=["dep1", "dep2"],
            version="2.0.0",
            tags=["tag1", "tag2"],
            enabled=False
        )
        
        registration = registry._tools["advanced_tool"]
        metadata = registration.metadata
        
        assert metadata.agent_types == {"agent1", "agent2"}
        assert metadata.dependencies == ["dep1", "dep2"]
        assert metadata.version == "2.0.0"
        assert metadata.tags == {"tag1", "tag2"}
        assert not metadata.enabled
        
        # Check agent-tool mappings
        assert "advanced_tool" in registry._agent_tools["agent1"]
        assert "advanced_tool" in registry._agent_tools["agent2"]
        
        # Check dependency mappings
        assert registry._tool_dependencies["advanced_tool"] == {"dep1", "dep2"}
    
    def test_register_tool_validation(self, registry):
        """Test tool registration validation."""
        # Test empty name
        with pytest.raises(ValueError, match="Tool name cannot be empty"):
            registry.register_tool(
                tool_class=MockTool,
                name="",
                description="Test",
                category=ToolCategory.GENERAL
            )
        
        # Test duplicate name
        registry.register_tool(
            tool_class=MockTool,
            name="duplicate",
            description="Test",
            category=ToolCategory.GENERAL
        )
        
        with pytest.raises(ValueError, match="Tool 'duplicate' is already registered"):
            registry.register_tool(
                tool_class=MockTool,
                name="duplicate",
                description="Test",
                category=ToolCategory.GENERAL
            )
        
        # Test invalid tool class
        with pytest.raises(ValueError, match="tool_class must be a subclass of BaseTool"):
            registry.register_tool(
                tool_class=str,  # Invalid class
                name="invalid",
                description="Test",
                category=ToolCategory.GENERAL
            )
    
    def test_unregister_tool(self, registry, sample_tool_class):
        """Test tool unregistration."""
        # Register tool
        registry.register_tool(
            tool_class=sample_tool_class,
            name="test_tool",
            description="Test tool",
            category=ToolCategory.DATA_ACCESS,
            agent_types=["agent1"]
        )
        
        # Verify registration
        assert "test_tool" in registry._tools
        assert "test_tool" in registry._categories[ToolCategory.DATA_ACCESS]
        assert "test_tool" in registry._agent_tools["agent1"]
        
        # Unregister
        registry.unregister_tool("test_tool")
        
        # Verify removal
        assert "test_tool" not in registry._tools
        assert "test_tool" not in registry._categories[ToolCategory.DATA_ACCESS]
        assert "agent1" not in registry._agent_tools  # Should be removed when empty
        
        registry.logger.info.assert_called()
    
    def test_unregister_nonexistent_tool(self, registry):
        """Test unregistering a non-existent tool."""
        with pytest.raises(ValueError, match="Tool 'nonexistent' is not registered"):
            registry.unregister_tool("nonexistent")
    
    def test_get_tool_instance(self, registry, sample_tool_class):
        """Test getting tool instances."""
        registry.register_tool(
            tool_class=sample_tool_class,
            name="test_tool",
            description="Test tool",
            category=ToolCategory.GENERAL
        )
        
        # Get instance
        tool = registry.get_tool_instance("test_tool")
        
        assert isinstance(tool, MockTool)
        assert tool.name == "test_tool"
        assert tool.description == "Test tool"
        
        # Check usage tracking
        metadata = registry.get_tool_metadata("test_tool")
        assert metadata.usage_count == 1
        assert metadata.last_used is not None
        
        # Get same instance again (should be cached)
        tool2 = registry.get_tool_instance("test_tool")
        assert tool2 is tool
        
        # Check usage tracking updated
        metadata = registry.get_tool_metadata("test_tool")
        assert metadata.usage_count == 2
    
    def test_get_tool_instance_with_init_kwargs(self, registry, sample_tool_class):
        """Test getting tool instance with initialization kwargs."""
        registry.register_tool(
            tool_class=sample_tool_class,
            name="test_tool",
            description="Test tool",
            category=ToolCategory.GENERAL
        )
        
        # Get instance with kwargs (should create new instance)
        tool = registry.get_tool_instance("test_tool", should_fail=True)
        
        assert isinstance(tool, MockTool)
        assert tool.should_fail
    
    def test_get_tool_instance_validation(self, registry, sample_tool_class):
        """Test tool instance validation."""
        # Test non-existent tool
        with pytest.raises(ValueError, match="Tool 'nonexistent' is not registered"):
            registry.get_tool_instance("nonexistent")
        
        # Test disabled tool
        registry.register_tool(
            tool_class=sample_tool_class,
            name="disabled_tool",
            description="Disabled tool",
            category=ToolCategory.GENERAL,
            enabled=False
        )
        
        with pytest.raises(ValueError, match="Tool 'disabled_tool' is disabled"):
            registry.get_tool_instance("disabled_tool")
    
    def test_get_tools_for_agent(self, registry, sample_tool_class):
        """Test getting tools for specific agent."""
        # Register tools for different agents
        registry.register_tool(
            tool_class=sample_tool_class,
            name="tool1",
            description="Tool 1",
            category=ToolCategory.GENERAL,
            agent_types=["agent1", "agent2"]
        )
        
        registry.register_tool(
            tool_class=sample_tool_class,
            name="tool2",
            description="Tool 2",
            category=ToolCategory.GENERAL,
            agent_types=["agent2"]
        )
        
        registry.register_tool(
            tool_class=sample_tool_class,
            name="tool3",
            description="Tool 3",
            category=ToolCategory.GENERAL,
            agent_types=["agent3"]
        )
        
        # Get tools for agent1
        agent1_tools = registry.get_tools_for_agent("agent1")
        assert len(agent1_tools) == 1
        assert agent1_tools[0].name == "tool1"
        
        # Get tools for agent2
        agent2_tools = registry.get_tools_for_agent("agent2")
        assert len(agent2_tools) == 2
        tool_names = {tool.name for tool in agent2_tools}
        assert tool_names == {"tool1", "tool2"}
        
        # Get tools for non-existent agent
        nonexistent_tools = registry.get_tools_for_agent("nonexistent")
        assert len(nonexistent_tools) == 0
    
    def test_get_tools_by_category(self, registry, sample_tool_class):
        """Test getting tools by category."""
        # Register tools in different categories
        registry.register_tool(
            tool_class=sample_tool_class,
            name="data_tool1",
            description="Data tool 1",
            category=ToolCategory.DATA_ACCESS
        )
        
        registry.register_tool(
            tool_class=sample_tool_class,
            name="data_tool2",
            description="Data tool 2",
            category=ToolCategory.DATA_ACCESS
        )
        
        registry.register_tool(
            tool_class=sample_tool_class,
            name="query_tool",
            description="Query tool",
            category=ToolCategory.QUERY_EXECUTION
        )
        
        # Test category filtering
        data_tools = registry.get_tools_by_category(ToolCategory.DATA_ACCESS)
        assert set(data_tools) == {"data_tool1", "data_tool2"}
        
        query_tools = registry.get_tools_by_category(ToolCategory.QUERY_EXECUTION)
        assert query_tools == ["query_tool"]
        
        empty_category = registry.get_tools_by_category(ToolCategory.AUTHENTICATION)
        assert empty_category == []
    
    def test_get_tools_by_tags(self, registry, sample_tool_class):
        """Test getting tools by tags."""
        # Register tools with different tags
        registry.register_tool(
            tool_class=sample_tool_class,
            name="tool1",
            description="Tool 1",
            category=ToolCategory.GENERAL,
            tags=["tag1", "tag2"]
        )
        
        registry.register_tool(
            tool_class=sample_tool_class,
            name="tool2",
            description="Tool 2",
            category=ToolCategory.GENERAL,
            tags=["tag2", "tag3"]
        )
        
        registry.register_tool(
            tool_class=sample_tool_class,
            name="tool3",
            description="Tool 3",
            category=ToolCategory.GENERAL,
            tags=["tag4"]
        )
        
        # Test tag filtering
        tag1_tools = registry.get_tools_by_tags(["tag1"])
        assert tag1_tools == ["tool1"]
        
        tag2_tools = registry.get_tools_by_tags(["tag2"])
        assert set(tag2_tools) == {"tool1", "tool2"}
        
        multi_tag_tools = registry.get_tools_by_tags(["tag1", "tag3"])
        assert set(multi_tag_tools) == {"tool1", "tool2"}
        
        no_match_tools = registry.get_tools_by_tags(["nonexistent"])
        assert no_match_tools == []
    
    def test_search_tools(self, registry, sample_tool_class):
        """Test tool search functionality."""
        # Register tools with various properties
        registry.register_tool(
            tool_class=sample_tool_class,
            name="data_processor",
            description="Process data files",
            category=ToolCategory.DATA_ACCESS,
            agent_types=["agent1"],
            tags=["processing"]
        )
        
        registry.register_tool(
            tool_class=sample_tool_class,
            name="query_executor",
            description="Execute database queries",
            category=ToolCategory.QUERY_EXECUTION,
            agent_types=["agent2"],
            tags=["database"]
        )
        
        registry.register_tool(
            tool_class=sample_tool_class,
            name="file_reader",
            description="Read various file formats",
            category=ToolCategory.FILE_OPERATIONS,
            agent_types=["agent1"],
            tags=["processing", "files"]
        )
        
        # Test query search
        query_results = registry.search_tools("data")
        assert set(query_results) == {"data_processor", "query_executor"}
        
        # Test category filter
        data_category_results = registry.search_tools("", category=ToolCategory.DATA_ACCESS)
        assert data_category_results == ["data_processor"]
        
        # Test agent type filter
        agent1_results = registry.search_tools("", agent_type="agent1")
        assert set(agent1_results) == {"data_processor", "file_reader"}
        
        # Test tags filter
        processing_results = registry.search_tools("", tags=["processing"])
        assert set(processing_results) == {"data_processor", "file_reader"}
        
        # Test combined filters
        combined_results = registry.search_tools(
            "file",
            category=ToolCategory.FILE_OPERATIONS,
            agent_type="agent1",
            tags=["files"]
        )
        assert combined_results == ["file_reader"]
    
    def test_tool_metadata_operations(self, registry, sample_tool_class):
        """Test tool metadata operations."""
        registry.register_tool(
            tool_class=sample_tool_class,
            name="test_tool",
            description="Test tool",
            category=ToolCategory.GENERAL,
            dependencies=["dep1", "dep2"]
        )
        
        # Test get metadata
        metadata = registry.get_tool_metadata("test_tool")
        assert isinstance(metadata, ToolMetadata)
        assert metadata.name == "test_tool"
        assert metadata.description == "Test tool"
        assert metadata.category == ToolCategory.GENERAL
        
        # Test get dependencies
        dependencies = registry.get_tool_dependencies("test_tool")
        assert set(dependencies) == {"dep1", "dep2"}
        
        # Test non-existent tool
        with pytest.raises(ValueError, match="Tool 'nonexistent' is not registered"):
            registry.get_tool_metadata("nonexistent")
    
    def test_dependency_validation(self, registry, sample_tool_class):
        """Test dependency validation."""
        # Register dependency tools
        registry.register_tool(
            tool_class=sample_tool_class,
            name="dep1",
            description="Dependency 1",
            category=ToolCategory.GENERAL
        )
        
        registry.register_tool(
            tool_class=sample_tool_class,
            name="dep2",
            description="Dependency 2",
            category=ToolCategory.GENERAL,
            enabled=False  # Disabled dependency
        )
        
        # Register tool with dependencies
        registry.register_tool(
            tool_class=sample_tool_class,
            name="main_tool",
            description="Main tool",
            category=ToolCategory.GENERAL,
            dependencies=["dep1", "dep2", "missing_dep"]
        )
        
        # Test validation
        assert not registry.validate_dependencies("main_tool")  # Should fail due to missing and disabled deps
        
        # Enable dep2
        registry.enable_tool("dep2")
        assert not registry.validate_dependencies("main_tool")  # Still fails due to missing dep
        
        # Register missing dependency
        registry.register_tool(
            tool_class=sample_tool_class,
            name="missing_dep",
            description="Missing dependency",
            category=ToolCategory.GENERAL
        )
        
        assert registry.validate_dependencies("main_tool")  # Should now pass
        
        # Test tool without dependencies
        assert registry.validate_dependencies("dep1")  # Should pass
    
    def test_tool_enable_disable(self, registry, sample_tool_class):
        """Test tool enable/disable functionality."""
        registry.register_tool(
            tool_class=sample_tool_class,
            name="test_tool",
            description="Test tool",
            category=ToolCategory.GENERAL,
            enabled=True
        )
        
        # Test initial state
        assert registry.is_tool_enabled("test_tool")
        
        # Test disable
        registry.disable_tool("test_tool")
        assert not registry.is_tool_enabled("test_tool")
        registry.logger.info.assert_called()
        
        # Test enable
        registry.enable_tool("test_tool")
        assert registry.is_tool_enabled("test_tool")
        registry.logger.info.assert_called()
        
        # Test non-existent tool
        with pytest.raises(ValueError, match="Tool 'nonexistent' is not registered"):
            registry.enable_tool("nonexistent")
        
        with pytest.raises(ValueError, match="Tool 'nonexistent' is not registered"):
            registry.disable_tool("nonexistent")
        
        assert not registry.is_tool_enabled("nonexistent")
    
    def test_registry_stats(self, registry, sample_tool_class):
        """Test registry statistics."""
        # Register various tools
        registry.register_tool(
            tool_class=sample_tool_class,
            name="tool1",
            description="Tool 1",
            category=ToolCategory.DATA_ACCESS,
            agent_types=["agent1"]
        )
        
        registry.register_tool(
            tool_class=sample_tool_class,
            name="tool2",
            description="Tool 2",
            category=ToolCategory.DATA_ACCESS,
            agent_types=["agent1", "agent2"],
            enabled=False
        )
        
        registry.register_tool(
            tool_class=sample_tool_class,
            name="tool3",
            description="Tool 3",
            category=ToolCategory.QUERY_EXECUTION,
            agent_types=["agent2"]
        )
        
        # Use some tools to generate usage stats
        registry.get_tool_instance("tool1")
        registry.get_tool_instance("tool3")
        registry.get_tool_instance("tool3")  # Use twice
        
        stats = registry.get_registry_stats()
        
        assert stats["total_tools"] == 3
        assert stats["enabled_tools"] == 2
        assert stats["disabled_tools"] == 1
        assert stats["category_counts"][ToolCategory.DATA_ACCESS.value] == 2
        assert stats["category_counts"][ToolCategory.QUERY_EXECUTION.value] == 1
        assert stats["agent_tool_counts"]["agent1"] == 2
        assert stats["agent_tool_counts"]["agent2"] == 2
        assert stats["total_usage"] == 3
        assert not stats["initialized"]  # Not async initialized yet
    
    def test_list_all_tools(self, registry, sample_tool_class):
        """Test listing all tools."""
        # Register a tool
        registry.register_tool(
            tool_class=sample_tool_class,
            name="test_tool",
            description="Test tool",
            category=ToolCategory.GENERAL,
            agent_types=["agent1"],
            dependencies=["dep1"],
            version="2.0.0",
            tags=["test"],
            enabled=False
        )
        
        # Use the tool to generate usage stats
        registry.enable_tool("test_tool")
        registry.get_tool_instance("test_tool")
        
        tools_list = registry.list_all_tools()
        
        assert len(tools_list) == 1
        tool_info = tools_list[0]
        
        assert tool_info["name"] == "test_tool"
        assert tool_info["description"] == "Test tool"
        assert tool_info["category"] == ToolCategory.GENERAL.value
        assert tool_info["agent_types"] == ["agent1"]
        assert tool_info["dependencies"] == ["dep1"]
        assert tool_info["version"] == "2.0.0"
        assert tool_info["tags"] == ["test"]
        assert tool_info["enabled"]
        assert tool_info["usage_count"] == 1
        assert tool_info["last_used"] is not None
        assert tool_info["created_at"] is not None


class TestToolRegistryIntegration:
    """Integration tests for ToolRegistry with real scenarios."""
    
    @pytest.mark.asyncio
    async def test_full_lifecycle(self):
        """Test complete tool registry lifecycle."""
        registry = ToolRegistry()
        
        # Register tools
        registry.register_tool(
            tool_class=MockTool,
            name="data_tool",
            description="Data processing tool",
            category=ToolCategory.DATA_ACCESS,
            agent_types=["data_agent"],
            tags=["processing"]
        )
        
        registry.register_tool(
            tool_class=MockTool,
            name="query_tool",
            description="Query execution tool",
            category=ToolCategory.QUERY_EXECUTION,
            agent_types=["query_agent"],
            dependencies=["data_tool"]
        )
        
        # Initialize registry
        await registry.initialize()
        assert registry._initialized
        
        # Get tools for agents
        data_tools = registry.get_tools_for_agent("data_agent")
        assert len(data_tools) == 1
        assert data_tools[0].name == "data_tool"
        
        query_tools = registry.get_tools_for_agent("query_agent")
        assert len(query_tools) == 1
        assert query_tools[0].name == "query_tool"
        
        # Validate dependencies
        assert registry.validate_dependencies("query_tool")
        
        # Execute tools
        data_tool = data_tools[0]
        result = await data_tool.execute(test_param="test_value")
        assert result.success
        assert result.result["executed"]
        
        # Check stats
        stats = registry.get_registry_stats()
        assert stats["total_tools"] == 2
        assert stats["enabled_tools"] == 2
        assert stats["total_usage"] >= 2  # At least 2 from get_tools_for_agent calls
        
        # Shutdown
        await registry.shutdown()
        assert not registry._initialized
    
    @pytest.mark.asyncio
    async def test_error_handling_during_initialization(self):
        """Test error handling during tool initialization."""
        logger = Mock(spec=StructuredLogger)
        logger.info = Mock()
        logger.debug = Mock()
        logger.error = Mock()
        
        registry = ToolRegistry(logger=logger)
        
        # Register a tool that will fail initialization
        registry.register_tool(
            tool_class=MockTool,
            name="failing_tool",
            description="Tool that fails initialization",
            category=ToolCategory.GENERAL
        )
        
        # Get instance with failure flag
        tool = registry.get_tool_instance("failing_tool", should_fail=True)
        
        # Initialize should handle the error gracefully
        await registry.initialize()
        
        # Should still be initialized despite tool failure
        assert registry._initialized
        logger.error.assert_called()
    
    def test_concurrent_tool_access(self):
        """Test concurrent access to tools."""
        registry = ToolRegistry()
        registry.register_tool(
            tool_class=MockTool,
            name="concurrent_tool",
            description="Tool for concurrent access",
            category=ToolCategory.GENERAL
        )
        
        # Get multiple instances concurrently (should return same cached instance)
        tool1 = registry.get_tool_instance("concurrent_tool")
        tool2 = registry.get_tool_instance("concurrent_tool")
        tool3 = registry.get_tool_instance("concurrent_tool")
        
        assert tool1 is tool2 is tool3
        
        # Check usage count
        metadata = registry.get_tool_metadata("concurrent_tool")
        assert metadata.usage_count == 3