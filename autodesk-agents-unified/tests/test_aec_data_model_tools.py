"""
Unit tests for AEC Data Model tools.
"""

import pytest
import json
import os
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from langchain_core.documents import Document

from agent_core.tools.aec_data_model import (
    ExecuteGraphQLQueryTool,
    GetElementCategoriesTool,
    ExecuteJQQueryTool,
    FindRelatedPropertyDefinitionsTool,
    PropertyDefinitionsManager
)
from agent_core.auth import AuthContext
from agent_core.models import ToolResult


@pytest.fixture
def auth_context():
    """Create a mock authentication context."""
    return AuthContext(
        access_token="test_token",
        element_group_id="test_element_group_id"
    )


@pytest.fixture
def mock_vector_store():
    """Create a mock vector store."""
    store = Mock()
    store._initialized = True
    store.initialize = AsyncMock()
    store.similarity_search = AsyncMock(return_value=[
        Document(
            page_content="Property Name: Test Property\nID: prop123\nDescription: Test description\nUnits: mm",
            metadata={"_score": 0.95, "_id": "doc1", "property_id": "prop123"}
        )
    ])
    store.add_documents = AsyncMock(return_value=["doc1", "doc2"])
    return store


class TestExecuteGraphQLQueryTool:
    """Test cases for ExecuteGraphQLQueryTool."""
    
    def test_initialization(self):
        """Test tool initialization."""
        tool = ExecuteGraphQLQueryTool()
        assert tool.name == "execute_graphql_query"
        assert "GraphQL query" in tool.description
        assert tool.aecdm_endpoint == "https://developer.api.autodesk.com/aec/graphql"
    
    def test_parameters_schema(self):
        """Test parameters schema."""
        tool = ExecuteGraphQLQueryTool()
        schema = tool._get_parameters_schema()
        
        assert schema["type"] == "object"
        assert "query" in schema["properties"]
        assert schema["required"] == ["query"]
    
    @pytest.mark.asyncio
    async def test_execute_success(self, auth_context):
        """Test successful GraphQL query execution."""
        tool = ExecuteGraphQLQueryTool()
        
        mock_client = Mock()
        mock_client.execute_async = AsyncMock(return_value={"data": {"test": "result"}})
        
        with patch('agent_core.tools.aec_data_model.Client', return_value=mock_client), \
             patch('agent_core.tools.aec_data_model.AIOHTTPTransport'), \
             patch('agent_core.tools.aec_data_model.gql') as mock_gql:
            
            result = await tool.execute(
                query="query { test }",
                auth_context=auth_context
            )
            
            assert result.success is True
            assert result.result == {"data": {"test": "result"}}
            mock_gql.assert_called_once_with("query { test }")
    
    @pytest.mark.asyncio
    async def test_execute_no_auth(self):
        """Test execution without authentication."""
        tool = ExecuteGraphQLQueryTool()
        
        result = await tool.execute(query="query { test }", auth_context=None)
        
        assert result.success is False
        assert "Authentication context" in result.error
    
    @pytest.mark.asyncio
    async def test_execute_large_response(self, auth_context):
        """Test handling of large responses."""
        tool = ExecuteGraphQLQueryTool()
        
        # Create a large response that exceeds the limit
        large_data = {"data": "x" * (tool.max_response_size + 1000)}
        
        mock_client = Mock()
        mock_client.execute_async = AsyncMock(return_value=large_data)
        
        with patch('agent_core.tools.aec_data_model.Client', return_value=mock_client), \
             patch('agent_core.tools.aec_data_model.AIOHTTPTransport'), \
             patch('agent_core.tools.aec_data_model.gql'):
            
            result = await tool.execute(
                query="query { test }",
                auth_context=auth_context
            )
            
            assert result.success is False
            assert "too large" in result.error
    
    @pytest.mark.asyncio
    async def test_execute_api_error(self, auth_context):
        """Test handling of API errors."""
        tool = ExecuteGraphQLQueryTool()
        
        mock_client = Mock()
        mock_client.execute_async = AsyncMock(side_effect=Exception("API Error"))
        
        with patch('agent_core.tools.aec_data_model.Client', return_value=mock_client), \
             patch('agent_core.tools.aec_data_model.AIOHTTPTransport'), \
             patch('agent_core.tools.aec_data_model.gql'):
            
            result = await tool.execute(
                query="query { test }",
                auth_context=auth_context
            )
            
            assert result.success is False
            assert "API Error" in result.error


