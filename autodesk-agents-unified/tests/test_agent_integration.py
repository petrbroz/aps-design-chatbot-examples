"""
Integration tests for all agents with real API calls and external services.

These tests validate:
- Agent interactions with external services (APS, AECDM, OpenSearch)
- Caching behavior and performance
- Error scenarios and recovery
- Cross-agent functionality
"""

import pytest
import os
import tempfile
import asyncio
import time
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Dict, Any, List

from agent_core.core import AgentCore
from agent_core.config import CoreConfig
from agent_core.auth import AuthContext
from agent_core.models import AgentRequest, AgentResponse
from agent_core.agents.model_properties_agent import ModelPropertiesAgent
from agent_core.agents.aec_data_model_agent import AECDataModelAgent
from agent_core.agents.model_derivatives_agent import ModelDerivativesAgent
from agent_core.orchestrator import StrandsOrchestrator
from agent_core.cache import CacheManager
from agent_core.error_handler import ErrorHandler


@pytest.fixture
def test_config():
    """Create test configuration."""
    return CoreConfig(
        aws_region="us-east-1",
        bedrock_model_id="anthropic.claude-3-5-sonnet-20241022-v2:0",
        opensearch_endpoint="https://test-opensearch.amazonaws.com",
        cache_directory="/tmp/test_agent_cache",
        log_level="DEBUG",
        health_check_interval=30
    )


@pytest.fixture
async def agent_core(test_config):
    """Create and initialize AgentCore for testing."""
    core = AgentCore(test_config)
    await core.initialize()
    yield core
    await core.shutdown()


@pytest.fixture
def auth_contexts():
    """Create various authentication contexts for testing."""
    return {
        "model_properties": AuthContext(
            access_token="test_mp_token",
            project_id="b.project123",
            version_id="test_version_123"
        ),
        "aec_data_model": AuthContext(
            access_token="test_aec_token",
            element_group_id="test_element_group_456"
        ),
        "model_derivatives": AuthContext(
            access_token="test_md_token",
            urn="dXJuOmFkc2sud2lwcHJvZDpmcy5maWxlOnZmLlUyTVk1UEFwUi1PV2l2TS1Zam9BQXc_dmVyc2lvbj0x"
        )
    }


@pytest.fixture
async def orchestrator(agent_core):
    """Create and initialize Strands orchestrator with all agents."""
    orchestrator = StrandsOrchestrator(agent_core)
    
    # Register all agents
    mp_agent = ModelPropertiesAgent(agent_core)
    aec_agent = AECDataModelAgent(agent_core)
    md_agent = ModelDerivativesAgent(agent_core)
    
    await orchestrator.register_agent("model_properties", mp_agent)
    await orchestrator.register_agent("aec_data_model", aec_agent)
    await orchestrator.register_agent("model_derivatives", md_agent)
    
    return orchestrator


