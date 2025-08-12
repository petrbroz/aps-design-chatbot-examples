"""
Unit tests for Model Properties tools.
"""

import pytest
import json
import os
import tempfile
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from datetime import datetime

from agent_core.tools.model_properties import (
    CreateIndexTool,
    ListIndexPropertiesTool,
    QueryIndexTool,
    ExecuteJQQueryTool,
    ModelPropertiesClient
)
from agent_core.auth import AuthContext
from agent_core.models import ToolResult


class TestModelPropertiesClient:
    """Test cases for ModelPropertiesClient."""
    
    @pytest.fixture
    def client(self):
        """Create a test client."""
        return ModelPropertiesClient("test_token")
    
    def test_build_url(self, client):
        """Test URL building."""
        # Test with b. prefix
        url = client._build_url("b.project123", "/test")
        assert url == "https://developer.api.autodesk.com/construction/index/v2/projects/project123/indexes/test"
        
        # Test without b. prefix
        url = client._build_url("project123", "/test")
        assert url == "https://developer.api.autodesk.com/construction/index/v2/projects/project123/indexes/test"
    
    @pytest.mark.asyncio
    async def test_get_json_success(self, client):
        """Test successful JSON GET request."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"test": "data"}
        
        with patch.object(client.client, 'get', return_value=mock_response):
            result = await client._get_json("http://test.com")
            assert result == {"test": "data"}
    
    @pytest.mark.asyncio
    async def test_get_json_error(self, client):
        """Test JSON GET request with error."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"error": "Bad request"}
        
        with patch.object(client.client, 'get', return_value=mock_response):
            with pytest.raises(Exception):
                await client._get_json("http://test.com")
    
    @pytest.mark.asyncio
    async def test_get_ldjson(self, client):
        """Test line-delimited JSON GET request."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"line1": "data1"}\n{"line2": "data2"}'
        
        with patch.object(client.client, 'get', return_value=mock_response):
            result = await client._get_ldjson("http://test.com")
            assert result == [{"line1": "data1"}, {"line2": "data2"}]


class TestCreateIndexTool:
    """Test cases for CreateIndexTool."""
    
    @pytest.fixture
    def tool(self):
        """Create a test tool."""
        return CreateIndexTool()
    
    @pytest.fixture
    def auth_context(self):
        """Create test auth context."""
        return AuthContext(
            access_token="test_token",
            project_id="b.project123"
        )
    
    def test_init(self, tool):
        """Test tool initialization."""
        assert tool.name == "create_index"
        assert "Model Properties index" in tool.description
    
    def test_parameters_schema(self, tool):
        """Test parameters schema."""
        schema = tool._get_parameters_schema()
        assert schema["type"] == "object"
        assert "design_id" in schema["properties"]
        assert "design_id" in schema["required"]
    
    @pytest.mark.asyncio
    async def test_execute_missing_design_id(self, tool):
        """Test execution with missing design_id."""
        result = await tool.execute()
        assert not result.success
        assert "design_id parameter is required" in result.error
    
    @pytest.mark.asyncio
    async def test_execute_missing_auth_context(self, tool):
        """Test execution with missing auth context."""
        result = await tool.execute(design_id="test_design")
        assert not result.success
        assert "auth_context is required" in result.error
    
    @pytest.mark.asyncio
    async def test_execute_missing_cache_dir(self, tool, auth_context):
        """Test execution with missing cache directory."""
        result = await tool.execute(
            design_id="test_design",
            auth_context=auth_context
        )
        assert not result.success
        assert "cache_dir is required" in result.error
    
    @pytest.mark.asyncio
    async def test_execute_success_cached(self, tool, auth_context):
        """Test successful execution with cached index."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create cached index file
            index_data = {"indexId": "test_index_123", "state": "FINISHED"}
            index_path = os.path.join(temp_dir, "index.json")
            with open(index_path, "w") as f:
                json.dump(index_data, f)
            
            result = await tool.execute(
                design_id="test_design",
                auth_context=auth_context,
                cache_dir=temp_dir
            )
            
            assert result.success
            assert result.result == "test_index_123"
            assert result.metadata["index_state"] == "FINISHED"
    
    @pytest.mark.asyncio
    async def test_execute_success_new_index(self, tool, auth_context):
        """Test successful execution creating new index."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Mock the client
            mock_client = AsyncMock()
            mock_client.create_indexes.return_value = {
                "indexes": [{"indexId": "new_index_123", "state": "PROCESSING"}]
            }
            mock_client.get_index.return_value = {"indexId": "new_index_123", "state": "FINISHED"}
            
            with patch('agent_core.tools.model_properties.ModelPropertiesClient', return_value=mock_client):
                result = await tool.execute(
                    design_id="test_design",
                    auth_context=auth_context,
                    cache_dir=temp_dir
                )
            
            assert result.success
            assert result.result == "new_index_123"
            
            # Verify index was cached
            index_path = os.path.join(temp_dir, "index.json")
            assert os.path.exists(index_path)
    
    @pytest.mark.asyncio
    async def test_execute_index_with_errors(self, tool, auth_context):
        """Test execution with index creation errors."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create cached index file with errors
            index_data = {"indexId": "test_index_123", "errors": ["Some error"]}
            index_path = os.path.join(temp_dir, "index.json")
            with open(index_path, "w") as f:
                json.dump(index_data, f)
            
            result = await tool.execute(
                design_id="test_design",
                auth_context=auth_context,
                cache_dir=temp_dir
            )
            
            assert not result.success
            assert "Index creation failed with errors" in result.error