class TestGetElementCategoriesTool:
    """Test cases for GetElementCategoriesTool."""
    
    def test_initialization(self):
        """Test tool initialization."""
        tool = GetElementCategoriesTool()
        assert tool.name == "get_element_categories"
        assert "element categories" in tool.description
    
    def test_parameters_schema(self):
        """Test parameters schema."""
        tool = GetElementCategoriesTool()
        schema = tool._get_parameters_schema()
        
        assert schema["type"] == "object"
        assert schema["required"] == []
    
    @pytest.mark.asyncio
    async def test_execute_from_cache(self, auth_context, tmp_path):
        """Test execution with cached data."""
        tool = GetElementCategoriesTool()
        
        # Create cache file
        cache_dir = str(tmp_path)
        categories_cache_path = os.path.join(cache_dir, "categories.json")
        test_categories = ["Walls", "Doors", "Windows"]
        
        with open(categories_cache_path, 'w') as f:
            json.dump(test_categories, f)
        
        result = await tool.execute(
            auth_context=auth_context,
            cache_dir=cache_dir
        )
        
        assert result.success is True
        assert result.result == test_categories
    
    @pytest.mark.asyncio
    async def test_execute_from_api(self, auth_context, tmp_path):
        """Test execution fetching from API."""
        tool = GetElementCategoriesTool()
        cache_dir = str(tmp_path)
        
        # Mock API response
        mock_response = {
            "elementsByElementGroup": {
                "pagination": {"cursor": None},
                "results": [
                    {"properties": {"results": [{"value": "Walls"}]}},
                    {"properties": {"results": [{"value": "Doors"}]}}
                ]
            }
        }
        
        mock_client = Mock()
        mock_client.execute_async = AsyncMock(return_value=mock_response)
        
        with patch('agent_core.tools.aec_data_model.Client', return_value=mock_client), \
             patch('agent_core.tools.aec_data_model.AIOHTTPTransport'), \
             patch('agent_core.tools.aec_data_model.gql'):
            
            result = await tool.execute(
                auth_context=auth_context,
                cache_dir=cache_dir
            )
            
            assert result.success is True
            assert "Walls" in result.result
            assert "Doors" in result.result
            
            # Check that cache file was created
            cache_file = os.path.join(cache_dir, "categories.json")
            assert os.path.exists(cache_file)
    
    @pytest.mark.asyncio
    async def test_execute_no_auth(self, tmp_path):
        """Test execution without authentication."""
        tool = GetElementCategoriesTool()
        
        result = await tool.execute(
            auth_context=None,
            cache_dir=str(tmp_path)
        )
        
        assert result.success is False
        assert "Authentication context" in result.error
    
    @pytest.mark.asyncio
    async def test_execute_no_element_group_id(self, tmp_path):
        """Test execution without element group ID."""
        tool = GetElementCategoriesTool()
        auth_context = AuthContext(access_token="test_token")  # No element_group_id
        
        result = await tool.execute(
            auth_context=auth_context,
            cache_dir=str(tmp_path)
        )
        
        assert result.success is False
        assert "Element group ID" in result.error


class TestExecuteJQQueryTool:
    """Test cases for ExecuteJQQueryTool."""
    
    def test_initialization(self):
        """Test tool initialization."""
        tool = ExecuteJQQueryTool()
        assert tool.name == "execute_jq_query"
        assert "jq query" in tool.description
    
    def test_parameters_schema(self):
        """Test parameters schema."""
        tool = ExecuteJQQueryTool()
        schema = tool._get_parameters_schema()
        
        assert schema["type"] == "object"
        assert "query" in schema["properties"]
        assert "input_json" in schema["properties"]
        assert set(schema["required"]) == {"query", "input_json"}
    
    @pytest.mark.asyncio
    async def test_execute_success(self):
        """Test successful jq query execution."""
        tool = ExecuteJQQueryTool()
        
        input_json = '{"name": "test", "value": 42}'
        query = ".name"
        
        result = await tool.execute(query=query, input_json=input_json)
        
        assert result.success is True
        assert result.result == ["test"]
    
    @pytest.mark.asyncio
    async def test_execute_complex_query(self):
        """Test complex jq query."""
        tool = ExecuteJQQueryTool()
        
        input_json = '{"items": [{"name": "a", "value": 1}, {"name": "b", "value": 2}]}'
        query = ".items[] | select(.value > 1) | .name"
        
        result = await tool.execute(query=query, input_json=input_json)
        
        assert result.success is True
        assert result.result == ["b"]
    
    @pytest.mark.asyncio
    async def test_execute_invalid_json(self):
        """Test execution with invalid JSON."""
        tool = ExecuteJQQueryTool()
        
        result = await tool.execute(query=".name", input_json="invalid json")
        
        assert result.success is False
        assert "jq query execution failed" in result.error
    
    @pytest.mark.asyncio
    async def test_execute_invalid_query(self):
        """Test execution with invalid jq query."""
        tool = ExecuteJQQueryTool()
        
        result = await tool.execute(query="invalid query syntax", input_json='{"test": true}')
        
        assert result.success is False
        assert "jq query execution failed" in result.error


