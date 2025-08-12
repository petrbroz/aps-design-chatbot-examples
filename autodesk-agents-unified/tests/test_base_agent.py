"""
Unit tests for BaseAgent and BaseTool classes.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

from agent_core.base_agent import BaseAgent, BaseTool
from agent_core.models import (
    AgentRequest, AgentResponse, ToolResult, AgentMetrics, ErrorCode
)
from agent_core.auth import AuthContext


class MockTool(BaseTool):
    """Mock tool for testing."""
    
    def __init__(self, name: str = "mock_tool", description: str = "Mock tool for testing"):
        super().__init__(name, description)
        self.execute_called = False
        self.execute_kwargs = {}
    
    async def execute(self, **kwargs) -> ToolResult:
        """Mock execute method."""
        self.execute_called = True
        self.execute_kwargs = kwargs
        
        if kwargs.get("should_fail"):
            raise ValueError("Mock tool failure")
        
        return ToolResult(
            tool_name=self.name,
            success=True,
            result={"mock": "result"},
            execution_time=0.1
        )
    
    def _get_parameters_schema(self) -> dict:
        """Mock parameters schema."""
        return {
            "type": "object",
            "properties": {
                "param1": {"type": "string"},
                "should_fail": {"type": "boolean"}
            }
        }


class MockAgent(BaseAgent):
    """Mock agent for testing."""
    
    def __init__(self, agent_core, tools=None):
        super().__init__(agent_core, tools)
        self.process_prompt_called = False
        self.process_prompt_request = None
    
    async def process_prompt(self, request: AgentRequest) -> AgentResponse:
        """Mock process_prompt method."""
        self.process_prompt_called = True
        self.process_prompt_request = request
        
        if "error" in request.prompt.lower():
            raise ValueError("Mock agent error")
        
        return AgentResponse(
            responses=[f"Mock response to: {request.prompt}"],
            agent_type=self.get_agent_type(),
            request_id=request.request_id
        )
    
    def get_agent_type(self) -> str:
        """Return mock agent type."""
        return "mock_agent"


class TestBaseTool:
    """Test cases for BaseTool class."""
    
    def test_tool_initialization(self):
        """Test BaseTool initialization."""
        tool = MockTool("test_tool", "Test tool description")
        
        assert tool.name == "test_tool"
        assert tool.description == "Test tool description"
    
    def test_get_schema(self):
        """Test tool schema generation."""
        tool = MockTool("test_tool", "Test tool description")
        schema = tool.get_schema()
        
        assert schema["name"] == "test_tool"
        assert schema["description"] == "Test tool description"
        assert "parameters" in schema
        assert schema["parameters"]["type"] == "object"
    
    @pytest.mark.asyncio
    async def test_tool_execute_success(self):
        """Test successful tool execution."""
        tool = MockTool()
        result = await tool.execute(param1="test_value")
        
        assert tool.execute_called
        assert tool.execute_kwargs == {"param1": "test_value"}
        assert result.tool_name == "mock_tool"
        assert result.success is True
        assert result.result == {"mock": "result"}
    
    @pytest.mark.asyncio
    async def test_tool_execute_failure(self):
        """Test tool execution failure."""
        tool = MockTool()
        
        with pytest.raises(ValueError, match="Mock tool failure"):
            await tool.execute(should_fail=True)


class TestBaseAgent:
    """Test cases for BaseAgent class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_agent_core = Mock()
        self.mock_agent_core.logger = Mock()
        self.mock_agent_core.auth_manager = Mock()
        self.mock_agent_core.auth_manager.enabled = True
        self.mock_agent_core.is_healthy.return_value = True
        self.mock_agent_core.tool_registry = Mock()
        self.mock_agent_core.tool_registry.get_tools_for_agent.return_value = []
        
        self.mock_tool = MockTool()
        self.agent = MockAgent(self.mock_agent_core, [self.mock_tool])
    
    def test_agent_initialization(self):
        """Test BaseAgent initialization."""
        assert self.agent.agent_core == self.mock_agent_core
        assert len(self.agent.tools) == 1
        assert self.agent.tools[0] == self.mock_tool
        assert isinstance(self.agent.metrics, AgentMetrics)
        assert self.agent.metrics.agent_type == "mock_agent"
        assert not self.agent._initialized
        assert "mock_tool" in self.agent._tool_registry
    
    @pytest.mark.asyncio
    async def test_agent_initialize(self):
        """Test agent initialization."""
        await self.agent.initialize()
        
        assert self.agent._initialized
        self.mock_agent_core.logger.info.assert_called()
    
    @pytest.mark.asyncio
    async def test_agent_shutdown(self):
        """Test agent shutdown."""
        await self.agent.initialize()
        await self.agent.shutdown()
        
        assert not self.agent._initialized
        self.mock_agent_core.logger.info.assert_called()
    
    def test_get_agent_type(self):
        """Test get_agent_type method."""
        assert self.agent.get_agent_type() == "mock_agent"
    
    @pytest.mark.asyncio
    async def test_execute_tool_success(self):
        """Test successful tool execution."""
        result = await self.agent.execute_tool("mock_tool", param1="test")
        
        assert result.tool_name == "mock_tool"
        assert result.success is True
        assert result.result == {"mock": "result"}
        assert self.mock_tool.execute_called
    
    @pytest.mark.asyncio
    async def test_execute_tool_not_found(self):
        """Test tool execution with non-existent tool."""
        with pytest.raises(ValueError, match="Tool 'nonexistent' not found"):
            await self.agent.execute_tool("nonexistent")
    
    @pytest.mark.asyncio
    async def test_execute_tool_failure(self):
        """Test tool execution failure handling."""
        result = await self.agent.execute_tool("mock_tool", should_fail=True)
        
        assert result.tool_name == "mock_tool"
        assert result.success is False
        assert "Mock tool failure" in result.error
        assert result.execution_time > 0
    
    def test_get_available_tools(self):
        """Test getting available tools."""
        tools = self.agent.get_available_tools()
        
        assert len(tools) == 1
        assert tools[0]["name"] == "mock_tool"
        assert tools[0]["description"] == "Mock tool for testing"
    
    def test_has_tool(self):
        """Test checking if agent has a tool."""
        assert self.agent.has_tool("mock_tool")
        assert not self.agent.has_tool("nonexistent_tool")
    
    @pytest.mark.asyncio
    async def test_validate_request_success(self):
        """Test successful request validation."""
        auth_context = AuthContext(access_token="test_token")
        request = AgentRequest(
            agent_type="mock_agent",
            prompt="Test prompt",
            authentication=auth_context
        )
        
        # Should not raise any exception
        await self.agent.validate_request(request)
    
    @pytest.mark.asyncio
    async def test_validate_request_missing_agent_type(self):
        """Test request validation with missing agent_type."""
        with pytest.raises(ValueError, match="agent_type is required"):
            AgentRequest(agent_type="", prompt="Test prompt")
    
    @pytest.mark.asyncio
    async def test_validate_request_wrong_agent_type(self):
        """Test request validation with wrong agent_type."""
        request = AgentRequest(agent_type="wrong_agent", prompt="Test prompt")
        
        with pytest.raises(ValueError, match="does not match agent"):
            await self.agent.validate_request(request)
    
    @pytest.mark.asyncio
    async def test_validate_request_missing_prompt(self):
        """Test request validation with missing prompt."""
        with pytest.raises(ValueError, match="prompt is required"):
            AgentRequest(agent_type="mock_agent", prompt="")
    
    @pytest.mark.asyncio
    async def test_validate_request_missing_auth_when_required(self):
        """Test request validation with missing authentication when required."""
        request = AgentRequest(agent_type="mock_agent", prompt="Test prompt")
        
        with pytest.raises(ValueError, match="authentication is required"):
            await self.agent.validate_request(request)
    
    @pytest.mark.asyncio
    async def test_validate_request_auth_disabled(self):
        """Test request validation when authentication is disabled."""
        self.mock_agent_core.auth_manager.enabled = False
        request = AgentRequest(agent_type="mock_agent", prompt="Test prompt")
        
        # Should not raise any exception
        await self.agent.validate_request(request)
    
    @pytest.mark.asyncio
    async def test_handle_request_success(self):
        """Test successful request handling."""
        auth_context = AuthContext(access_token="test_token")
        request = AgentRequest(
            agent_type="mock_agent",
            prompt="Test prompt",
            authentication=auth_context,
            request_id="req_123"
        )
        
        self.mock_agent_core.auth_manager.validate_token = AsyncMock()
        
        response = await self.agent.handle_request(request)
        
        assert response.success is True
        assert response.agent_type == "mock_agent"
        assert response.request_id == "req_123"
        assert response.execution_time > 0
        assert "Mock response to: Test prompt" in response.responses
        assert self.agent.process_prompt_called
    
    @pytest.mark.asyncio
    async def test_handle_request_validation_error(self):
        """Test request handling with validation error."""
        request = AgentRequest(agent_type="wrong_agent", prompt="Test prompt")
        
        response = await self.agent.handle_request(request)
        
        assert response.success is False
        assert response.agent_type == "mock_agent"
        assert "Error:" in response.responses[0]
        assert "error" in response.metadata
    
    @pytest.mark.asyncio
    async def test_handle_request_processing_error(self):
        """Test request handling with processing error."""
        auth_context = AuthContext(access_token="test_token")
        request = AgentRequest(
            agent_type="mock_agent",
            prompt="This will cause an error",
            authentication=auth_context
        )
        
        self.mock_agent_core.auth_manager.validate_token = AsyncMock()
        
        response = await self.agent.handle_request(request)
        
        assert response.success is False
        assert response.agent_type == "mock_agent"
        assert "Error:" in response.responses[0]
        assert "error" in response.metadata
    
    @pytest.mark.asyncio
    async def test_handle_request_updates_metrics(self):
        """Test that request handling updates metrics."""
        auth_context = AuthContext(access_token="test_token")
        request = AgentRequest(
            agent_type="mock_agent",
            prompt="Test prompt",
            authentication=auth_context
        )
        
        self.mock_agent_core.auth_manager.validate_token = AsyncMock()
        
        initial_requests = self.agent.metrics.total_requests
        await self.agent.handle_request(request)
        
        assert self.agent.metrics.total_requests == initial_requests + 1
        assert self.agent.metrics.successful_requests == 1
        assert self.agent.metrics.average_response_time > 0
    
    def test_get_metrics(self):
        """Test getting agent metrics."""
        metrics = self.agent.get_metrics()
        
        assert isinstance(metrics, AgentMetrics)
        assert metrics.agent_type == "mock_agent"
        assert metrics.uptime_seconds >= 0
    
    def test_is_healthy(self):
        """Test agent health check."""
        # Not initialized
        assert not self.agent.is_healthy()
        
        # Initialized and healthy
        self.agent._initialized = True
        assert self.agent.is_healthy()
        
        # Agent core unhealthy
        self.mock_agent_core.is_healthy.return_value = False
        assert not self.agent.is_healthy()
    
    @pytest.mark.asyncio
    async def test_get_status(self):
        """Test getting agent status."""
        await self.agent.initialize()
        status = await self.agent.get_status()
        
        assert status["agent_type"] == "mock_agent"
        assert status["initialized"] is True
        assert status["healthy"] is True
        assert status["tools_count"] == 1
        assert "mock_tool" in status["available_tools"]
        assert "metrics" in status
        assert "total_requests" in status["metrics"]