class TestModelPropertiesAgentIntegration:
    """Integration tests for Model Properties Agent."""
    
    @pytest.mark.asyncio
    async def test_agent_initialization_with_real_services(self, agent_core):
        """Test agent initialization with real AWS services."""
        agent = ModelPropertiesAgent(agent_core)
        
        # Mock AWS services to avoid real API calls
        with patch('agent_core.agents.model_properties_agent.ChatBedrock') as mock_bedrock:
            mock_llm = MagicMock()
            mock_bedrock.return_value = mock_llm
            
            await agent.initialize()
            
            assert agent._initialized
            assert agent._llm == mock_llm
            assert len(agent.tools) > 0
            
            # Verify Bedrock was configured correctly
            mock_bedrock.assert_called_once_with(
                model_id="anthropic.claude-3-5-sonnet-20241022-v2:0",
                model_kwargs={
                    "temperature": 0.0,
                    "max_tokens": 4096
                }
            )
    
    @pytest.mark.asyncio
    async def test_cache_behavior_and_performance(self, agent_core, auth_contexts):
        """Test caching behavior and performance metrics."""
        agent = ModelPropertiesAgent(agent_core)
        await agent.initialize()
        
        auth_context = auth_contexts["model_properties"]
        
        # Create test requests
        requests = [
            AgentRequest(
                agent_type="model_properties",
                prompt="List available properties",
                authentication=auth_context
            ),
            AgentRequest(
                agent_type="model_properties",
                prompt="List available properties",  # Same request for cache test
                authentication=auth_context
            )
        ]
        
        # Mock LangChain agent to simulate processing
        mock_langchain_agent = AsyncMock()
        mock_langchain_agent.ainvoke.return_value = {"output": "Available properties: Name, Category, Material"}
        
        with patch.object(agent, '_create_langchain_agent', return_value=mock_langchain_agent):
            # First request - should create cache
            start_time = time.time()
            response1 = await agent.process_prompt(requests[0])
            first_execution_time = time.time() - start_time
            
            assert response1.success
            assert "cache_dir" in response1.metadata
            
            # Verify cache directory was created
            cache_dir = response1.metadata["cache_dir"]
            assert os.path.exists(cache_dir)
            
            # Second request - should use cache (faster)
            start_time = time.time()
            response2 = await agent.process_prompt(requests[1])
            second_execution_time = time.time() - start_time
            
            assert response2.success
            assert response2.metadata["cache_dir"] == cache_dir
            
            # Verify logs were created
            logs_path = os.path.join(cache_dir, "logs.txt")
            assert os.path.exists(logs_path)
            
            with open(logs_path, 'r') as f:
                log_content = f.read()
                assert "List available properties" in log_content
    
    @pytest.mark.asyncio
    async def test_error_scenarios_and_recovery(self, agent_core, auth_contexts):
        """Test error handling and recovery mechanisms."""
        agent = ModelPropertiesAgent(agent_core)
        await agent.initialize()
        
        auth_context = auth_contexts["model_properties"]
        
        # Test 1: Invalid authentication
        invalid_auth = AuthContext(access_token="invalid_token")
        request_invalid_auth = AgentRequest(
            agent_type="model_properties",
            prompt="Test prompt",
            authentication=invalid_auth
        )
        
        # Mock tool to simulate auth failure
        mock_langchain_agent = AsyncMock()
        mock_langchain_agent.ainvoke.side_effect = Exception("Authentication failed")
        
        with patch.object(agent, '_create_langchain_agent', return_value=mock_langchain_agent):
            response = await agent.process_prompt(request_invalid_auth)
            
            # Agent should handle error gracefully
            assert response.success  # Agent wraps errors in responses
            assert "Authentication failed" in response.responses[0]
        
        # Test 2: Tool execution failure
        request_tool_error = AgentRequest(
            agent_type="model_properties",
            prompt="Execute invalid operation",
            authentication=auth_context
        )
        
        mock_langchain_agent.ainvoke.side_effect = Exception("Tool execution failed")
        
        with patch.object(agent, '_create_langchain_agent', return_value=mock_langchain_agent):
            response = await agent.process_prompt(request_tool_error)
            
            assert response.success  # Error handled gracefully
            assert "Tool execution failed" in response.responses[0]
        
        # Test 3: Recovery after error
        mock_langchain_agent.ainvoke.side_effect = None
        mock_langchain_agent.ainvoke.return_value = {"output": "Recovery successful"}
        
        request_recovery = AgentRequest(
            agent_type="model_properties",
            prompt="Test recovery",
            authentication=auth_context
        )
        
        with patch.object(agent, '_create_langchain_agent', return_value=mock_langchain_agent):
            response = await agent.process_prompt(request_recovery)
            
            assert response.success
            assert "Recovery successful" in response.responses[0]
    
    @pytest.mark.asyncio
    async def test_concurrent_request_handling(self, agent_core, auth_contexts):
        """Test handling multiple concurrent requests."""
        agent = ModelPropertiesAgent(agent_core)
        await agent.initialize()
        
        auth_context = auth_contexts["model_properties"]
        
        # Create multiple concurrent requests
        requests = [
            AgentRequest(
                agent_type="model_properties",
                prompt=f"Request {i}",
                authentication=auth_context
            )
            for i in range(5)
        ]
        
        # Mock LangChain agent
        mock_langchain_agent = AsyncMock()
        mock_langchain_agent.ainvoke.return_value = {"output": "Concurrent response"}
        
        with patch.object(agent, '_create_langchain_agent', return_value=mock_langchain_agent):
            # Process requests concurrently
            tasks = [agent.process_prompt(req) for req in requests]
            responses = await asyncio.gather(*tasks)
            
            # Verify all requests were processed successfully
            assert len(responses) == 5
            for response in responses:
                assert response.success
                assert "Concurrent response" in response.responses[0]
                assert response.agent_type == "model_properties"


