"""
Integration tests for Model Derivatives Agent.
"""

import os
import tempfile
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from agent_core.agents.model_derivatives_agent import ModelDerivativesAgent, LangChainToolWrapper
from agent_core.base_agent import BaseTool
from agent_core.models import AgentRequest, AgentResponse, ToolResult
from agent_core.auth import AuthContext
from agent_core.tools.model_derivatives import SetupDatabaseTool, SQLQueryTool


class MockAgentCore:
    """Mock AgentCore for testing."""
    
    def __init__(self):
        self.logger = MagicMock()
        self.config = MagicMock()
        self.config.cache_directory = "/tmp/test_cache"
        self.tool_registry = None
        self.auth_manager = MagicMock()
        self.auth_manager.enabled = False
    
    def is_healthy(self):
        return True


class MockTool(BaseTool):
    """Mock tool for testing."""
    
    def __init__(self, name: str = "mock_tool", description: str = "Mock tool for testing"):
        super().__init__(name, description)
        self.execute_result = ToolResult(
            tool_name=name,
            success=True,
            result="Mock result"
        )
    
    def _get_parameters_schema(self):
        return {
            "type": "object",
            "properties": {
                "test_param": {
                    "type": "string",
                    "description": "Test parameter"
                }
            },
            "required": ["test_param"]
        }
    
    async def execute(self, **kwargs):
        return self.execute_result


