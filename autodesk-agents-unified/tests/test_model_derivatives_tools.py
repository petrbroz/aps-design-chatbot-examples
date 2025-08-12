"""
Unit tests for Model Derivatives tools.
"""

import os
import json
import sqlite3
import tempfile
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from agent_core.tools.model_derivatives import (
    SetupDatabaseTool,
    SQLQueryTool,
    GetTableInfoTool,
    GetSampleDataTool,
    ModelDerivativesClient,
    PropertyParser,
    PROPERTIES
)
from agent_core.models import ToolResult
from agent_core.auth import AuthContext


class TestPropertyParser:
    """Test the PropertyParser utility class."""
    
    def test_parse_length(self):
        """Test length parsing with various units."""
        assert PropertyParser._parse_length("10 m") == 10.0
        assert PropertyParser._parse_length("100 cm") == 1.0
        assert PropertyParser._parse_length("1000 mm") == 1.0
        assert PropertyParser._parse_length("1 ft") == 0.3048
        assert PropertyParser._parse_length("12 in") == pytest.approx(0.3048, rel=1e-6)
        assert PropertyParser._parse_length("invalid") is None
        assert PropertyParser._parse_length("10") is None
    
    def test_parse_area(self):
        """Test area parsing with various units."""
        assert PropertyParser._parse_area("1 m^2") == 1.0
        assert PropertyParser._parse_area("10000 cm^2") == 1.0
        assert PropertyParser._parse_area("1 ft^2") == 0.092903
        assert PropertyParser._parse_area("invalid") is None
    
    def test_parse_volume(self):
        """Test volume parsing with various units."""
        assert PropertyParser._parse_volume("1 m^3") == 1.0
        assert PropertyParser._parse_volume("1000000 cm^3") == 1.0
        assert PropertyParser._parse_volume("1 ft^3") == 0.0283168
        assert PropertyParser._parse_volume("1 CF") == 0.0283168
        assert PropertyParser._parse_volume("invalid") is None
    
    def test_parse_angle(self):
        """Test angle parsing with various units."""
        assert PropertyParser._parse_angle("90 degrees") == 90.0
        assert PropertyParser._parse_angle("90 deg") == 90.0
        assert PropertyParser._parse_angle("90 °") == 90.0
        assert PropertyParser._parse_angle("1.5708 radians") == pytest.approx(90.0, rel=1e-3)
        assert PropertyParser._parse_angle("invalid") is None
    
    def test_parse_text(self):
        """Test text parsing (no conversion)."""
        assert PropertyParser._parse_text("test") == "test"
        assert PropertyParser._parse_text("Level 1") == "Level 1"


class TestModelDerivativesClient:
    """Test the ModelDerivativesClient."""
    
    @pytest.fixture
    def client(self):
        """Create a test client."""
        return ModelDerivativesClient("test_token")
    
    @pytest.mark.asyncio
    async def test_list_model_views(self, client):
        """Test listing model views."""
        mock_response = {
            "data": {
                "metadata": [
                    {"guid": "test-guid-1", "name": "3D View"},
                    {"guid": "test-guid-2", "name": "Floor Plan"}
                ]
            }
        }
        
        with patch.object(client, '_get', return_value=mock_response) as mock_get:
            views = await client.list_model_views("test-urn")
            
            mock_get.assert_called_once_with("modelderivative/v2/designdata/test-urn/metadata")
            assert len(views) == 2
            assert views[0]["guid"] == "test-guid-1"
    
    @pytest.mark.asyncio
    async def test_fetch_object_tree(self, client):
        """Test fetching object tree."""
        mock_response = {
            "data": {
                "objects": [
                    {"objectid": 1, "name": "Wall"},
                    {"objectid": 2, "name": "Door"}
                ]
            }
        }
        
        with patch.object(client, '_get', return_value=mock_response) as mock_get:
            tree = await client.fetch_object_tree("test-urn", "test-guid")
            
            mock_get.assert_called_once_with("modelderivative/v2/designdata/test-urn/metadata/test-guid")
            assert len(tree) == 2
            assert tree[0]["objectid"] == 1
    
    @pytest.mark.asyncio
    async def test_fetch_all_properties(self, client):
        """Test fetching all properties."""
        mock_response = {
            "data": {
                "collection": [
                    {
                        "objectid": 1,
                        "name": "Wall-001",
                        "externalId": "wall-ext-1",
                        "properties": {
                            "Dimensions": {
                                "Width": "200 mm",
                                "Height": "3000 mm"
                            }
                        }
                    }
                ]
            }
        }
        
        with patch.object(client, '_get', return_value=mock_response) as mock_get:
            props = await client.fetch_all_properties("test-urn", "test-guid")
            
            mock_get.assert_called_once_with("modelderivative/v2/designdata/test-urn/metadata/test-guid/properties")
            assert len(props) == 1
            assert props[0]["objectid"] == 1