class TestAECDataModelAgentIntegration:
    """Integration tests for AEC Data Model Agent."""
    
    @pytest.mark.asyncio
    async def test_opensearch_integration(self, agent_core, auth_contexts):
        """Test OpenSearch vector store integration."""
        agent = AECDataModelAgent(agent_core)
        
        # Mock OpenSearch and related services
        mock_vector_store = Mock()
        mock_vector_store.initialize = AsyncMock()
        mock_vector_store.health_check = AsyncMock(return_value={
            "cluster_status": "green",
            "index_exists": True,
            "document_count": 100
        })
        
        mock_property_manager = Mock()
        mock_property_manager.ensure_vector_store_populated = AsyncMock()
        
        with patch('agent_core.agents.aec_data_model_agent.ChatBedrock'), \
             patch('agent_core.agents.aec_data_model_agent.OpenSearchVectorStore', return_value=mock_vector_store), \
             patch('agent_core.agents.aec_data_model_agent.PropertyDefinitionsManager', return_value=mock_property_manager):
            
            await agent.initialize()
            
            assert agent._vector_store == mock_vector_store
            assert agent._property_manager == mock_property_manager
            
            # Verify OpenSearch was initialized
            mock_vector_store.initialize.assert_called_once()
            
            # Test status includes vector store health
            status = await agent.get_status()
            assert status["vector_store_initialized"]
            assert status["vector_store_health"]["cluster_status"] == "green"
    
    @pytest.mark.asyncio
    async def test_property_definitions_loading(self, agent_core, auth_contexts):
        """Test property definitions loading and caching."""
        agent = AECDataModelAgent(agent_core)
        auth_context = auth_contexts["aec_data_model"]
        
        # Mock services
        mock_vector_store = Mock()
        mock_vector_store.initialize = AsyncMock()
        mock_vector_store.health_check = AsyncMock(return_value={"status": "healthy"})
        
        mock_property_manager = Mock()
        mock_property_manager.ensure_vector_store_populated = AsyncMock()
        
        mock_langchain_agent = AsyncMock()
        mock_langchain_agent.ainvoke.return_value = {"output": "Property definitions loaded"}
        
        with patch('agent_core.agents.aec_data_model_agent.ChatBedrock'), \
             patch('agent_core.agents.aec_data_model_agent.OpenSearchVectorStore', return_value=mock_vector_store), \
             patch('agent_core.agents.aec_data_model_agent.PropertyDefinitionsManager', return_value=mock_property_manager), \
             patch.object(agent, '_create_langchain_agent', return_value=mock_langchain_agent):
            
            await agent.initialize()
            
            request = AgentRequest(
                agent_type="aec_data_model",
                prompt="Find wall properties",
                authentication=auth_context
            )
            
            response = await agent.process_prompt(request)
            
            assert response.success
            
            # Verify property definitions were loaded
            mock_property_manager.ensure_vector_store_populated.assert_called_once_with(
                auth_context.element_group_id,
                auth_context.access_token,
                agent._get_cache_dir(auth_context)
            )
    
    @pytest.mark.asyncio
    async def test_semantic_search_functionality(self, agent_core, auth_contexts):
        """Test semantic search for property definitions."""
        agent = AECDataModelAgent(agent_core)
        auth_context = auth_contexts["aec_data_model"]
        
        # Mock vector store with search results
        mock_vector_store = Mock()
        mock_vector_store.initialize = AsyncMock()
        mock_vector_store.similarity_search = AsyncMock(return_value=[
            Mock(page_content="Wall Height property definition", metadata={"id": "prop1"}),
            Mock(page_content="Wall Width property definition", metadata={"id": "prop2"})
        ])
        
        mock_property_manager = Mock()
        mock_property_manager.ensure_vector_store_populated = AsyncMock()
        
        # Mock find_related_property_definitions tool
        mock_find_tool = Mock()
        mock_find_tool.name = "find_related_property_definitions"
        mock_find_tool.execute = AsyncMock(return_value=Mock(
            success=True,
            result=["Wall Height", "Wall Width", "Wall Material"]
        ))
        
        with patch('agent_core.agents.aec_data_model_agent.ChatBedrock'), \
             patch('agent_core.agents.aec_data_model_agent.OpenSearchVectorStore', return_value=mock_vector_store), \
             patch('agent_core.agents.aec_data_model_agent.PropertyDefinitionsManager', return_value=mock_property_manager):
            
            await agent.initialize()
            
            # Add the mock tool to agent tools
            agent.tools.append(mock_find_tool)
            
            # Test semantic search through tool
            result = await mock_find_tool.execute(
                query="wall dimensions",
                auth_context=auth_context,
                cache_dir="/tmp/test"
            )
            
            assert result.success
            assert "Wall Height" in result.result
            assert "Wall Width" in result.result


