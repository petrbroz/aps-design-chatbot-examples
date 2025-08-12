"""
Pytest configuration and shared fixtures for integration and end-to-end tests.
"""

import pytest
import asyncio
import tempfile
import os
import shutil
from typing import Dict, Any, AsyncGenerator
from unittest.mock import Mock, AsyncMock, patch

from agent_core.core import AgentCore
from agent_core.config import CoreConfig
from agent_core.auth import AuthContext
from agent_core.models import AgentRequest, AgentResponse


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_cache_dir():
    """Create a temporary cache directory for tests."""
    temp_dir = tempfile.mkdtemp(prefix="agent_test_cache_")
    yield temp_dir
    # Cleanup
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def test_config(temp_cache_dir):
    """Create test configuration with temporary cache directory."""
    return CoreConfig(
        aws_region="us-east-1",
        bedrock_model_id="anthropic.claude-3-5-sonnet-20241022-v2:0",
        opensearch_endpoint="https://test-opensearch.us-east-1.es.amazonaws.com",
        cache_directory=temp_cache_dir,
        log_level="DEBUG",
        health_check_interval=30
    )


@pytest.fixture
def mock_aws_services():
    """Mock AWS services to avoid real API calls."""
    with patch('boto3.client') as mock_boto_client, \
         patch('langchain_aws.ChatBedrock') as mock_bedrock, \
         patch('langchain_aws.BedrockEmbeddings') as mock_embeddings:
        
        # Mock Bedrock LLM
        mock_llm = Mock()
        mock_llm.ainvoke = AsyncMock(return_value=Mock(content="Mocked LLM response"))
        mock_bedrock.return_value = mock_llm
        
        # Mock Bedrock Embeddings
        mock_embeddings_instance = Mock()
        mock_embeddings_instance.embed_query = Mock(return_value=[0.1, 0.2, 0.3, 0.4, 0.5])
        mock_embeddings_instance.embed_documents = Mock(return_value=[[0.1, 0.2], [0.3, 0.4]])
        mock_embeddings.return_value = mock_embeddings_instance
        
        # Mock boto3 client
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        
        yield {
            "bedrock": mock_bedrock,
            "embeddings": mock_embeddings,
            "boto_client": mock_boto_client
        }


@pytest.fixture
def mock_opensearch():
    """Mock OpenSearch client."""
    with patch('opensearch_py.OpenSearch') as mock_opensearch_class:
        mock_client = Mock()
        
        # Mock successful responses
        mock_client.indices.exists.return_value = True
        mock_client.indices.create.return_value = {"acknowledged": True}
        mock_client.index.return_value = {"_id": "doc1", "result": "created"}
        mock_client.search.return_value = {
            "hits": {
                "total": {"value": 2},
                "hits": [
                    {
                        "_id": "doc1",
                        "_source": {"content": "Test document 1", "metadata": {"id": "1"}},
                        "_score": 0.9
                    },
                    {
                        "_id": "doc2",
                        "_source": {"content": "Test document 2", "metadata": {"id": "2"}},
                        "_score": 0.8
                    }
                ]
            }
        }
        mock_client.cluster.health.return_value = {"status": "green"}
        
        mock_opensearch_class.return_value = mock_client
        yield mock_client


@pytest.fixture
def mock_external_apis():
    """Mock external API calls (APS, AECDM)."""
    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = Mock()
        
        # Mock successful API responses
        async def mock_post(*args, **kwargs):
            url = args[0] if args else kwargs.get('url', '')
            
            if 'model-properties' in url:
                return Mock(
                    status_code=200,
                    json=lambda: {"status": "success", "data": "Model Properties response"}
                )
            elif 'aec-data-model' in url or 'graphql' in url:
                return Mock(
                    status_code=200,
                    json=lambda: {
                        "data": {
                            "elements": [
                                {"id": "elem1", "properties": {"name": "Wall-001"}}
                            ]
                        }
                    }
                )
            else:
                return Mock(
                    status_code=200,
                    json=lambda: {"status": "success"}
                )
        
        async def mock_get(*args, **kwargs):
            return Mock(
                status_code=200,
                content=b"Mock file content",
                json=lambda: {"status": "success"}
            )
        
        mock_client.post = mock_post
        mock_client.get = mock_get
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        yield mock_client


@pytest.fixture
def sample_auth_contexts():
    """Create sample authentication contexts for testing."""
    return {
        "model_properties": AuthContext(
            access_token="test_mp_token_12345",
            project_id="b.project123",
            version_id="test_version_456"
        ),
        "aec_data_model": AuthContext(
            access_token="test_aec_token_12345",
            element_group_id="test_element_group_789"
        ),
        "model_derivatives": AuthContext(
            access_token="test_md_token_12345",
            urn="dXJuOmFkc2sud2lwcHJvZDpmcy5maWxlOnZmLlUyTVk1UEFwUi1PV2l2TS1Zam9BQXc_dmVyc2lvbj0x"
        )
    }