class TestLangChainToolWrapper:
    """Test the LangChainToolWrapper."""
    
    @pytest.fixture
    def mock_tool(self):
        """Create a mock tool."""
        return MockTool()
    
    @pytest.fixture
    def auth_context(self):
        """Create a test auth context."""
        return AuthContext(access_token="test_token", urn="test_urn")
    
    @pytest.fixture
    def temp_cache_dir(self):
        """Create a temporary cache directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir
    
    def test_wrapper_initialization(self, mock_tool, auth_context, temp_cache_dir):
        """Test wrapper initialization."""
        wrapper = LangChainToolWrapper(mock_tool, auth_context, temp_cache_dir)
        
        assert wrapper.name == "mock_tool"
        assert wrapper.description == "Mock tool for testing"
        assert wrapper._agent_tool == mock_tool
        assert wrapper._auth_context == auth_context
        assert wrapper._cache_dir == temp_cache_dir
    
    @pytest.mark.asyncio
    async def test_wrapper_execution_success(self, mock_tool, auth_context, temp_cache_dir):
        """Test successful wrapper execution."""
        wrapper = LangChainToolWrapper(mock_tool, auth_context, temp_cache_dir)
        
        result = await wrapper._arun(test_param="test_value")
        
        assert result == "Mock result"
    
    @pytest.mark.asyncio
    async def test_wrapper_execution_failure(self, mock_tool, auth_context, temp_cache_dir):
        """Test wrapper execution with tool failure."""
        # Set up tool to return failure
        mock_tool.execute_result = ToolResult(
            tool_name="mock_tool",
            success=False,
            error="Mock error"
        )
        
        wrapper = LangChainToolWrapper(mock_tool, auth_context, temp_cache_dir)
        
        with pytest.raises(Exception, match="Mock error"):
            await wrapper._arun(test_param="test_value")
    
    def test_sync_execution_not_implemented(self, mock_tool, auth_context, temp_cache_dir):
        """Test that sync execution raises NotImplementedError."""
        wrapper = LangChainToolWrapper(mock_tool, auth_context, temp_cache_dir)
        
        with pytest.raises(NotImplementedError):
            wrapper._run(test_param="test_value")


class TestModelDerivativesAgent:
    """Test the ModelDerivativesAgent."""
    
    @pytest.fixture
    def mock_agent_core(self):
        """Create a mock AgentCore."""
        return MockAgentCore()
    
    @pytest.fixture
    def mock_tools(self):
        """Create mock tools."""
        return [
            MockTool("setup_database", "Setup database tool"),
            MockTool("sql_query", "SQL query tool"),
            MockTool("get_table_info", "Get table info tool"),
            MockTool("get_sample_data", "Get sample data tool")
        ]
    
    @pytest.fixture
    def agent(self, mock_agent_core, mock_tools):
        """Create a test agent."""
        return ModelDerivativesAgent(mock_agent_core, mock_tools)
    
    @pytest.fixture
    def auth_context(self):
        """Create a test auth context."""
        return AuthContext(access_token="test_token", urn="test_urn")
    
    def test_agent_initialization(self, agent):
        """Test agent initialization."""
        assert agent.get_agent_type() == "model_derivatives"
        assert len(agent.tools) == 4
        assert agent._llm is None
    
    @pytest.mark.asyncio
    async def test_agent_initialize(self, agent):
        """Test agent initialization with LLM."""
        with patch('agent_core.agents.model_derivatives_agent.ChatBedrock') as mock_bedrock:
            mock_llm = MagicMock()
            mock_bedrock.return_value = mock_llm
            
            await agent.initialize()
            
            assert agent._llm == mock_llm
            mock_bedrock.assert_called_once_with(
                model_id="anthropic.claude-3-5-sonnet-20241022-v2:0",
                model_kwargs={
                    "temperature": 0.0,
                    "max_tokens": 4096
                }
            )
    
    def test_get_cache_dir_with_urn(self, agent, auth_context):
        """Test cache directory generation with URN."""
        with tempfile.TemporaryDirectory() as temp_dir:
            agent.agent_core.config.cache_directory = temp_dir
            
            cache_dir = agent._get_cache_dir(auth_context)
            
            expected_path = os.path.join(temp_dir, "model_derivatives", "test_urn")
            assert cache_dir == expected_path
            assert os.path.exists(cache_dir)
    
    def test_get_cache_dir_without_urn(self, agent):
        """Test cache directory generation without URN."""
        auth_context = AuthContext(access_token="test_token")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            agent.agent_core.config.cache_directory = temp_dir
            
            cache_dir = agent._get_cache_dir(auth_context)
            
            expected_path = os.path.join(temp_dir, "model_derivatives", "default")
            assert cache_dir == expected_path
            assert os.path.exists(cache_dir)
    
    def test_get_logs_path(self, agent):
        """Test logs path generation."""
        cache_dir = "/test/cache/dir"
        logs_path = agent._get_logs_path(cache_dir)
        
        assert logs_path == "/test/cache/dir/logs.txt"
    
    def test_log_interaction_success(self, agent):
        """Test successful log interaction."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logs_path = os.path.join(temp_dir, "logs.txt")
            
            agent._log_interaction(logs_path, "Test message")
            
            assert os.path.exists(logs_path)
            with open(logs_path, "r") as f:
                content = f.read()
                assert "Test message" in content
    
    def test_log_interaction_failure(self, agent):
        """Test log interaction with file write failure."""
        # Use invalid path to trigger error
        logs_path = "/invalid/path/logs.txt"
        
        # Should not raise exception, just log warning
        agent._log_interaction(logs_path, "Test message")
        
        # Verify warning was logged
        agent.agent_core.logger.warning.assert_called()
    
    @pytest.mark.asyncio
    async def test_process_prompt_missing_auth(self, agent):
        """Test process_prompt with missing authentication."""
        request = AgentRequest(
            agent_type="model_derivatives",
            prompt="Test prompt",
            context={},
            authentication=None,
            metadata={}
        )
        
        response = await agent.process_prompt(request)
        
        assert not response.success
        assert "Authentication context is required" in response.responses[0]
    
    @pytest.mark.asyncio
    async def test_process_prompt_success(self, agent, auth_context):
        """Test successful prompt processing."""
        request = AgentRequest(
            agent_type="model_derivatives",
            prompt="Test prompt",
            context={},
            authentication=auth_context,
            metadata={}
        )
        
        # Mock LangChain agent
        mock_langchain_agent = AsyncMock()
        mock_langchain_agent.ainvoke.return_value = {"output": "Test response"}
        
        with patch.object(agent, '_create_langchain_agent', return_value=mock_langchain_agent):
            with tempfile.TemporaryDirectory() as temp_dir:
                agent.agent_core.config.cache_directory = temp_dir
                
                response = await agent.process_prompt(request)
                
                assert response.success
                assert len(response.responses) == 1
                assert response.responses[0] == "Test response"
                assert response.agent_type == "model_derivatives"
                assert "cache_dir" in response.metadata
                assert "urn" in response.metadata
    
    @pytest.mark.asyncio
    async def test_process_prompt_agent_error(self, agent, auth_context):
        """Test prompt processing with agent execution error."""
        request = AgentRequest(
            agent_type="model_derivatives",
            prompt="Test prompt",
            context={},
            authentication=auth_context,
            metadata={}
        )
        
        # Mock LangChain agent to raise error
        mock_langchain_agent = AsyncMock()
        mock_langchain_agent.ainvoke.side_effect = Exception("Agent error")
        
        with patch.object(agent, '_create_langchain_agent', return_value=mock_langchain_agent):
            with tempfile.TemporaryDirectory() as temp_dir:
                agent.agent_core.config.cache_directory = temp_dir
                
                response = await agent.process_prompt(request)
                
                assert response.success  # Agent handles errors gracefully
                assert len(response.responses) == 1
                assert "Agent execution error" in response.responses[0]
    
    @pytest.mark.asyncio
    async def test_get_status(self, agent):
        """Test get_status method."""
        # Initialize agent first
        with patch('agent_core.agents.model_derivatives_agent.ChatBedrock'):
            await agent.initialize()
        
        status = await agent.get_status()
        
        assert status["agent_type"] == "model_derivatives"
        assert status["llm_initialized"] is True
        assert status["llm_model_id"] == "anthropic.claude-3-5-sonnet-20241022-v2:0"
        assert status["supports_sqlite"] is True
        assert status["supports_caching"] is True
        assert "database_tools" in status
        assert len(status["database_tools"]) == 4
    
    def test_create_langchain_agent(self, agent, auth_context):
        """Test LangChain agent creation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Initialize LLM first
            agent._llm = MagicMock()
            
            with patch('agent_core.agents.model_derivatives_agent.create_langchain_react_agent') as mock_create:
                with patch('agent_core.agents.model_derivatives_agent.AgentExecutor') as mock_executor:
                    mock_agent = MagicMock()
                    mock_create.return_value = mock_agent
                    mock_executor_instance = MagicMock()
                    mock_executor.return_value = mock_executor_instance
                    
                    result = agent._create_langchain_agent(auth_context, temp_dir)
                    
                    assert result == mock_executor_instance
                    mock_create.assert_called_once()
                    mock_executor.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_validate_request(self, agent, auth_context):
        """Test request validation."""
        # Valid request
        valid_request = AgentRequest(
            agent_type="model_derivatives",
            prompt="Test prompt",
            context={},
            authentication=auth_context,
            metadata={}
        )
        
        # Should not raise exception
        await agent.validate_request(valid_request)
        
        # Invalid agent type
        invalid_request = AgentRequest(
            agent_type="wrong_type",
            prompt="Test prompt",
            context={},
            authentication=auth_context,
            metadata={}
        )
        
        with pytest.raises(ValueError, match="does not match agent"):
            await agent.validate_request(invalid_request)
        
        # Missing prompt - this will fail at AgentRequest creation
        with pytest.raises(ValueError, match="prompt is required"):
            AgentRequest(
                agent_type="model_derivatives",
                prompt="",
                context={},
                authentication=auth_context,
                metadata={}
            )


class TestModelDerivativesAgentIntegration:
    """Integration tests with real tools."""
    
    @pytest.fixture
    def mock_agent_core(self):
        """Create a mock AgentCore."""
        return MockAgentCore()
    
    @pytest.fixture
    def real_tools(self):
        """Create real tools for integration testing."""
        return [
            SetupDatabaseTool(),
            SQLQueryTool()
        ]
    
    @pytest.fixture
    def agent(self, mock_agent_core, real_tools):
        """Create an agent with real tools."""
        return ModelDerivativesAgent(mock_agent_core, real_tools)
    
    @pytest.fixture
    def auth_context(self):
        """Create a test auth context."""
        return AuthContext(access_token="test_token", urn="test_urn")
    
    def test_agent_with_real_tools(self, agent):
        """Test agent initialization with real tools."""
        assert agent.get_agent_type() == "model_derivatives"
        assert len(agent.tools) == 2
        assert agent.tools[0].name == "setup_database"
        assert agent.tools[1].name == "sql_query"
    
    def test_tool_wrapper_with_real_tools(self, agent, auth_context):
        """Test tool wrapper with real tools."""
        with tempfile.TemporaryDirectory() as temp_dir:
            setup_tool = agent.tools[0]  # SetupDatabaseTool
            wrapper = LangChainToolWrapper(setup_tool, auth_context, temp_dir)
            
            assert wrapper.name == "setup_database"
            assert "SQLite database" in wrapper.description
    
    @pytest.mark.asyncio
    async def test_tool_execution_through_wrapper(self, agent, auth_context):
        """Test tool execution through wrapper."""
        with tempfile.TemporaryDirectory() as temp_dir:
            sql_tool = agent.tools[1]  # SQLQueryTool
            wrapper = LangChainToolWrapper(sql_tool, auth_context, temp_dir)
            
            # This should fail because no database exists
            with pytest.raises(Exception, match="Database not found"):
                await wrapper._arun(query="SELECT * FROM properties")
    
    @pytest.mark.asyncio
    async def test_agent_status_with_real_tools(self, agent):
        """Test agent status with real tools."""
        status = await agent.get_status()
        
        assert status["agent_type"] == "model_derivatives"
        assert "tools_count" in status
        assert status["tools_count"] == 2