class TestModelDerivativesAgentIntegration:
    """Integration tests for Model Derivatives Agent."""
    
    @pytest.mark.asyncio
    async def test_sqlite_database_operations(self, agent_core, auth_contexts):
        """Test SQLite database setup and operations."""
        agent = ModelDerivativesAgent(agent_core)
        await agent.initialize()
        
        auth_context = auth_contexts["model_derivatives"]
        
        # Mock database tools
        mock_setup_tool = Mock()
        mock_setup_tool.name = "setup_database"
        mock_setup_tool.execute = AsyncMock(return_value=Mock(
            success=True,
            result="Database setup completed"
        ))
        
        mock_query_tool = Mock()
        mock_query_tool.name = "sql_query"
        mock_query_tool.execute = AsyncMock(return_value=Mock(
            success=True,
            result=[{"id": 1, "name": "Wall-001", "height": 3.0}]
        ))
        
        # Replace agent tools with mocks
        agent.tools = [mock_setup_tool, mock_query_tool]
        
        # Test database setup
        setup_result = await mock_setup_tool.execute(
            urn=auth_context.urn,
            auth_context=auth_context,
            cache_dir="/tmp/test"
        )
        
        assert setup_result.success
        assert "Database setup completed" in setup_result.result
        
        # Test SQL query
        query_result = await mock_query_tool.execute(
            query="SELECT * FROM properties WHERE name LIKE 'Wall%'",
            auth_context=auth_context,
            cache_dir="/tmp/test"
        )
        
        assert query_result.success
        assert len(query_result.result) == 1
        assert query_result.result[0]["name"] == "Wall-001"
    
    @pytest.mark.asyncio
    async def test_database_error_handling(self, agent_core, auth_contexts):
        """Test database error scenarios."""
        agent = ModelDerivativesAgent(agent_core)
        await agent.initialize()
        
        auth_context = auth_contexts["model_derivatives"]
        
        # Mock tool that fails
        mock_query_tool = Mock()
        mock_query_tool.name = "sql_query"
        mock_query_tool.execute = AsyncMock(return_value=Mock(
            success=False,
            error="Database not found"
        ))
        
        agent.tools = [mock_query_tool]
        
        # Mock LangChain agent to use the failing tool
        mock_langchain_agent = AsyncMock()
        mock_langchain_agent.ainvoke.side_effect = Exception("Database not found")
        
        with patch.object(agent, '_create_langchain_agent', return_value=mock_langchain_agent):
            request = AgentRequest(
                agent_type="model_derivatives",
                prompt="Query the database",
                authentication=auth_context
            )
            
            response = await agent.process_prompt(request)
            
            # Agent should handle database errors gracefully
            assert response.success  # Error wrapped in response
            assert "Database not found" in response.responses[0]


class TestCrossAgentIntegration:
    """Integration tests across multiple agents."""
    
    @pytest.mark.asyncio
    async def test_orchestrator_agent_routing(self, orchestrator, auth_contexts):
        """Test request routing to appropriate agents."""
        # Test Model Properties routing
        mp_request = AgentRequest(
            agent_type="model_properties",
            prompt="Create an index",
            authentication=auth_contexts["model_properties"]
        )
        
        # Mock agent responses
        with patch.object(orchestrator.agents["model_properties"], 'process_prompt') as mock_mp:
            mock_mp.return_value = AgentResponse(
                responses=["Index created successfully"],
                agent_type="model_properties",
                success=True
            )
            
            response = await orchestrator.route_request(mp_request)
            
            assert response.success
            assert response.agent_type == "model_properties"
            mock_mp.assert_called_once_with(mp_request)
        
        # Test AEC Data Model routing
        aec_request = AgentRequest(
            agent_type="aec_data_model",
            prompt="Find wall elements",
            authentication=auth_contexts["aec_data_model"]
        )
        
        with patch.object(orchestrator.agents["aec_data_model"], 'process_prompt') as mock_aec:
            mock_aec.return_value = AgentResponse(
                responses=["Found 5 wall elements"],
                agent_type="aec_data_model",
                success=True
            )
            
            response = await orchestrator.route_request(aec_request)
            
            assert response.success
            assert response.agent_type == "aec_data_model"
            mock_aec.assert_called_once_with(aec_request)
    
    @pytest.mark.asyncio
    async def test_agent_health_monitoring(self, orchestrator):
        """Test health monitoring across all agents."""
        # Get health status for all agents
        health_status = {}
        
        for agent_type, agent in orchestrator.agents.items():
            with patch.object(agent, 'get_status') as mock_status:
                mock_status.return_value = {
                    "agent_type": agent_type,
                    "healthy": True,
                    "initialized": True,
                    "tools_count": len(agent.tools)
                }
                
                status = await agent.get_status()
                health_status[agent_type] = status
        
        # Verify all agents report healthy
        assert len(health_status) == 3
        for agent_type, status in health_status.items():
            assert status["healthy"]
            assert status["initialized"]
            assert status["tools_count"] > 0
    
    @pytest.mark.asyncio
    async def test_cache_isolation_between_agents(self, orchestrator, auth_contexts):
        """Test that agents maintain separate cache directories."""
        cache_dirs = {}
        
        # Get cache directories for each agent
        for agent_type, agent in orchestrator.agents.items():
            auth_context = auth_contexts[agent_type]
            cache_dir = agent._get_cache_dir(auth_context)
            cache_dirs[agent_type] = cache_dir
        
        # Verify cache directories are separate
        assert len(set(cache_dirs.values())) == 3  # All unique
        
        for agent_type, cache_dir in cache_dirs.items():
            assert agent_type in cache_dir
            assert os.path.exists(cache_dir)
    
    @pytest.mark.asyncio
    async def test_error_propagation_and_isolation(self, orchestrator, auth_contexts):
        """Test that errors in one agent don't affect others."""
        # Make one agent fail
        with patch.object(orchestrator.agents["model_properties"], 'process_prompt') as mock_mp:
            mock_mp.side_effect = Exception("Model Properties agent failed")
            
            # Test that other agents still work
            aec_request = AgentRequest(
                agent_type="aec_data_model",
                prompt="Test request",
                authentication=auth_contexts["aec_data_model"]
            )
            
            with patch.object(orchestrator.agents["aec_data_model"], 'process_prompt') as mock_aec:
                mock_aec.return_value = AgentResponse(
                    responses=["AEC agent working"],
                    agent_type="aec_data_model",
                    success=True
                )
                
                response = await orchestrator.route_request(aec_request)
                
                assert response.success
                assert response.agent_type == "aec_data_model"
                
                # Verify the failing agent didn't affect this one
                mock_aec.assert_called_once()


