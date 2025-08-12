"""
Integration tests for AEC Data Model Agent.
"""

import pytest
import os
import tempfile
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime

from agent_core.agents.aec_data_model_agent import AECDataModelAgent, LangChainToolWrapper
from agent_core.models import AgentRequest, AgentResponse
from agent_core.config import CoreConfig
from agent_core.auth import AuthContext
from agent_core.base_agent import BaseTool
from agent_core.models import ToolResult


@pytest.fixture
def mock_agent_core():
    """Create a mock AgentCore instance."""
    core = Mock()
    core.config = CoreConfig(
        aws_region="us-east-1",
        bedrock_model_id="anthropic.claude-3-5-sonnet-20241022-v2:0",
        opensearch_endpoint="https://test-opensearch.com",
        cache_directory="/tmp/test_cache",
        log_level="INFO",
        health_check_interval=30
    )
    core.logger = Mock()
    core.logger.info = Mock()
    core.logger.debug = Mock()
    core.logger.warning = Mock()
    core.logger.error = Mock()
    core.auth_manager = Mock()
    core.auth_manager.enabled = True
    core.auth_manager.validate_token = AsyncMock()
    core.tool_registry = None
    core.is_healthy = Mock(return_value=True)
    return core


@pytest.fixture
def auth_context():
    """Create a mock authentication context."""
    return AuthContext(
        access_token="test_access_token",
        element_group_id="test_element_group_id"
    )


@pytest.fixture
def mock_vector_store():
    """Create a mock vector store."""
    store = Mock()
    store._initialized = False
    store.initialize = AsyncMock()
    store.similarity_search = AsyncMock(return_value=[])
    store.add_documents = AsyncMock(return_value=["doc1", "doc2"])
    store.health_check = AsyncMock(return_value={
        "cluster_status": "green",
        "index_exists": True,
        "document_count": 10
    })
    return store


@pytest.fixture
def mock_property_manager():
    """Create a mock property definitions manager."""
    manager = Mock()
    manager.ensure_vector_store_populated = AsyncMock()
    return manager


class TestLangChainToolWrapper:
    """Test cases for LangChainToolWrapper."""
    
    @pytest.fixture
    def mock_agent_tool(self):
        """Create a mock AgentCore tool."""
        tool = Mock(spec=BaseTool)
        tool.name = "test_tool"
        tool.description = "Test tool description"
        tool.execute = AsyncMock(return_value=ToolResult(
            tool_name="test_tool",
            success=True,
            result={"test": "result"}
        ))
        return tool
    
    def test_initialization(self, mock_agent_tool, auth_context):
        """Test wrapper initialization."""
        cache_dir = "/tmp/test"
        wrapper = LangChainToolWrapper(mock_agent_tool, auth_context, cache_dir)
        
        assert wrapper.name == "test_tool"
        assert wrapper.description == "Test tool description"
        assert wrapper._agent_tool == mock_agent_tool
        assert wrapper._auth_context == auth_context
        assert wrapper._cache_dir == cache_dir
    
    @pytest.mark.asyncio
    async def test_arun_success(self, mock_agent_tool, auth_context):
        """Test successful async execution."""
        cache_dir = "/tmp/test"
        wrapper = LangChainToolWrapper(mock_agent_tool, auth_context, cache_dir)
        
        result = await wrapper._arun(param1="value1", param2="value2")
        
        assert result == {"test": "result"}
        mock_agent_tool.execute.assert_called_once_with(
            param1="value1",
            param2="value2",
            auth_context=auth_context,
            cache_dir=cache_dir
        )
    
    @pytest.mark.asyncio
    async def test_arun_failure(self, mock_agent_tool, auth_context):
        """Test async execution with tool failure."""
        cache_dir = "/tmp/test"
        mock_agent_tool.execute.return_value = ToolResult(
            tool_name="test_tool",
            success=False,
            error="Tool execution failed"
        )
        
        wrapper = LangChainToolWrapper(mock_agent_tool, auth_context, cache_dir)
        
        with pytest.raises(Exception, match="Tool execution failed"):
            await wrapper._arun(param1="value1")
    
    def test_run_not_implemented(self, mock_agent_tool, auth_context):
        """Test that synchronous run is not implemented."""
        cache_dir = "/tmp/test"
        wrapper = LangChainToolWrapper(mock_agent_tool, auth_context, cache_dir)
        
        with pytest.raises(NotImplementedError):
            wrapper._run(param1="value1")


