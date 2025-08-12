"""
Integration tests for ToolRegistry with AgentCore.
"""

import pytest
import asyncio
from typing import Dict, Any

from agent_core import (
    AgentCore, BaseAgent, BaseTool, ToolRegistry, ToolCategory,
    AgentRequest, AgentResponse, ToolResult
)


class SampleTool(BaseTool):
    """Sample tool for integration testing."""
    
    def __init__(self, name: str, description: str):
        super().__init__(name, description)
        self.execution_count = 0
    
    async def execute(self, **kwargs) -> ToolResult:
        """Execute the sample tool."""
        self.execution_count += 1
        return ToolResult(
            tool_name=self.name,
            success=True,
            result={"message": f"Tool {self.name} executed", "kwargs": kwargs},
            execution_time=0.1
        )
    
    def _get_parameters_schema(self) -> Dict[str, Any]:
        """Get parameter schema."""
        return {
            "type": "object",
            "properties": {
                "input_data": {"type": "string", "description": "Input data for processing"}
            }
        }


class SampleAgent(BaseAgent):
    """Sample agent for integration testing."""
    
    async def process_prompt(self, request: AgentRequest) -> AgentResponse:
        """Process a prompt using available tools."""
        responses = [f"Processing prompt: {request.prompt}"]
        
        # Use a tool if available
        if self.has_tool("data_processor"):
            tool_result = await self.execute_tool("data_processor", input_data=request.prompt)
            if tool_result.success:
                responses.append(f"Tool result: {tool_result.result}")
        
        return AgentResponse(
            responses=responses,
            agent_type=self.get_agent_type(),
            request_id=request.request_id
        )
    
    def get_agent_type(self) -> str:
        """Return agent type."""
        return "sample_agent"