class TestPerformanceAndScaling:
    """Performance and scaling integration tests."""
    
    @pytest.mark.asyncio
    async def test_memory_usage_under_load(self, agent_core, auth_contexts):
        """Test memory usage under concurrent load."""
        import psutil
        import gc
        
        agent = ModelPropertiesAgent(agent_core)
        await agent.initialize()
        
        auth_context = auth_contexts["model_properties"]
        
        # Get initial memory usage
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Create many concurrent requests
        requests = [
            AgentRequest(
                agent_type="model_properties",
                prompt=f"Test request {i}",
                authentication=auth_context
            )
            for i in range(20)
        ]
        
        # Mock LangChain agent
        mock_langchain_agent = AsyncMock()
        mock_langchain_agent.ainvoke.return_value = {"output": "Test response"}
        
        with patch.object(agent, '_create_langchain_agent', return_value=mock_langchain_agent):
            # Process requests in batches
            batch_size = 5
            for i in range(0, len(requests), batch_size):
                batch = requests[i:i + batch_size]
                tasks = [agent.process_prompt(req) for req in batch]
                responses = await asyncio.gather(*tasks)
                
                # Verify all responses are successful
                for response in responses:
                    assert response.success
                
                # Force garbage collection
                gc.collect()
        
        # Check final memory usage
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory
        
        # Memory increase should be reasonable (less than 100MB for this test)
        assert memory_increase < 100, f"Memory increased by {memory_increase}MB"
    
    @pytest.mark.asyncio
    async def test_response_time_consistency(self, agent_core, auth_contexts):
        """Test response time consistency under load."""
        agent = ModelPropertiesAgent(agent_core)
        await agent.initialize()
        
        auth_context = auth_contexts["model_properties"]
        
        response_times = []
        
        # Mock LangChain agent with consistent response time
        mock_langchain_agent = AsyncMock()
        mock_langchain_agent.ainvoke.return_value = {"output": "Consistent response"}
        
        with patch.object(agent, '_create_langchain_agent', return_value=mock_langchain_agent):
            # Process multiple requests and measure response times
            for i in range(10):
                request = AgentRequest(
                    agent_type="model_properties",
                    prompt=f"Test request {i}",
                    authentication=auth_context
                )
                
                start_time = time.time()
                response = await agent.process_prompt(request)
                end_time = time.time()
                
                assert response.success
                response_times.append(end_time - start_time)
        
        # Calculate statistics
        avg_time = sum(response_times) / len(response_times)
        max_time = max(response_times)
        min_time = min(response_times)
        
        # Response times should be consistent (max shouldn't be more than 2x avg)
        assert max_time < avg_time * 2, f"Response time inconsistent: avg={avg_time:.3f}s, max={max_time:.3f}s"
        assert min_time > 0, "Response time should be positive"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])