class TestFindRelatedPropertyDefinitionsTool:
    """Test cases for FindRelatedPropertyDefinitionsTool."""
    
    def test_initialization(self, mock_vector_store):
        """Test tool initialization."""
        tool = FindRelatedPropertyDefinitionsTool(mock_vector_store)
        assert tool.name == "find_related_property_definitions"
        assert "property definitions" in tool.description
        assert tool.vector_store == mock_vector_store
    
    def test_parameters_schema(self, mock_vector_store):
        """Test parameters schema."""
        tool = FindRelatedPropertyDefinitionsTool(mock_vector_store)
        schema = tool._get_parameters_schema()
        
        assert schema["type"] == "object"
        assert "query" in schema["properties"]
        assert "k" in schema["properties"]
        assert schema["required"] == ["query"]
    
    @pytest.mark.asyncio
    async def test_execute_success(self, mock_vector_store):
        """Test successful property definition search."""
        tool = FindRelatedPropertyDefinitionsTool(mock_vector_store)
        
        result = await tool.execute(query="wall properties", k=5)
        
        assert result.success is True
        assert "query" in result.result
        assert "results_count" in result.result
        assert "properties" in result.result
        assert result.result["results_count"] == 1
        
        # Check property parsing
        prop = result.result["properties"][0]
        assert prop["name"] == "Test Property"
        assert prop["property_id"] == "prop123"
        assert prop["description"] == "Test description"
        assert prop["units"] == "mm"
    
    @pytest.mark.asyncio
    async def test_execute_uninitialized_vector_store(self, mock_vector_store):
        """Test execution with uninitialized vector store."""
        mock_vector_store._initialized = False
        tool = FindRelatedPropertyDefinitionsTool(mock_vector_store)
        
        result = await tool.execute(query="test query")
        
        assert result.success is True
        mock_vector_store.initialize.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_execute_vector_store_error(self, mock_vector_store):
        """Test handling of vector store errors."""
        mock_vector_store.similarity_search.side_effect = Exception("Vector store error")
        tool = FindRelatedPropertyDefinitionsTool(mock_vector_store)
        
        result = await tool.execute(query="test query")
        
        assert result.success is False
        assert "Vector store error" in result.error