class TestAECDataModelAgent:
    """Test cases for AECDataModelAgent."""
    
    def test_initialization(self, mock_agent_core):
        """Test agent initialization."""
        agent = AECDataModelAgent(mock_agent_core)
        
        assert agent.get_agent_type() == "aec_data_model"
        assert agent.agent_core == mock_agent_core
        assert agent._llm is None
        assert agent._vector_store is None
        assert agent._property_manager is None
    
    @pytest.mark.asyncio
    async def test_initialize(self, mock_agent_core, mock_vector_store, mock_property_manager):
        """Test agent initialization process."""
        agent = AECDataModelAgent(mock_agent_core)
        
        with patch('agent_core.agents.aec_data_model_agent.ChatBedrock') as mock_bedrock, \
             patch('agent_core.agents.aec_data_model_agent.OpenSearchVectorStore', return_value=mock_vector_store), \
             patch('agent_core.agents.aec_data_model_agent.PropertyDefinitionsManager', return_value=mock_property_manager):
            
            await agent.initialize()
            
            assert agent._initialized is True
            assert agent._llm is not None
            assert agent._vector_store == mock_vector_store
            assert agent._property_manager == mock_property_manager
            assert len(agent.tools) == 4  # 4 AEC Data Model tools
            
            mock_vector_store.initialize.assert_called_once()
            mock_agent_core.logger.info.assert_called()
    
    def test_get_cache_dir_with_element_group_id(self, mock_agent_core, auth_context):
        """Test cache directory generation with element group ID."""
        agent = AECDataModelAgent(mock_agent_core)
        
        cache_dir = agent._get_cache_dir(auth_context)
        
        expected_path = os.path.join(
            mock_agent_core.config.cache_directory,
            "aec_data_model",
            "test_element_group_id"
        )
        assert cache_dir == expected_path
    
    def test_get_cache_dir_without_element_group_id(self, mock_agent_core):
        """Test cache directory generation without element group ID."""
        agent = AECDataModelAgent(mock_agent_core)
        auth_context = AuthContext(access_token="test_token")  # No element_group_id
        
        cache_dir = agent._get_cache_dir(auth_context)
        
        expected_path = os.path.join(
            mock_agent_core.config.cache_directory,
            "aec_data_model",
            "default"
        )
        assert cache_dir == expected_path
    
    def test_get_logs_path(self, mock_agent_core):
        """Test logs path generation."""
        agent = AECDataModelAgent(mock_agent_core)
        cache_dir = "/tmp/test_cache"
        
        logs_path = agent._get_logs_path(cache_dir)
        
        assert logs_path == "/tmp/test_cache/logs.txt"
    
    def test_log_interaction(self, mock_agent_core):
        """Test interaction logging."""
        agent = AECDataModelAgent(mock_agent_core)
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp_file:
            temp_path = temp_file.name
        
        try:
            agent._log_interaction(temp_path, "Test message")
            
            with open(temp_path, 'r') as f:
                content = f.read()
                assert "Test message" in content
                assert datetime.now().strftime("%Y-%m-%d") in content
        finally:
            os.unlink(temp_path)
    
    @pytest.mark.asyncio
    async def test_ensure_property_definitions_loaded(self, mock_agent_core, auth_context, mock_property_manager):
        """Test property definitions loading."""
        agent = AECDataModelAgent(mock_agent_core)
        agent._property_manager = mock_property_manager
        cache_dir = "/tmp/test_cache"
        
        await agent._ensure_property_definitions_loaded(auth_context, cache_dir)
        
        mock_property_manager.ensure_vector_store_populated.assert_called_once_with(
            auth_context.element_group_id,
            auth_context.access_token,
            cache_dir
        )
    
    @pytest.mark.asyncio
    async def test_ensure_property_definitions_loaded_no_element_group_id(self, mock_agent_core, mock_property_manager):
        """Test property definitions loading without element group ID."""
        agent = AECDataModelAgent(mock_agent_core)
        agent._property_manager = mock_property_manager
        auth_context = AuthContext(access_token="test_token")  # No element_group_id
        cache_dir = "/tmp/test_cache"
        
        await agent._ensure_property_definitions_loaded(auth_context, cache_dir)
        
        # Should not call the property manager
        mock_property_manager.ensure_vector_store_populated.assert_not_called()
        mock_agent_core.logger.warning.assert_called()
    
    @pytest.mark.asyncio
    async def test_process_prompt_no_auth(self, mock_agent_core):
        """Test processing prompt without authentication."""
        agent = AECDataModelAgent(mock_agent_core)
        
        request = AgentRequest(
            agent_type="aec_data_model",
            prompt="Test prompt",
            context={},
            authentication=None,
            metadata={}
        )
        
        response = await agent.process_prompt(request)
        
        assert response.success is False
        assert "Authentication context is required" in response.responses[0]
    
    @pytest.mark.asyncio
    async def test_process_prompt_success(self, mock_agent_core, auth_context, mock_vector_store, mock_property_manager):
        """Test successful prompt processing."""
        agent = AECDataModelAgent(mock_agent_core)
        agent._property_manager = mock_property_manager
        
        # Mock LangChain agent
        mock_langchain_agent = Mock()
        mock_langchain_agent.ainvoke = AsyncMock(return_value={"output": "Test response"})
        
        with patch('agent_core.agents.aec_data_model_agent.ChatBedrock'), \
             patch('agent_core.agents.aec_data_model_agent.OpenSearchVectorStore', return_value=mock_vector_store), \
             patch('agent_core.agents.aec_data_model_agent.PropertyDefinitionsManager', return_value=mock_property_manager), \
             patch.object(agent, '_create_langchain_agent', return_value=mock_langchain_agent), \
             patch('os.makedirs'):
            
            await agent.initialize()
            
            request = AgentRequest(
                agent_type="aec_data_model",
                prompt="What are the wall properties?",
                context={},
                authentication=auth_context,
                metadata={}
            )
            
            response = await agent.process_prompt(request)
            
            assert response.success is True
            assert len(response.responses) == 1
            assert response.responses[0] == "Test response"
            assert response.agent_type == "aec_data_model"
            assert "element_group_id" in response.metadata
            
            # Verify property definitions were loaded
            mock_property_manager.ensure_vector_store_populated.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_process_prompt_agent_error(self, mock_agent_core, auth_context, mock_vector_store, mock_property_manager):
        """Test prompt processing with agent execution error."""
        agent = AECDataModelAgent(mock_agent_core)
        agent._property_manager = mock_property_manager
        
        # Mock LangChain agent that raises an error
        mock_langchain_agent = Mock()
        mock_langchain_agent.ainvoke = AsyncMock(side_effect=Exception("Agent execution failed"))
        
        with patch('agent_core.agents.aec_data_model_agent.ChatBedrock'), \
             patch('agent_core.agents.aec_data_model_agent.OpenSearchVectorStore', return_value=mock_vector_store), \
             patch('agent_core.agents.aec_data_model_agent.PropertyDefinitionsManager', return_value=mock_property_manager), \
             patch.object(agent, '_create_langchain_agent', return_value=mock_langchain_agent), \
             patch('os.makedirs'):
            
            await agent.initialize()
            
            request = AgentRequest(
                agent_type="aec_data_model",
                prompt="Test prompt",
                context={},
                authentication=auth_context,
                metadata={}
            )
            
            response = await agent.process_prompt(request)
            
            assert response.success is True  # Agent handles errors gracefully
            assert "Agent execution error" in response.responses[0]
    
    @pytest.mark.asyncio
    async def test_get_status(self, mock_agent_core, mock_vector_store, mock_property_manager):
        """Test getting agent status."""
        agent = AECDataModelAgent(mock_agent_core)
        
        with patch('agent_core.agents.aec_data_model_agent.ChatBedrock'), \
             patch('agent_core.agents.aec_data_model_agent.OpenSearchVectorStore', return_value=mock_vector_store), \
             patch('agent_core.agents.aec_data_model_agent.PropertyDefinitionsManager', return_value=mock_property_manager):
            
            await agent.initialize()
            
            status = await agent.get_status()
            
            assert status["agent_type"] == "aec_data_model"
            assert status["initialized"] is True
            assert status["llm_initialized"] is True
            assert status["vector_store_initialized"] is True
            assert status["property_manager_initialized"] is True
            assert status["supports_graphql"] is True
            assert status["supports_semantic_search"] is True
            assert status["supports_caching"] is True
            assert "vector_store_health" in status
    
    @pytest.mark.asyncio
    async def test_get_status_vector_store_error(self, mock_agent_core, mock_vector_store, mock_property_manager):
        """Test getting agent status with vector store error."""
        agent = AECDataModelAgent(mock_agent_core)
        mock_vector_store.health_check.side_effect = Exception("Vector store error")
        
        with patch('agent_core.agents.aec_data_model_agent.ChatBedrock'), \
             patch('agent_core.agents.aec_data_model_agent.OpenSearchVectorStore', return_value=mock_vector_store), \
             patch('agent_core.agents.aec_data_model_agent.PropertyDefinitionsManager', return_value=mock_property_manager):
            
            await agent.initialize()
            
            status = await agent.get_status()
            
            assert "error" in status["vector_store_health"]
            assert "Vector store error" in status["vector_store_health"]["error"]
    
    @pytest.mark.asyncio
    async def test_shutdown(self, mock_agent_core, mock_vector_store, mock_property_manager):
        """Test agent shutdown."""
        agent = AECDataModelAgent(mock_agent_core)
        
        with patch('agent_core.agents.aec_data_model_agent.ChatBedrock'), \
             patch('agent_core.agents.aec_data_model_agent.OpenSearchVectorStore', return_value=mock_vector_store), \
             patch('agent_core.agents.aec_data_model_agent.PropertyDefinitionsManager', return_value=mock_property_manager):
            
            await agent.initialize()
            await agent.shutdown()
            
            assert agent._initialized is False
            mock_agent_core.logger.info.assert_called()
    
    def test_create_langchain_agent(self, mock_agent_core, auth_context, mock_vector_store, mock_property_manager):
        """Test LangChain agent creation."""
        agent = AECDataModelAgent(mock_agent_core)
        
        with patch('agent_core.agents.aec_data_model_agent.ChatBedrock'), \
             patch('agent_core.agents.aec_data_model_agent.OpenSearchVectorStore', return_value=mock_vector_store), \
             patch('agent_core.agents.aec_data_model_agent.PropertyDefinitionsManager', return_value=mock_property_manager), \
             patch('agent_core.agents.aec_data_model_agent.create_langchain_react_agent') as mock_create_agent, \
             patch('agent_core.agents.aec_data_model_agent.AgentExecutor') as mock_executor:
            
            # Initialize agent to set up tools
            import asyncio
            asyncio.run(agent.initialize())
            
            cache_dir = "/tmp/test_cache"
            langchain_agent = agent._create_langchain_agent(auth_context, cache_dir)
            
            # Verify LangChain agent was created
            mock_create_agent.assert_called_once()
            mock_executor.assert_called_once()
            
            # Verify tools were wrapped
            executor_call_args = mock_executor.call_args[1]
            assert "tools" in executor_call_args
            assert len(executor_call_args["tools"]) == 4