@pytest.fixture
def sample_requests(sample_auth_contexts):
    """Create sample agent requests for testing."""
    return {
        "model_properties": AgentRequest(
            agent_type="model_properties",
            prompt="Create an index and list all wall properties",
            authentication=sample_auth_contexts["model_properties"],
            context={"test": True},
            metadata={"source": "test"}
        ),
        "aec_data_model": AgentRequest(
            agent_type="aec_data_model",
            prompt="Find all door elements and their properties",
            authentication=sample_auth_contexts["aec_data_model"],
            context={"test": True},
            metadata={"source": "test"}
        ),
        "model_derivatives": AgentRequest(
            agent_type="model_derivatives",
            prompt="Setup database and find elements with area > 10m²",
            authentication=sample_auth_contexts["model_derivatives"],
            context={"test": True},
            metadata={"source": "test"}
        )
    }


@pytest.fixture
def sample_responses():
    """Create sample agent responses for testing."""
    return {
        "model_properties": AgentResponse(
            responses=[
                "I'll create an index and list wall properties for you.",
                "Index created successfully with ID: idx_test_123",
                "Found wall properties: Name, Height, Width, Material, Thickness"
            ],
            agent_type="model_properties",
            success=True,
            execution_time=2.5,
            metadata={
                "tools_used": ["create_index", "list_index_properties"],
                "cache_hit": False,
                "index_id": "idx_test_123"
            },
            request_id="req_mp_123"
        ),
        "aec_data_model": AgentResponse(
            responses=[
                "I'll search for door elements and their properties.",
                "Found 8 door elements in the design.",
                "Door properties: Height (2.1m avg), Width (0.9m avg), Material (Wood, Steel)"
            ],
            agent_type="aec_data_model",
            success=True,
            execution_time=1.8,
            metadata={
                "tools_used": ["execute_graphql_query", "find_related_property_definitions"],
                "elements_found": 8,
                "vector_search_used": True
            },
            request_id="req_aec_123"
        ),
        "model_derivatives": AgentResponse(
            responses=[
                "I'll setup the database and execute your query.",
                "Database setup completed. Properties loaded: 1,247 elements",
                "Found 23 elements with area > 10 m²"
            ],
            agent_type="model_derivatives",
            success=True,
            execution_time=3.2,
            metadata={
                "tools_used": ["setup_database", "sql_query"],
                "database_size": "2.1MB",
                "query_results": 23
            },
            request_id="req_md_123"
        )
    }


@pytest.fixture
async def agent_core_with_mocks(test_config, mock_aws_services, mock_opensearch, mock_external_apis):
    """Create AgentCore with all external services mocked."""
    core = AgentCore(test_config)
    
    # Initialize with mocked services
    await core.initialize()
    
    yield core
    
    # Cleanup
    await core.shutdown()


@pytest.fixture
def integration_test_markers():
    """Provide markers for different types of integration tests."""
    return {
        "unit": pytest.mark.unit,
        "integration": pytest.mark.integration,
        "e2e": pytest.mark.e2e,
        "slow": pytest.mark.slow,
        "external": pytest.mark.external  # Tests that require external services
    }


# Pytest configuration
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "e2e: End-to-end tests")
    config.addinivalue_line("markers", "slow: Slow running tests")
    config.addinivalue_line("markers", "external: Tests requiring external services")


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers based on test file names."""
    for item in items:
        # Add markers based on test file names
        if "test_integration" in item.nodeid:
            item.add_marker(pytest.mark.integration)
        elif "test_end_to_end" in item.nodeid:
            item.add_marker(pytest.mark.e2e)
        elif "test_external_services" in item.nodeid:
            item.add_marker(pytest.mark.external)
        
        # Mark slow tests
        if any(keyword in item.nodeid for keyword in ["performance", "load", "concurrent"]):
            item.add_marker(pytest.mark.slow)


# Helper functions for tests
def create_mock_tool_result(success: bool = True, result: Any = None, error: str = None):
    """Create a mock tool result for testing."""
    from agent_core.models import ToolResult
    
    return ToolResult(
        tool_name="mock_tool",
        success=success,
        result=result if success else None,
        error=error if not success else None,
        execution_time=0.1,
        metadata={"test": True}
    )


def assert_agent_response_valid(response: AgentResponse, expected_agent_type: str):
    """Assert that an agent response is valid."""
    assert isinstance(response, AgentResponse)
    assert response.agent_type == expected_agent_type
    assert isinstance(response.responses, list)
    assert len(response.responses) > 0
    assert isinstance(response.execution_time, (int, float))
    assert response.execution_time >= 0
    assert isinstance(response.metadata, dict)
    assert isinstance(response.success, bool)


def assert_auth_context_valid(auth_context: AuthContext):
    """Assert that an authentication context is valid."""
    assert isinstance(auth_context, AuthContext)
    assert auth_context.access_token is not None
    assert len(auth_context.access_token) > 0