class TestPropertyDefinitionsManager:
    """Test cases for PropertyDefinitionsManager."""
    
    @pytest.fixture
    def manager(self, mock_vector_store):
        """Create PropertyDefinitionsManager instance."""
        return PropertyDefinitionsManager(mock_vector_store)
    
    @pytest.mark.asyncio
    async def test_get_property_definitions_from_cache(self, manager, tmp_path):
        """Test getting property definitions from cache."""
        cache_dir = str(tmp_path)
        props_cache_path = os.path.join(cache_dir, "props.json")
        
        test_props = [
            {"id": "prop1", "name": "Property 1", "description": "Test", "units": {"name": "mm"}},
            {"id": "prop2", "name": "Property 2", "description": "Test 2", "units": None}
        ]
        
        with open(props_cache_path, 'w') as f:
            json.dump(test_props, f)
        
        result = await manager.get_property_definitions(
            "element_group_1", "token", cache_dir
        )
        
        assert result == test_props
    
    @pytest.mark.asyncio
    async def test_get_property_definitions_from_api(self, manager, tmp_path):
        """Test getting property definitions from API."""
        cache_dir = str(tmp_path)
        
        # Mock API response
        mock_response = {
            "elementGroupAtTip": {
                "propertyDefinitions": {
                    "pagination": {"cursor": None},
                    "results": [
                        {"id": "prop1", "name": "Property 1", "description": "Test", "units": {"name": "mm"}}
                    ]
                }
            }
        }
        
        mock_client = Mock()
        mock_client.execute_async = AsyncMock(return_value=mock_response)
        
        with patch('agent_core.tools.aec_data_model.Client', return_value=mock_client), \
             patch('agent_core.tools.aec_data_model.AIOHTTPTransport'), \
             patch('agent_core.tools.aec_data_model.gql'):
            
            result = await manager.get_property_definitions(
                "element_group_1", "token", cache_dir
            )
            
            assert len(result) == 1
            assert result[0]["id"] == "prop1"
            
            # Check cache file was created
            cache_file = os.path.join(cache_dir, "props.json")
            assert os.path.exists(cache_file)
    
    @pytest.mark.asyncio
    async def test_populate_vector_store(self, manager, mock_vector_store, tmp_path):
        """Test populating vector store with property definitions."""
        cache_dir = str(tmp_path)
        
        # Create cached property definitions
        test_props = [
            {"id": "prop1", "name": "Property 1", "description": "Test", "units": {"name": "mm"}},
            {"id": "prop2", "name": "Property 2", "description": "Test 2", "units": None}
        ]
        
        props_cache_path = os.path.join(cache_dir, "props.json")
        with open(props_cache_path, 'w') as f:
            json.dump(test_props, f)
        
        await manager.populate_vector_store("element_group_1", "token", cache_dir)
        
        # Verify documents were added to vector store
        mock_vector_store.add_documents.assert_called_once()
        documents = mock_vector_store.add_documents.call_args[0][0]
        
        assert len(documents) == 2
        assert "Property Name: Property 1" in documents[0].page_content
        assert documents[0].metadata["property_id"] == "prop1"
    
    @pytest.mark.asyncio
    async def test_ensure_vector_store_populated_with_data(self, manager, mock_vector_store, tmp_path):
        """Test ensuring vector store is populated when data exists."""
        # Mock vector store to return existing data
        mock_vector_store.similarity_search.return_value = [Mock()]
        
        await manager.ensure_vector_store_populated("element_group_1", "token", str(tmp_path))
        
        # Should not populate since data exists
        mock_vector_store.add_documents.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_ensure_vector_store_populated_without_data(self, manager, mock_vector_store, tmp_path):
        """Test ensuring vector store is populated when no data exists."""
        cache_dir = str(tmp_path)
        
        # Mock vector store to return no data
        mock_vector_store.similarity_search.return_value = []
        
        # Create cached property definitions
        test_props = [{"id": "prop1", "name": "Property 1", "description": "Test", "units": {"name": "mm"}}]
        props_cache_path = os.path.join(cache_dir, "props.json")
        with open(props_cache_path, 'w') as f:
            json.dump(test_props, f)
        
        await manager.ensure_vector_store_populated("element_group_1", "token", cache_dir)
        
        # Should populate since no data exists
        mock_vector_store.add_documents.assert_called_once()


@pytest.mark.asyncio
async def test_integration_workflow(mock_vector_store, auth_context, tmp_path):
    """Test complete workflow integration."""
    cache_dir = str(tmp_path)
    
    # Create tools
    graphql_tool = ExecuteGraphQLQueryTool()
    categories_tool = GetElementCategoriesTool()
    jq_tool = ExecuteJQQueryTool()
    search_tool = FindRelatedPropertyDefinitionsTool(mock_vector_store)
    
    # Test jq tool (no external dependencies)
    jq_result = await jq_tool.execute(
        query=".name",
        input_json='{"name": "test", "value": 42}'
    )
    assert jq_result.success is True
    assert jq_result.result == ["test"]
    
    # Test search tool
    search_result = await search_tool.execute(query="wall properties")
    assert search_result.success is True
    assert search_result.result["results_count"] == 1
    
    # Test property definitions manager
    manager = PropertyDefinitionsManager(mock_vector_store)
    
    # Create test cache data
    test_props = [{"id": "prop1", "name": "Test Property", "description": "Test", "units": {"name": "mm"}}]
    props_cache_path = os.path.join(cache_dir, "props.json")
    with open(props_cache_path, 'w') as f:
        json.dump(test_props, f)
    
    # Test getting cached properties
    props = await manager.get_property_definitions("element_group_1", "token", cache_dir)
    assert len(props) == 1
    assert props[0]["name"] == "Test Property"