class TestListIndexPropertiesTool:
    """Test cases for ListIndexPropertiesTool."""
    
    @pytest.fixture
    def tool(self):
        """Create a test tool."""
        return ListIndexPropertiesTool()
    
    @pytest.fixture
    def auth_context(self):
        """Create test auth context."""
        return AuthContext(
            access_token="test_token",
            project_id="b.project123"
        )
    
    def test_init(self, tool):
        """Test tool initialization."""
        assert tool.name == "list_index_properties"
        assert "Lists available properties" in tool.description
    
    def test_parameters_schema(self, tool):
        """Test parameters schema."""
        schema = tool._get_parameters_schema()
        assert schema["type"] == "object"
        assert "index_id" in schema["properties"]
        assert "index_id" in schema["required"]
    
    @pytest.mark.asyncio
    async def test_execute_success_cached(self, tool, auth_context):
        """Test successful execution with cached fields."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create cached fields file
            fields_data = {
                "Dimensions": {"Width": "width_key", "Height": "height_key"},
                "Materials and Finishes": {"Material": "material_key"}
            }
            fields_path = os.path.join(temp_dir, "fields.json")
            with open(fields_path, "w") as f:
                json.dump(fields_data, f)
            
            result = await tool.execute(
                index_id="test_index",
                auth_context=auth_context,
                cache_dir=temp_dir
            )
            
            assert result.success
            assert result.result == fields_data
            assert result.metadata["categories_count"] == 2
    
    @pytest.mark.asyncio
    async def test_execute_success_new_fields(self, tool, auth_context):
        """Test successful execution fetching new fields."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Mock the client
            mock_client = AsyncMock()
            mock_fields = [
                {"category": "Dimensions", "name": "Width", "key": "width_key"},
                {"category": "Dimensions", "name": "Height", "key": "height_key"},
                {"category": "Other", "name": "Other Prop", "key": "other_key"},  # Should be filtered
                {"category": "Materials and Finishes", "name": "Material", "key": "material_key"}
            ]
            mock_client.get_index_fields.return_value = mock_fields
            
            with patch('agent_core.tools.model_properties.ModelPropertiesClient', return_value=mock_client):
                result = await tool.execute(
                    index_id="test_index",
                    auth_context=auth_context,
                    cache_dir=temp_dir
                )
            
            assert result.success
            expected_result = {
                "Dimensions": {"Width": "width_key", "Height": "height_key"},
                "Materials and Finishes": {"Material": "material_key"}
            }
            assert result.result == expected_result
            
            # Verify fields were cached
            fields_path = os.path.join(temp_dir, "fields.json")
            assert os.path.exists(fields_path)


