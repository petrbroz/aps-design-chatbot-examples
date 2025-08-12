"""
Integration tests for ModelPropertiesAgent.
"""

import pytest
import tempfile
import os
import json
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from agent_core.agents.model_properties_agent import ModelPropertiesAgent, LangChainToolWrapper
from agent_core.auth import AuthContext
from agent_core.models import AgentRequest, AgentResponse
from agent_core.tools.model_properties import CreateIndexTool, ExecuteJQQueryTool


class TestLangChainToolWrapper:
    """Test cases for LangChainToolWrapper."""
    
    @pytest.fixture
    def auth_context(self):
        """Create test auth context."""
        return AuthContext(
            access_token="test_token",
            project_id="b.project123",
            version_id="test_version"
        )
    
    @pytest.fixture
    def agent_tool(self):
        """Create test agent tool."""
        return ExecuteJQQueryTool()
    
    def test_init(self, agent_tool, auth_context):
        """Test wrapper initialization."""
        with tempfile.TemporaryDirectory() as temp_dir:
            wrapper = LangChainToolWrapper(agent_tool, auth_context, temp_dir)
            
            assert wrapper.name == agent_tool.name
            assert wrapper.description == agent_tool.description
            assert wrapper._agent_tool == agent_tool
            assert wrapper._auth_context == auth_context
            assert wrapper._cache_dir == temp_dir
    
    @pytest.mark.asyncio
    async def test_arun_success(self, agent_tool, auth_context):
        """Test successful async execution."""
        with tempfile.TemporaryDirectory() as temp_dir:
            wrapper = LangChainToolWrapper(agent_tool, auth_context, temp_dir)
            
            result = await wrapper._arun(
                jq_query=".test",
                input_json='{"test": "value"}'
            )
            
            assert result == ["value"]
    
    @pytest.mark.asyncio
    async def test_arun_failure(self, agent_tool, auth_context):
        """Test async execution with failure."""
        with tempfile.TemporaryDirectory() as temp_dir:
            wrapper = LangChainToolWrapper(agent_tool, auth_context, temp_dir)
            
            with pytest.raises(Exception):
                await wrapper._arun(
                    jq_query=".invalid[syntax",
                    input_json='{"test": "value"}'
                )
    
    def test_run_not_implemented(self, agent_tool, auth_context):
        """Test that sync run is not implemented."""
        with tempfile.TemporaryDirectory() as temp_dir:
            wrapper = LangChainToolWrapper(agent_tool, auth_context, temp_dir)
            
            with pytest.raises(NotImplementedError):
                wrapper._run()


