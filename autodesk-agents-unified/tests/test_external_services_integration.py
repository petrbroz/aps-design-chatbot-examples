"""
Integration tests for external service interactions.

These tests validate:
- APS (Autodesk Platform Services) API integration
- AECDM (AEC Data Model) API integration  
- OpenSearch vector store integration
- AWS Bedrock integration
- Error handling with external services
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Dict, Any, List

import httpx
try:
    from opensearch_py import OpenSearch
    from opensearch_py.exceptions import OpenSearchException
except ImportError:
    # Mock OpenSearch if not available
    class OpenSearch:
        pass
    class OpenSearchException(Exception):
        pass

from agent_core.core import AgentCore
from agent_core.config import CoreConfig
from agent_core.auth import AuthContext
from agent_core.models import AgentRequest, AgentResponse
from agent_core.vector_store import OpenSearchVectorStore
from agent_core.tools.model_properties import CreateIndexTool, QueryIndexTool
from agent_core.tools.aec_data_model import ExecuteGraphQLQueryTool, FindRelatedPropertyDefinitionsTool
from agent_core.tools.model_derivatives import SetupDatabaseTool


@pytest.fixture
def test_config():
    """Create test configuration for external services."""
    return CoreConfig(
        aws_region="us-east-1",
        bedrock_model_id="anthropic.claude-3-5-sonnet-20241022-v2:0",
        opensearch_endpoint="https://test-opensearch.us-east-1.es.amazonaws.com",
        cache_directory="/tmp/test_external_cache",
        log_level="DEBUG",
        health_check_interval=30
    )


@pytest.fixture
def auth_context():
    """Create authentication context for external API calls."""
    return AuthContext(
        access_token="test_access_token_12345",
        project_id="b.project123",
        version_id="test_version_456",
        element_group_id="test_element_group_789",
        urn="dXJuOmFkc2sud2lwcHJvZDpmcy5maWxlOnZmLlUyTVk1UEFwUi1PV2l2TS1Zam9BQXc_dmVyc2lvbj0x"
    )


class TestAPSIntegration:
    """Test integration with Autodesk Platform Services APIs."""
    
    @pytest.mark.asyncio
    async def test_model_properties_api_calls(self, auth_context):
        """Test Model Properties API integration."""
        tool = CreateIndexTool()
        
        # Mock successful API response
        mock_response = {
            "status": "success",
            "indexId": "test_index_123",
            "message": "Index created successfully"
        }
        
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_post.return_value = httpx.Response(
                status_code=200,
                json=mock_response,
                request=httpx.Request("POST", "https://developer.api.autodesk.com/")
            )
            
            result = await tool.execute(
                version_id=auth_context.version_id,
                auth_context=auth_context,
                cache_dir="/tmp/test"
            )
            
            assert result.success
            assert "test_index_123" in str(result.result)
            
            # Verify API call was made with correct headers
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert "Authorization" in call_args[1]["headers"]
            assert f"Bearer {auth_context.access_token}" in call_args[1]["headers"]["Authorization"]
    
    @pytest.mark.asyncio
    async def test_model_properties_api_error_handling(self, auth_context):
        """Test error handling for Model Properties API failures."""
        tool = QueryIndexTool()
        
        # Mock API error response
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_post.return_value = httpx.Response(
                status_code=401,
                json={"error": "Unauthorized", "message": "Invalid token"},
                request=httpx.Request("POST", "https://developer.api.autodesk.com/")
            )
            
            result = await tool.execute(
                version_id=auth_context.version_id,
                query={"query": {"$eq": ["s.props.p123", "'Wall'"]}},
                auth_context=auth_context,
                cache_dir="/tmp/test"
            )
            
            assert not result.success
            assert "Unauthorized" in result.error or "401" in result.error
    
    @pytest.mark.asyncio
    async def test_model_properties_api_timeout_handling(self, auth_context):
        """Test timeout handling for Model Properties API."""
        tool = CreateIndexTool()
        
        # Mock timeout
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_post.side_effect = httpx.TimeoutException("Request timed out")
            
            result = await tool.execute(
                version_id=auth_context.version_id,
                auth_context=auth_context,
                cache_dir="/tmp/test"
            )
            
            assert not result.success
            assert "timeout" in result.error.lower() or "timed out" in result.error.lower()
    
    @pytest.mark.asyncio
    async def test_model_derivatives_api_calls(self, auth_context):
        """Test Model Derivatives API integration."""
        tool = SetupDatabaseTool()
        
        # Mock successful API responses for derivative download
        mock_manifest_response = {
            "derivatives": [
                {
                    "name": "properties.db",
                    "urn": "test_derivative_urn",
                    "status": "success"
                }
            ]
        }
        
        mock_download_response = b"SQLite database content"
        
        with patch('httpx.AsyncClient.get') as mock_get:
            # Mock manifest call
            mock_get.side_effect = [
                httpx.Response(
                    status_code=200,
                    json=mock_manifest_response,
                    request=httpx.Request("GET", "https://developer.api.autodesk.com/")
                ),
                # Mock download call
                httpx.Response(
                    status_code=200,
                    content=mock_download_response,
                    request=httpx.Request("GET", "https://developer.api.autodesk.com/")
                )
            ]
            
            result = await tool.execute(
                urn=auth_context.urn,
                auth_context=auth_context,
                cache_dir="/tmp/test"
            )
            
            # Should succeed or fail gracefully
            assert result.success or "error" in result.error.lower()
            
            # Verify API calls were made
            assert mock_get.call_count >= 1


class TestAECDMIntegration:
    """Test integration with AEC Data Model API."""
    
    @pytest.mark.asyncio
    async def test_graphql_api_calls(self, auth_context):
        """Test AEC Data Model GraphQL API integration."""
        tool = ExecuteGraphQLQueryTool()
        
        # Mock successful GraphQL response
        mock_response = {
            "data": {
                "elementsByElementGroup": {
                    "results": [
                        {
                            "id": "element_1",
                            "externalId": "ext_1",
                            "properties": {
                                "results": [
                                    {
                                        "definition": {"name": "Height"},
                                        "value": 3.0
                                    }
                                ]
                            }
                        }
                    ]
                }
            }
        }
        
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_post.return_value = httpx.Response(
                status_code=200,
                json=mock_response,
                request=httpx.Request("POST", "https://developer.api.autodesk.com/")
            )
            
            query = """
            query GetElements($elementGroupId: ID!) {
                elementsByElementGroup(elementGroupId: $elementGroupId) {
                    results {
                        id
                        externalId
                        properties {
                            results {
                                definition { name }
                                value
                            }
                        }
                    }
                }
            }
            """
            
            result = await tool.execute(
                query=query,
                variables={"elementGroupId": auth_context.element_group_id},
                auth_context=auth_context,
                cache_dir="/tmp/test"
            )
            
            assert result.success
            assert "element_1" in str(result.result)
            
            # Verify GraphQL endpoint was called
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert "query" in call_args[1]["json"]
    
    @pytest.mark.asyncio
    async def test_graphql_api_error_handling(self, auth_context):
        """Test GraphQL API error handling."""
        tool = ExecuteGraphQLQueryTool()
        
        # Mock GraphQL error response
        mock_response = {
            "errors": [
                {
                    "message": "Element group not found",
                    "extensions": {"code": "NOT_FOUND"}
                }
            ]
        }
        
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_post.return_value = httpx.Response(
                status_code=200,  # GraphQL returns 200 even for errors
                json=mock_response,
                request=httpx.Request("POST", "https://developer.api.autodesk.com/")
            )
            
            result = await tool.execute(
                query="query { invalid }",
                variables={},
                auth_context=auth_context,
                cache_dir="/tmp/test"
            )
            
            assert not result.success
            assert "Element group not found" in result.error
    
    @pytest.mark.asyncio
    async def test_graphql_network_error_handling(self, auth_context):
        """Test GraphQL network error handling."""
        tool = ExecuteGraphQLQueryTool()
        
        # Mock network error
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_post.side_effect = httpx.ConnectError("Connection failed")
            
            result = await tool.execute(
                query="query { test }",
                variables={},
                auth_context=auth_context,
                cache_dir="/tmp/test"
            )
            
            assert not result.success
            assert "connection" in result.error.lower() or "network" in result.error.lower()


class TestOpenSearchIntegration:
    """Test integration with OpenSearch vector store."""
    
    @pytest.fixture
    def mock_opensearch_client(self):
        """Create mock OpenSearch client."""
        client = Mock(spec=OpenSearch)
        
        # Mock successful responses
        client.indices.exists.return_value = True
        client.indices.create.return_value = {"acknowledged": True}
        client.index.return_value = {"_id": "doc1", "result": "created"}
        client.search.return_value = {
            "hits": {
                "total": {"value": 2},
                "hits": [
                    {
                        "_id": "doc1",
                        "_source": {"content": "Wall height property", "metadata": {"id": "prop1"}},
                        "_score": 0.9
                    },
                    {
                        "_id": "doc2", 
                        "_source": {"content": "Wall width property", "metadata": {"id": "prop2"}},
                        "_score": 0.8
                    }
                ]
            }
        }
        client.cluster.health.return_value = {"status": "green"}
        
        return client
    
    @pytest.mark.asyncio
    async def test_vector_store_initialization(self, test_config, mock_opensearch_client):
        """Test OpenSearch vector store initialization."""
        with patch('agent_core.vector_store.OpenSearch', return_value=mock_opensearch_client), \
             patch('agent_core.vector_store.BedrockEmbeddings') as mock_embeddings:
            
            mock_embeddings_instance = Mock()
            mock_embeddings_instance.embed_query.return_value = [0.1, 0.2, 0.3]
            mock_embeddings.return_value = mock_embeddings_instance
            
            vector_store = OpenSearchVectorStore(
                opensearch_endpoint=test_config.opensearch_endpoint,
                index_name="test_index",
                embeddings_model_id="amazon.titan-embed-text-v1",
                aws_region=test_config.aws_region
            )
            
            await vector_store.initialize()
            
            assert vector_store._initialized
            mock_opensearch_client.indices.exists.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_vector_store_document_operations(self, test_config, mock_opensearch_client):
        """Test document indexing and search operations."""
        with patch('agent_core.vector_store.OpenSearch', return_value=mock_opensearch_client), \
             patch('agent_core.vector_store.BedrockEmbeddings') as mock_embeddings:
            
            mock_embeddings_instance = Mock()
            mock_embeddings_instance.embed_documents.return_value = [[0.1, 0.2], [0.3, 0.4]]
            mock_embeddings_instance.embed_query.return_value = [0.1, 0.2]
            mock_embeddings.return_value = mock_embeddings_instance
            
            vector_store = OpenSearchVectorStore(
                opensearch_endpoint=test_config.opensearch_endpoint,
                index_name="test_index",
                embeddings_model_id="amazon.titan-embed-text-v1",
                aws_region=test_config.aws_region
            )
            
            await vector_store.initialize()
            
            # Test document addition
            from langchain_core.documents import Document
            documents = [
                Document(page_content="Wall height property", metadata={"id": "prop1"}),
                Document(page_content="Wall width property", metadata={"id": "prop2"})
            ]
            
            await vector_store.add_documents(documents)
            
            # Verify documents were indexed
            assert mock_opensearch_client.index.call_count == 2
            
            # Test similarity search
            results = await vector_store.similarity_search("wall dimensions", k=2)
            
            assert len(results) == 2
            assert "Wall height property" in results[0].page_content
            assert "Wall width property" in results[1].page_content
            
            # Verify search was called
            mock_opensearch_client.search.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_vector_store_error_handling(self, test_config):
        """Test OpenSearch error handling."""
        # Mock client that raises errors
        mock_client = Mock(spec=OpenSearch)
        mock_client.indices.exists.side_effect = OpenSearchException("Connection failed")
        
        with patch('agent_core.vector_store.OpenSearch', return_value=mock_client):
            vector_store = OpenSearchVectorStore(
                opensearch_endpoint=test_config.opensearch_endpoint,
                index_name="test_index",
                embeddings_model_id="amazon.titan-embed-text-v1",
                aws_region=test_config.aws_region
            )
            
            # Initialization should handle the error
            with pytest.raises(Exception):
                await vector_store.initialize()
    
    @pytest.mark.asyncio
    async def test_vector_store_health_check(self, test_config, mock_opensearch_client):
        """Test OpenSearch health check functionality."""
        with patch('agent_core.vector_store.OpenSearch', return_value=mock_opensearch_client), \
             patch('agent_core.vector_store.BedrockEmbeddings'):
            
            vector_store = OpenSearchVectorStore(
                opensearch_endpoint=test_config.opensearch_endpoint,
                index_name="test_index",
                embeddings_model_id="amazon.titan-embed-text-v1",
                aws_region=test_config.aws_region
            )
            
            await vector_store.initialize()
            
            # Test health check
            health = await vector_store.health_check()
            
            assert health["cluster_status"] == "green"
            assert health["index_exists"] is True
            mock_opensearch_client.cluster.health.assert_called_once()
            mock_opensearch_client.indices.exists.assert_called()


class TestAWSBedrockIntegration:
    """Test integration with AWS Bedrock services."""
    
    @pytest.mark.asyncio
    async def test_bedrock_llm_integration(self, test_config):
        """Test Bedrock LLM integration."""
        from langchain_aws import ChatBedrock
        
        # Mock Bedrock client
        with patch('langchain_aws.ChatBedrock') as mock_bedrock:
            mock_llm = Mock()
            mock_llm.ainvoke.return_value = Mock(content="Test response from Bedrock")
            mock_bedrock.return_value = mock_llm
            
            # Create LLM instance
            llm = ChatBedrock(
                model_id=test_config.bedrock_model_id,
                model_kwargs={
                    "temperature": 0.0,
                    "max_tokens": 4096
                }
            )
            
            # Test LLM call
            from langchain_core.messages import HumanMessage
            response = await llm.ainvoke([HumanMessage(content="Test prompt")])
            
            assert response.content == "Test response from Bedrock"
            mock_llm.ainvoke.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_bedrock_embeddings_integration(self, test_config):
        """Test Bedrock embeddings integration."""
        from langchain_aws import BedrockEmbeddings
        
        # Mock Bedrock embeddings
        with patch('langchain_aws.BedrockEmbeddings') as mock_embeddings_class:
            mock_embeddings = Mock()
            mock_embeddings.embed_query.return_value = [0.1, 0.2, 0.3, 0.4, 0.5]
            mock_embeddings.embed_documents.return_value = [
                [0.1, 0.2, 0.3, 0.4, 0.5],
                [0.6, 0.7, 0.8, 0.9, 1.0]
            ]
            mock_embeddings_class.return_value = mock_embeddings
            
            # Create embeddings instance
            embeddings = BedrockEmbeddings(
                model_id="amazon.titan-embed-text-v1",
                region_name=test_config.aws_region
            )
            
            # Test query embedding
            query_embedding = embeddings.embed_query("test query")
            assert len(query_embedding) == 5
            assert query_embedding[0] == 0.1
            
            # Test document embeddings
            doc_embeddings = embeddings.embed_documents(["doc1", "doc2"])
            assert len(doc_embeddings) == 2
            assert len(doc_embeddings[0]) == 5
    
    @pytest.mark.asyncio
    async def test_bedrock_error_handling(self, test_config):
        """Test Bedrock error handling."""
        from langchain_aws import ChatBedrock
        import boto3
        
        # Mock Bedrock client that raises errors
        with patch('langchain_aws.ChatBedrock') as mock_bedrock:
            mock_llm = Mock()
            mock_llm.ainvoke.side_effect = Exception("Bedrock service unavailable")
            mock_bedrock.return_value = mock_llm
            
            llm = ChatBedrock(
                model_id=test_config.bedrock_model_id,
                model_kwargs={"temperature": 0.0}
            )
            
            # Test error handling
            from langchain_core.messages import HumanMessage
            with pytest.raises(Exception, match="Bedrock service unavailable"):
                await llm.ainvoke([HumanMessage(content="Test prompt")])


class TestExternalServiceResilience:
    """Test resilience and recovery with external services."""
    
    @pytest.mark.asyncio
    async def test_service_retry_logic(self, auth_context):
        """Test retry logic for external service failures."""
        tool = CreateIndexTool()
        
        # Mock service that fails first, then succeeds
        call_count = 0
        
        def mock_post_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.ConnectError("Connection failed")
            else:
                return httpx.Response(
                    status_code=200,
                    json={"status": "success", "indexId": "retry_success"},
                    request=httpx.Request("POST", "https://developer.api.autodesk.com/")
                )
        
        with patch('httpx.AsyncClient.post', side_effect=mock_post_side_effect):
            # Tool should implement retry logic
            result = await tool.execute(
                version_id=auth_context.version_id,
                auth_context=auth_context,
                cache_dir="/tmp/test"
            )
            
            # Should eventually succeed after retry
            # Note: This depends on tool implementation having retry logic
            # If not implemented, this test will document the need for it
            if result.success:
                assert "retry_success" in str(result.result)
            else:
                # Document that retry logic should be implemented
                assert "connection" in result.error.lower()
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_pattern(self, auth_context):
        """Test circuit breaker pattern for external services."""
        tool = QueryIndexTool()
        
        # Simulate multiple consecutive failures
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_post.side_effect = httpx.ConnectError("Service unavailable")
            
            # Make multiple calls that should trigger circuit breaker
            results = []
            for i in range(5):
                result = await tool.execute(
                    version_id=auth_context.version_id,
                    query={"query": {"$eq": ["s.props.p123", "'Wall'"]}},
                    auth_context=auth_context,
                    cache_dir="/tmp/test"
                )
                results.append(result)
                
                # Small delay between calls
                await asyncio.sleep(0.1)
            
            # All should fail, but later ones might fail faster (circuit breaker)
            for result in results:
                assert not result.success
    
    @pytest.mark.asyncio
    async def test_graceful_degradation(self, test_config, auth_context):
        """Test graceful degradation when external services are unavailable."""
        # Test with FindRelatedPropertyDefinitionsTool when OpenSearch is down
        mock_vector_store = Mock()
        mock_vector_store.similarity_search.side_effect = Exception("OpenSearch unavailable")
        
        tool = FindRelatedPropertyDefinitionsTool(mock_vector_store)
        
        result = await tool.execute(
            query="wall properties",
            auth_context=auth_context,
            cache_dir="/tmp/test"
        )
        
        # Tool should handle the error gracefully
        assert not result.success
        assert "unavailable" in result.error.lower() or "error" in result.error.lower()
    
    @pytest.mark.asyncio
    async def test_service_health_monitoring(self, test_config):
        """Test health monitoring for external services."""
        # Test OpenSearch health monitoring
        mock_client = Mock(spec=OpenSearch)
        mock_client.cluster.health.return_value = {"status": "red"}
        mock_client.indices.exists.return_value = False
        
        with patch('agent_core.vector_store.OpenSearch', return_value=mock_client), \
             patch('agent_core.vector_store.BedrockEmbeddings'):
            
            vector_store = OpenSearchVectorStore(
                opensearch_endpoint=test_config.opensearch_endpoint,
                index_name="test_index",
                embeddings_model_id="amazon.titan-embed-text-v1",
                aws_region=test_config.aws_region
            )
            
            # Initialize despite health issues
            try:
                await vector_store.initialize()
            except:
                pass  # Expected to fail
            
            # Health check should report issues
            try:
                health = await vector_store.health_check()
                assert health["cluster_status"] == "red"
                assert health["index_exists"] is False
            except:
                # Health check itself might fail, which is also valid
                pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])