class TestQueryIndexTool:
    """Test cases for QueryIndexTool."""
    
    @pytest.fixture
    def tool(self):
        """Create a test tool."""
        return QueryIndexTool()
    
    @pytest.fixture
    def auth_context(self):
        """Create test auth context."""
        return AuthContext(
            access_token="test_token",
            project_id="b.project123"
        )
    
    def test_init(self, tool):
        """Test tool initialization."""
        assert tool.name == "query_index"
        assert "Queries a Model Properties index" in tool.description
    
    def test_parameters_schema(self, tool):
        """Test parameters schema."""
        schema = tool._get_parameters_schema()
        assert schema["type"] == "object"
        assert "index_id" in schema["properties"]
        assert "query_str" in schema["properties"]
        assert set(schema["required"]) == {"index_id", "query_str"}
    
    @pytest.mark.asyncio
    async def test_execute_missing_parameters(self, tool, auth_context):
        """Test execution with missing parameters."""
        # Missing index_id
        result = await tool.execute(query_str='{"test": "query"}', auth_context=auth_context)
        assert not result.success
        assert "index_id parameter is required" in result.error
        
        # Missing query_str
        result = await tool.execute(index_id="test_index", auth_context=auth_context)
        assert not result.success
        assert "query_str parameter is required" in result.error
    
    @pytest.mark.asyncio
    async def test_execute_invalid_json(self, tool, auth_context):
        """Test execution with invalid JSON query."""
        result = await tool.execute(
            index_id="test_index",
            query_str="invalid json",
            auth_context=auth_context
        )
        
        assert not result.success
        assert "Invalid JSON in query_str" in result.error
    
    @pytest.mark.asyncio
    async def test_execute_success(self, tool, auth_context):
        """Test successful query execution."""
        # Mock the client
        mock_client = AsyncMock()
        mock_client.create_query.return_value = {"queryId": "query_123", "state": "PROCESSING"}
        mock_client.get_query.return_value = {"queryId": "query_123", "state": "FINISHED"}
        mock_client.get_query_results.return_value = [
            {"element_id": "1", "width": 100},
            {"element_id": "2", "width": 200}
        ]
        
        with patch('agent_core.tools.model_properties.ModelPropertiesClient', return_value=mock_client):
            result = await tool.execute(
                index_id="test_index",
                query_str='{"filter": {"width": {"$gt": 50}}}',
                auth_context=auth_context
            )
        
        assert result.success
        assert len(result.result) == 2
        assert result.metadata["results_count"] == 2
        assert result.metadata["query_id"] == "query_123"
    
    @pytest.mark.asyncio
    async def test_execute_too_many_results(self, tool, auth_context):
        """Test execution with too many results."""
        # Mock the client
        mock_client = AsyncMock()
        mock_client.create_query.return_value = {"queryId": "query_123", "state": "PROCESSING"}
        mock_client.get_query.return_value = {"queryId": "query_123", "state": "FINISHED"}
        # Create more results than MAX_RESULTS
        mock_results = [{"element_id": str(i)} for i in range(300)]
        mock_client.get_query_results.return_value = mock_results
        
        with patch('agent_core.tools.model_properties.ModelPropertiesClient', return_value=mock_client):
            result = await tool.execute(
                index_id="test_index",
                query_str='{"filter": {}}',
                auth_context=auth_context
            )
        
        assert not result.success
        assert "too many results" in result.error
    
    @pytest.mark.asyncio
    async def test_execute_query_failed(self, tool, auth_context):
        """Test execution with failed query."""
        # Mock the client
        mock_client = AsyncMock()
        mock_client.create_query.return_value = {"queryId": "query_123", "state": "PROCESSING"}
        mock_client.get_query.return_value = {
            "queryId": "query_123", 
            "state": "FAILED", 
            "errors": ["Query syntax error"]
        }
        
        with patch('agent_core.tools.model_properties.ModelPropertiesClient', return_value=mock_client):
            result = await tool.execute(
                index_id="test_index",
                query_str='{"invalid": "query"}',
                auth_context=auth_context
            )
        
        assert not result.success
        assert "Query failed with errors" in result.error


class TestExecuteJQQueryTool:
    """Test cases for ExecuteJQQueryTool."""
    
    @pytest.fixture
    def tool(self):
        """Create a test tool."""
        return ExecuteJQQueryTool()
    
    def test_init(self, tool):
        """Test tool initialization."""
        assert tool.name == "execute_jq_query"
        assert "jq query" in tool.description
    
    def test_parameters_schema(self, tool):
        """Test parameters schema."""
        schema = tool._get_parameters_schema()
        assert schema["type"] == "object"
        assert "jq_query" in schema["properties"]
        assert "input_json" in schema["properties"]
        assert set(schema["required"]) == {"jq_query", "input_json"}
    
    @pytest.mark.asyncio
    async def test_execute_missing_parameters(self, tool):
        """Test execution with missing parameters."""
        # Missing jq_query
        result = await tool.execute(input_json='{"test": "data"}')
        assert not result.success
        assert "jq_query parameter is required" in result.error
        
        # Missing input_json
        result = await tool.execute(jq_query=".test")
        assert not result.success
        assert "input_json parameter is required" in result.error
    
    @pytest.mark.asyncio
    async def test_execute_success(self, tool):
        """Test successful jq query execution."""
        input_json = '{"items": [{"name": "item1", "value": 10}, {"name": "item2", "value": 20}]}'
        jq_query = ".items[] | .value"
        
        result = await tool.execute(
            jq_query=jq_query,
            input_json=input_json
        )
        
        assert result.success
        assert result.result == [10, 20]
        assert result.metadata["query"] == jq_query
    
    @pytest.mark.asyncio
    async def test_execute_invalid_jq_query(self, tool):
        """Test execution with invalid jq query."""
        input_json = '{"test": "data"}'
        jq_query = ".invalid[syntax"
        
        result = await tool.execute(
            jq_query=jq_query,
            input_json=input_json
        )
        
        assert not result.success
        assert "jq query execution failed" in result.error
    
    @pytest.mark.asyncio
    async def test_execute_invalid_json_input(self, tool):
        """Test execution with invalid JSON input."""
        input_json = "invalid json"
        jq_query = ".test"
        
        result = await tool.execute(
            jq_query=jq_query,
            input_json=input_json
        )
        
        assert not result.success
        assert "jq query execution failed" in result.error


if __name__ == "__main__":
    pytest.main([__file__])