@pytest.mark.asyncio
async def test_integration_workflow(mock_agent_core, auth_context, mock_vector_store, mock_property_manager):
    """Test complete agent workflow integration."""
    # Create agent
    agent = AECDataModelAgent(mock_agent_core)
    
    # Mock successful LangChain execution
    mock_langchain_agent = Mock()
    mock_langchain_agent.ainvoke = AsyncMock(return_value={
        "output": "Found 5 wall elements with the following properties: Height, Width, Material"
    })
    
    with patch('agent_core.agents.aec_data_model_agent.ChatBedrock'), \
         patch('agent_core.agents.aec_data_model_agent.OpenSearchVectorStore', return_value=mock_vector_store), \
         patch('agent_core.agents.aec_data_model_agent.PropertyDefinitionsManager', return_value=mock_property_manager), \
         patch.object(agent, '_create_langchain_agent', return_value=mock_langchain_agent), \
         patch('os.makedirs'):
        
        # Initialize agent
        await agent.initialize()
        assert agent._initialized is True
        assert agent.get_agent_type() == "aec_data_model"
        
        # Process a request
        request = AgentRequest(
            agent_type="aec_data_model",
            prompt="What are the properties of wall elements?",
            context={},
            authentication=auth_context,
            metadata={}
        )
        
        response = await agent.process_prompt(request)
        
        # Verify response
        assert response.success is True
        assert len(response.responses) == 1
        assert "wall elements" in response.responses[0]
        assert response.agent_type == "aec_data_model"
        assert response.metadata["element_group_id"] == auth_context.element_group_id
        
        # Verify property definitions were loaded
        mock_property_manager.ensure_vector_store_populated.assert_called_once_with(
            auth_context.element_group_id,
            auth_context.access_token,
            agent._get_cache_dir(auth_context)
        )
        
        # Get status
        status = await agent.get_status()
        assert status["healthy"] is True
        assert status["supports_graphql"] is True
        assert status["supports_semantic_search"] is True
        
        # Shutdown
        await agent.shutdown()
        assert agent._initialized is False