class TestModelPropertiesAgent:
    """Test cases for ModelPropertiesAgent."""
    
    @pytest.fixture
    def mock_agent_core(self):
        """Create mock agent core."""
        mock_core = MagicMock()
        mock_core.config = MagicMock()
        mock_core.config.cache_directory = "/tmp/test_cache"
        mock_core.logger = MagicMock()
        mock_core.tool_registry = MagicMock()
        mock_core.auth_manager = MagicMock()
        mock_core.auth_manager.enabled = False
        mock_core.is_healthy.return_value = True
        return mock_core
    
    @pytest.fixture
    def auth_context(self):
        """Create test auth context."""
        return AuthContext(
            access_token="test_token",
            project_id="b.project123",
            version_id="test_version"
        )
    
    @pytest.fixture
    def agent(self, mock_agent_core):
        """Create test agent."""
        # Create some mock tools
        mock_tools = [
            CreateIndexTool(),
            ExecuteJQQueryTool()
        ]
        return ModelPropertiesAgent(mock_agent_core, tools=mock_tools)
    
    def test_init(self, mock_agent_core):
        """Test agent initialization."""
        agent = ModelPropertiesAgent(mock_agent_core)
        assert agent.get_agent_type() == "model_properties"
        assert agent.agent_core == mock_agent_core
    
    @pytest.mark.asyncio
    async def test_initialize(self, agent):
        """Test agent initialization."""
        await agent.initialize()
        assert agent._initialized
        assert agent._llm is not None
        assert len(agent.tools) > 0
    
    def test_get_agent_type(self, mock_agent_core):
        """Test agent type."""
        agent = ModelPropertiesAgent(mock_agent_core)
        assert agent.get_agent_type() == "model_properties"
    
    def test_get_cache_dir(self, agent, auth_context):
        """Test cache directory creation."""
        cache_dir = agent._get_cache_dir(auth_context)
        
        assert os.path.exists(cache_dir)
        assert "model_properties" in cache_dir
        assert "test_version" in cache_dir
    
    def test_get_cache_dir_no_version(self, agent):
        """Test cache directory creation without version_id."""
        auth_context = AuthContext(
            access_token="test_token",
            project_id="b.project123"
        )
        
        cache_dir = agent._get_cache_dir(auth_context)
        
        assert os.path.exists(cache_dir)
        assert "model_properties" in cache_dir
        assert "default" in cache_dir
    
    def test_get_logs_path(self, agent):
        """Test logs path creation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logs_path = agent._get_logs_path(temp_dir)
            assert logs_path.endswith("logs.txt")
            assert temp_dir in logs_path
    
    def test_log_interaction(self, agent):
        """Test interaction logging."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logs_path = os.path.join(temp_dir, "logs.txt")
            
            agent._log_interaction(logs_path, "Test message")
            
            assert os.path.exists(logs_path)
            with open(logs_path, "r") as f:
                content = f.read()
                assert "Test message" in content
                assert datetime.now().strftime("%Y-%m-%d") in content
    
    def test_create_langchain_agent(self, agent, auth_context):
        """Test LangChain agent creation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Mock the LangChain agent creation to avoid complex setup
            with patch('agent_core.agents.model_properties_agent.create_langchain_react_agent') as mock_create:
                with patch('agent_core.agents.model_properties_agent.AgentExecutor') as mock_executor:
                    mock_agent = MagicMock()
                    mock_create.return_value = mock_agent
                    mock_executor_instance = MagicMock()
                    mock_executor.return_value = mock_executor_instance
                    
                    langchain_agent = agent._create_langchain_agent(auth_context, temp_dir)
                    
                    assert langchain_agent is not None
                    # Verify that the creation functions were called
                    mock_create.assert_called_once()
                    mock_executor.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_process_prompt_missing_auth(self, agent):
        """Test processing prompt without authentication."""
        request = AgentRequest(
            agent_type="model_properties",
            prompt="Test prompt"
        )
        
        response = await agent.process_prompt(request)
        
        assert not response.success
        assert "Authentication context is required" in response.responses[0]
    
    @pytest.mark.asyncio
    async def test_process_prompt_success(self, agent, auth_context):
        """Test successful prompt processing."""
        request = AgentRequest(
            agent_type="model_properties",
            prompt="What tools are available?",
            authentication=auth_context
        )
        
        # Mock the LangChain agent to avoid actual LLM calls
        mock_agent = AsyncMock()
        mock_agent.ainvoke.return_value = {"output": "I have tools for creating indexes and querying properties."}
        
        with patch.object(agent, '_create_langchain_agent', return_value=mock_agent):
            response = await agent.process_prompt(request)
        
        assert response.success
        assert len(response.responses) > 0
        assert "tools" in response.responses[0]
        assert response.agent_type == "model_properties"
        assert response.execution_time > 0
    
    @pytest.mark.asyncio
    async def test_process_prompt_with_tool_execution(self, agent, auth_context):
        """Test prompt processing with tool execution."""
        request = AgentRequest(
            agent_type="model_properties",
            prompt="Execute jq query '.test' on '{\"test\": \"value\"}'",
            authentication=auth_context
        )
        
        # Mock the LangChain agent
        mock_agent = AsyncMock()
        mock_agent.ainvoke.return_value = {"output": "I executed the jq query and got: value"}
        
        with patch.object(agent, '_create_langchain_agent', return_value=mock_agent):
            response = await agent.process_prompt(request)
        
        assert response.success
        assert len(response.responses) > 0
        assert response.agent_type == "model_properties"
    
    @pytest.mark.asyncio
    async def test_process_prompt_error(self, agent, auth_context):
        """Test prompt processing with error."""
        request = AgentRequest(
            agent_type="model_properties",
            prompt="Test prompt",
            authentication=auth_context
        )
        
        # Mock the LangChain agent to raise an error
        with patch.object(agent, '_create_langchain_agent', side_effect=Exception("Test error")):
            response = await agent.process_prompt(request)
        
        assert not response.success
        assert "Test error" in response.responses[0]
        assert response.agent_type == "model_properties"
    
    @pytest.mark.asyncio
    async def test_get_status(self, agent):
        """Test getting agent status."""
        await agent.initialize()  # Initialize the agent first
        status = await agent.get_status()
        
        assert status["agent_type"] == "model_properties"
        assert status["initialized"] == True
        assert status["llm_initialized"] == True
        assert status["llm_model_id"] == "anthropic.claude-3-5-sonnet-20241022-v2:0"
        assert status["supports_mpql"] == True
        assert status["supports_caching"] == True
        assert "tools_count" in status
        assert "metrics" in status
    
    @pytest.mark.asyncio
    async def test_validate_request(self, agent, auth_context):
        """Test request validation."""
        # Valid request
        valid_request = AgentRequest(
            agent_type="model_properties",
            prompt="Test prompt",
            authentication=auth_context
        )
        
        # Should not raise exception
        await agent.validate_request(valid_request)
        
        # Invalid agent type
        invalid_request = AgentRequest(
            agent_type="wrong_type",
            prompt="Test prompt",
            authentication=auth_context
        )
        
        with pytest.raises(ValueError, match="does not match agent"):
            await agent.validate_request(invalid_request)
    
    @pytest.mark.asyncio
    async def test_handle_request(self, agent, auth_context):
        """Test complete request handling."""
        request = AgentRequest(
            agent_type="model_properties",
            prompt="What can you do?",
            authentication=auth_context
        )
        
        # Mock the process_prompt method
        mock_response = AgentResponse(
            responses=["I can help with Model Properties queries."],
            agent_type="model_properties",
            success=True
        )
        
        with patch.object(agent, 'process_prompt', return_value=mock_response):
            response = await agent.handle_request(request)
        
        assert response.success
        assert response.agent_type == "model_properties"
        assert response.request_id == request.request_id
        assert response.execution_time > 0


if __name__ == "__main__":
    pytest.main([__file__])