class TestSetupDatabaseTool:
    """Test the SetupDatabaseTool."""
    
    @pytest.fixture
    def tool(self):
        """Create a test tool."""
        return SetupDatabaseTool()
    
    @pytest.fixture
    def auth_context(self):
        """Create a test auth context."""
        return AuthContext(access_token="test_token")
    
    @pytest.fixture
    def temp_cache_dir(self):
        """Create a temporary cache directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir
    
    @pytest.mark.asyncio
    async def test_missing_urn(self, tool):
        """Test error when URN is missing."""
        result = await tool.execute()
        
        assert not result.success
        assert "urn parameter is required" in result.error
    
    @pytest.mark.asyncio
    async def test_missing_auth_context(self, tool):
        """Test error when auth context is missing."""
        result = await tool.execute(urn="test-urn")
        
        assert not result.success
        assert "auth_context is required" in result.error
    
    @pytest.mark.asyncio
    async def test_missing_cache_dir(self, tool, auth_context):
        """Test error when cache dir is missing."""
        result = await tool.execute(urn="test-urn", auth_context=auth_context)
        
        assert not result.success
        assert "cache_dir is required" in result.error
    
    @pytest.mark.asyncio
    async def test_database_already_exists(self, tool, auth_context, temp_cache_dir):
        """Test when database already exists."""
        # Create existing database
        db_path = os.path.join(temp_cache_dir, "props.sqlite3")
        conn = sqlite3.connect(db_path)
        conn.close()
        
        result = await tool.execute(
            urn="test-urn",
            auth_context=auth_context,
            cache_dir=temp_cache_dir
        )
        
        assert result.success
        assert "already exists" in result.result
        assert result.metadata["cached"] is True
    
    @pytest.mark.asyncio
    async def test_successful_database_creation(self, tool, auth_context, temp_cache_dir):
        """Test successful database creation."""
        # Mock data
        mock_views = [{"guid": "test-guid"}]
        mock_tree = [{"objectid": 1, "name": "Wall"}]
        mock_props = [
            {
                "objectid": 1,
                "name": "Wall-001",
                "externalId": "wall-ext-1",
                "properties": {
                    "Dimensions": {
                        "Width": "200 mm",
                        "Height": "3000 mm"
                    },
                    "Materials and Finishes": {
                        "Structural Material": "Concrete"
                    }
                }
            }
        ]
        
        with patch('agent_core.tools.model_derivatives.ModelDerivativesClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.list_model_views.return_value = mock_views
            mock_client.fetch_object_tree.return_value = mock_tree
            mock_client.fetch_all_properties.return_value = mock_props
            
            result = await tool.execute(
                urn="test-urn",
                auth_context=auth_context,
                cache_dir=temp_cache_dir
            )
            
            assert result.success
            assert "created successfully" in result.result
            assert result.metadata["cached"] is False
            assert result.metadata["properties_count"] == 1
            
            # Verify database was created
            db_path = os.path.join(temp_cache_dir, "props.sqlite3")
            assert os.path.exists(db_path)
            
            # Verify database content
            conn = sqlite3.connect(db_path)
            c = conn.cursor()
            c.execute("SELECT * FROM properties")
            rows = c.fetchall()
            conn.close()
            
            assert len(rows) == 1
            assert rows[0][0] == 1  # object_id
            assert rows[0][1] == "Wall-001"  # name


class TestSQLQueryTool:
    """Test the SQLQueryTool."""
    
    @pytest.fixture
    def tool(self):
        """Create a test tool."""
        return SQLQueryTool()
    
    @pytest.fixture
    def temp_cache_dir_with_db(self):
        """Create a temporary cache directory with test database."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test database
            db_path = os.path.join(temp_dir, "props.sqlite3")
            conn = sqlite3.connect(db_path)
            c = conn.cursor()
            
            # Create test table
            c.execute("""
                CREATE TABLE properties (
                    object_id INTEGER,
                    name TEXT,
                    external_id TEXT,
                    width REAL,
                    height REAL
                )
            """)
            
            # Insert test data
            c.execute("""
                INSERT INTO properties VALUES (1, 'Wall-001', 'wall-1', 0.2, 3.0)
            """)
            c.execute("""
                INSERT INTO properties VALUES (2, 'Door-001', 'door-1', 0.8, 2.1)
            """)
            
            conn.commit()
            conn.close()
            
            yield temp_dir
    
    @pytest.mark.asyncio
    async def test_missing_query(self, tool):
        """Test error when query is missing."""
        result = await tool.execute()
        
        assert not result.success
        assert "query parameter is required" in result.error
    
    @pytest.mark.asyncio
    async def test_missing_cache_dir(self, tool):
        """Test error when cache dir is missing."""
        result = await tool.execute(query="SELECT * FROM properties")
        
        assert not result.success
        assert "cache_dir is required" in result.error
    
    @pytest.mark.asyncio
    async def test_database_not_found(self, tool):
        """Test error when database doesn't exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            result = await tool.execute(
                query="SELECT * FROM properties",
                cache_dir=temp_dir
            )
            
            assert not result.success
            assert "Database not found" in result.error
    
    @pytest.mark.asyncio
    async def test_select_query(self, tool, temp_cache_dir_with_db):
        """Test SELECT query execution."""
        result = await tool.execute(
            query="SELECT * FROM properties WHERE object_id = 1",
            cache_dir=temp_cache_dir_with_db
        )
        
        assert result.success
        assert len(result.result) == 1
        assert result.result[0]["name"] == "Wall-001"
        assert result.metadata["rows_returned"] == 1
    
    @pytest.mark.asyncio
    async def test_update_query(self, tool, temp_cache_dir_with_db):
        """Test UPDATE query execution."""
        result = await tool.execute(
            query="UPDATE properties SET name = 'Updated Wall' WHERE object_id = 1",
            cache_dir=temp_cache_dir_with_db
        )
        
        assert result.success
        assert "rows affected" in result.result
        assert result.metadata["rows_affected"] == 1
    
    @pytest.mark.asyncio
    async def test_invalid_query(self, tool, temp_cache_dir_with_db):
        """Test invalid SQL query."""
        result = await tool.execute(
            query="INVALID SQL QUERY",
            cache_dir=temp_cache_dir_with_db
        )
        
        assert not result.success
        assert "syntax error" in result.error.lower()


class TestGetTableInfoTool:
    """Test the GetTableInfoTool."""
    
    @pytest.fixture
    def tool(self):
        """Create a test tool."""
        return GetTableInfoTool()
    
    @pytest.fixture
    def temp_cache_dir_with_db(self):
        """Create a temporary cache directory with test database."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test database
            db_path = os.path.join(temp_dir, "props.sqlite3")
            conn = sqlite3.connect(db_path)
            c = conn.cursor()
            
            # Create test table
            c.execute("""
                CREATE TABLE properties (
                    object_id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    external_id TEXT,
                    width REAL,
                    height REAL
                )
            """)
            
            conn.commit()
            conn.close()
            
            yield temp_dir
    
    @pytest.mark.asyncio
    async def test_missing_cache_dir(self, tool):
        """Test error when cache dir is missing."""
        result = await tool.execute()
        
        assert not result.success
        assert "cache_dir is required" in result.error
    
    @pytest.mark.asyncio
    async def test_database_not_found(self, tool):
        """Test error when database doesn't exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            result = await tool.execute(cache_dir=temp_dir)
            
            assert not result.success
            assert "Database not found" in result.error
    
    @pytest.mark.asyncio
    async def test_get_all_tables_info(self, tool, temp_cache_dir_with_db):
        """Test getting info for all tables."""
        result = await tool.execute(cache_dir=temp_cache_dir_with_db)
        
        assert result.success
        assert len(result.result) == 1
        assert result.result[0]["table_name"] == "properties"
        assert len(result.result[0]["columns"]) == 5
        assert result.metadata["tables_count"] == 1
    
    @pytest.mark.asyncio
    async def test_get_specific_table_info(self, tool, temp_cache_dir_with_db):
        """Test getting info for specific table."""
        result = await tool.execute(
            table_name="properties",
            cache_dir=temp_cache_dir_with_db
        )
        
        assert result.success
        assert result.result["table_name"] == "properties"
        assert len(result.result["columns"]) == 5
        
        # Check column details
        columns = {col["name"]: col for col in result.result["columns"]}
        assert columns["object_id"]["primary_key"] is True
        assert columns["name"]["not_null"] is True
        assert columns["external_id"]["not_null"] is False
    
    @pytest.mark.asyncio
    async def test_table_not_found(self, tool, temp_cache_dir_with_db):
        """Test error when table doesn't exist."""
        result = await tool.execute(
            table_name="nonexistent_table",
            cache_dir=temp_cache_dir_with_db
        )
        
        assert not result.success
        assert "not found" in result.error