class TestToolRegistryIntegration:
    """Integration tests for ToolRegistry with AgentCore."""
    
    @pytest.mark.asyncio
    async def test_tool_registry_with_agent_core(self):
        """Test ToolRegistry integration with AgentCore and agents."""
        # Create AgentCore instance
        agent_core = AgentCore()
        await agent_core.initialize()
        
        try:
            # Register tools in the registry
            agent_core.tool_registry.register_tool(
                tool_class=SampleTool,
                name="data_processor",
                description="Process data inputs",
                category=ToolCategory.DATA_ACCESS,
                agent_types=["sample_agent"],
                tags=["processing", "data"]
            )
            
            agent_core.tool_registry.register_tool(
                tool_class=SampleTool,
                name="query_executor",
                description="Execute queries",
                category=ToolCategory.QUERY_EXECUTION,
                agent_types=["sample_agent"],
                tags=["query", "execution"]
            )
            
            # Verify tools are registered
            assert agent_core.tool_registry.is_tool_enabled("data_processor")
            assert agent_core.tool_registry.is_tool_enabled("query_executor")
            
            # Create agent (should get tools from registry)
            agent = SampleAgent(agent_core)
            await agent.initialize()
            
            # Verify agent has tools from registry
            assert len(agent.tools) == 2
            tool_names = {tool.name for tool in agent.tools}
            assert tool_names == {"data_processor", "query_executor"}
            
            # Test agent functionality
            request = AgentRequest(
                agent_type="sample_agent",
                prompt="Test input data"
            )
            
            # Disable authentication for testing
            agent_core.auth_manager.enabled = False
            
            response = await agent.handle_request(request)
            
            assert response.success
            assert len(response.responses) == 2  # Original response + tool result
            assert "Processing prompt: Test input data" in response.responses[0]
            assert "Tool result:" in response.responses[1]
            
            # Verify tool was executed
            data_processor = agent_core.tool_registry.get_tool_instance("data_processor")
            assert data_processor.execution_count == 1
            
            # Test registry stats
            stats = agent_core.tool_registry.get_registry_stats()
            assert stats["total_tools"] == 2
            assert stats["enabled_tools"] == 2
            assert stats["total_usage"] >= 2  # At least 2 from agent initialization and execution
            
        finally:
            await agent_core.shutdown()
    
    @pytest.mark.asyncio
    async def test_tool_discovery_and_categorization(self):
        """Test tool discovery and categorization features."""
        agent_core = AgentCore()
        await agent_core.initialize()
        
        try:
            # Register tools in different categories
            agent_core.tool_registry.register_tool(
                tool_class=SampleTool,
                name="file_reader",
                description="Read files from disk",
                category=ToolCategory.FILE_OPERATIONS,
                agent_types=["file_agent"],
                tags=["file", "read"]
            )
            
            agent_core.tool_registry.register_tool(
                tool_class=SampleTool,
                name="data_transformer",
                description="Transform data formats",
                category=ToolCategory.TRANSFORMATION,
                agent_types=["data_agent"],
                tags=["transform", "data"]
            )
            
            agent_core.tool_registry.register_tool(
                tool_class=SampleTool,
                name="cache_manager",
                description="Manage cached data",
                category=ToolCategory.CACHING,
                agent_types=["cache_agent"],
                tags=["cache", "storage"]
            )
            
            # Test category-based discovery
            file_tools = agent_core.tool_registry.get_tools_by_category(ToolCategory.FILE_OPERATIONS)
            assert file_tools == ["file_reader"]
            
            transform_tools = agent_core.tool_registry.get_tools_by_category(ToolCategory.TRANSFORMATION)
            assert transform_tools == ["data_transformer"]
            
            # Test tag-based discovery
            data_tools = agent_core.tool_registry.get_tools_by_tags(["data"])
            assert set(data_tools) == {"data_transformer"}
            
            # Test search functionality
            file_search = agent_core.tool_registry.search_tools("file")
            assert "file_reader" in file_search
            
            cache_search = agent_core.tool_registry.search_tools(
                "cache",
                category=ToolCategory.CACHING
            )
            assert cache_search == ["cache_manager"]
            
            # Test agent-specific tool assignment
            file_agent_tools = agent_core.tool_registry.get_tools_for_agent("file_agent")
            assert len(file_agent_tools) == 1
            assert file_agent_tools[0].name == "file_reader"
            
            data_agent_tools = agent_core.tool_registry.get_tools_for_agent("data_agent")
            assert len(data_agent_tools) == 1
            assert data_agent_tools[0].name == "data_transformer"
            
        finally:
            await agent_core.shutdown()
    
    @pytest.mark.asyncio
    async def test_tool_dependency_management(self):
        """Test tool dependency validation and management."""
        agent_core = AgentCore()
        await agent_core.initialize()
        
        try:
            # Register dependency tools
            agent_core.tool_registry.register_tool(
                tool_class=SampleTool,
                name="auth_tool",
                description="Handle authentication",
                category=ToolCategory.AUTHENTICATION,
                agent_types=["secure_agent"]
            )
            
            agent_core.tool_registry.register_tool(
                tool_class=SampleTool,
                name="validator",
                description="Validate inputs",
                category=ToolCategory.VALIDATION,
                agent_types=["secure_agent"]
            )
            
            # Register tool with dependencies
            agent_core.tool_registry.register_tool(
                tool_class=SampleTool,
                name="secure_processor",
                description="Process data securely",
                category=ToolCategory.DATA_ACCESS,
                agent_types=["secure_agent"],
                dependencies=["auth_tool", "validator"]
            )
            
            # Test dependency validation
            assert agent_core.tool_registry.validate_dependencies("secure_processor")
            assert agent_core.tool_registry.validate_dependencies("auth_tool")  # No deps
            
            # Test dependency retrieval
            deps = agent_core.tool_registry.get_tool_dependencies("secure_processor")
            assert set(deps) == {"auth_tool", "validator"}
            
            # Test with missing dependency
            agent_core.tool_registry.register_tool(
                tool_class=SampleTool,
                name="broken_tool",
                description="Tool with missing dependency",
                category=ToolCategory.GENERAL,
                agent_types=["test_agent"],
                dependencies=["missing_tool"]
            )
            
            assert not agent_core.tool_registry.validate_dependencies("broken_tool")
            
        finally:
            await agent_core.shutdown()
    
    @pytest.mark.asyncio
    async def test_tool_enable_disable_functionality(self):
        """Test tool enable/disable functionality."""
        agent_core = AgentCore()
        await agent_core.initialize()
        
        try:
            # Register tool
            agent_core.tool_registry.register_tool(
                tool_class=SampleTool,
                name="toggleable_tool",
                description="Tool that can be toggled",
                category=ToolCategory.GENERAL,
                agent_types=["test_agent"]
            )
            
            # Test initial state (enabled)
            assert agent_core.tool_registry.is_tool_enabled("toggleable_tool")
            
            # Test getting instance when enabled
            tool = agent_core.tool_registry.get_tool_instance("toggleable_tool")
            assert tool is not None
            
            # Disable tool
            agent_core.tool_registry.disable_tool("toggleable_tool")
            assert not agent_core.tool_registry.is_tool_enabled("toggleable_tool")
            
            # Test getting instance when disabled (should fail)
            with pytest.raises(ValueError, match="Tool 'toggleable_tool' is disabled"):
                agent_core.tool_registry.get_tool_instance("toggleable_tool")
            
            # Re-enable tool
            agent_core.tool_registry.enable_tool("toggleable_tool")
            assert agent_core.tool_registry.is_tool_enabled("toggleable_tool")
            
            # Should work again
            tool = agent_core.tool_registry.get_tool_instance("toggleable_tool")
            assert tool is not None
            
        finally:
            await agent_core.shutdown()
    
    @pytest.mark.asyncio
    async def test_system_info_includes_tool_registry(self):
        """Test that system info includes tool registry statistics."""
        agent_core = AgentCore()
        await agent_core.initialize()
        
        try:
            # Register some tools
            agent_core.tool_registry.register_tool(
                tool_class=SampleTool,
                name="info_tool1",
                description="Tool for info test",
                category=ToolCategory.GENERAL,
                agent_types=["info_agent"]
            )
            
            agent_core.tool_registry.register_tool(
                tool_class=SampleTool,
                name="info_tool2",
                description="Another tool for info test",
                category=ToolCategory.DATA_ACCESS,
                agent_types=["info_agent"],
                enabled=False
            )
            
            # Get system info
            system_info = await agent_core.get_system_info()
            
            # Verify tool registry stats are included
            assert "tool_registry_stats" in system_info
            tool_stats = system_info["tool_registry_stats"]
            
            assert tool_stats["total_tools"] == 2
            assert tool_stats["enabled_tools"] == 1
            assert tool_stats["disabled_tools"] == 1
            assert tool_stats["initialized"] == True
            
            # Verify category counts
            assert tool_stats["category_counts"]["general"] == 1
            assert tool_stats["category_counts"]["data_access"] == 1
            
            # Verify agent tool counts
            assert tool_stats["agent_tool_counts"]["info_agent"] == 2
            
        finally:
            await agent_core.shutdown()