class TestGetSampleDataTool:
    """Test the GetSampleDataTool."""
    
    @pytest.fixture
    def tool(self):
        """Create a test tool."""
        return GetSampleDataTool()
    
    @pytest.fixture
    def temp_cache_dir_with_data(self):
        """Create a temporary cache directory with test database and data."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test database
            db_path = os.path.join(temp_dir, "props.sqlite3")
            conn = sqlite3.connect(db_path)
            c = conn.cursor()
            
            # Create test table
            c.execute("""
                CREATE TABLE properties (
                    object_id INTEGER,
                    name TEXT,
                    external_id TEXT,
                    width REAL,
                    height REAL
                )
            """)
            
            # Insert test data
            for i in range(10):
                c.execute("""
                    INSERT INTO properties VALUES (?, ?, ?, ?, ?)
                """, (i + 1, f"Element-{i+1:03d}", f"ext-{i+1}", 0.2 + i * 0.1, 3.0 + i * 0.5))
            
            conn.commit()
            conn.close()
            
            yield temp_dir
    
    @pytest.mark.asyncio
    async def test_missing_table_name(self, tool):
        """Test error when table name is missing."""
        result = await tool.execute()
        
        assert not result.success
        assert "table_name parameter is required" in result.error
    
    @pytest.mark.asyncio
    async def test_missing_cache_dir(self, tool):
        """Test error when cache dir is missing."""
        result = await tool.execute(table_name="properties")
        
        assert not result.success
        assert "cache_dir is required" in result.error
    
    @pytest.mark.asyncio
    async def test_database_not_found(self, tool):
        """Test error when database doesn't exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            result = await tool.execute(
                table_name="properties",
                cache_dir=temp_dir
            )
            
            assert not result.success
            assert "Database not found" in result.error
    
    @pytest.mark.asyncio
    async def test_get_sample_data_default_limit(self, tool, temp_cache_dir_with_data):
        """Test getting sample data with default limit."""
        result = await tool.execute(
            table_name="properties",
            cache_dir=temp_cache_dir_with_data
        )
        
        assert result.success
        assert len(result.result) == 5  # Default limit
        assert result.result[0]["name"] == "Element-001"
        assert result.metadata["rows_returned"] == 5
        assert result.metadata["limit"] == 5
    
    @pytest.mark.asyncio
    async def test_get_sample_data_custom_limit(self, tool, temp_cache_dir_with_data):
        """Test getting sample data with custom limit."""
        result = await tool.execute(
            table_name="properties",
            cache_dir=temp_cache_dir_with_data,
            limit=3
        )
        
        assert result.success
        assert len(result.result) == 3
        assert result.metadata["rows_returned"] == 3
        assert result.metadata["limit"] == 3
    
    @pytest.mark.asyncio
    async def test_empty_table(self, tool):
        """Test getting sample data from empty table."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create empty database
            db_path = os.path.join(temp_dir, "props.sqlite3")
            conn = sqlite3.connect(db_path)
            c = conn.cursor()
            c.execute("CREATE TABLE empty_table (id INTEGER)")
            conn.commit()
            conn.close()
            
            result = await tool.execute(
                table_name="empty_table",
                cache_dir=temp_dir
            )
            
            assert result.success
            assert len(result.result) == 0
            assert result.metadata["rows_returned"] == 0
            assert "empty" in result.metadata["message"]