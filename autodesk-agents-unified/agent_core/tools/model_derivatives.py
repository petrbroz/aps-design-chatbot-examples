"""
Model Derivatives tools for the AgentCore framework.

These tools provide functionality for working with Autodesk Platform Services
Model Derivatives, including SQLite database setup, management, and querying
for design element properties.
"""

import os
import json
import sqlite3
import asyncio
from typing import Dict, Any, List, Optional, Union
from datetime import datetime

from ..base_agent import BaseTool
from ..models import ToolResult
from ..auth import AuthContext


class ModelDerivativesClient:
    """Client for interacting with Autodesk Platform Services Model Derivatives API."""
    
    def __init__(self, access_token: str, host: str = "https://developer.api.autodesk.com"):
        """
        Initialize the Model Derivatives client.
        
        Args:
            access_token: OAuth access token for API authentication
            host: API host URL
        """
        import httpx
        self.client = httpx.AsyncClient()
        self.access_token = access_token
        self.host = host

    async def _get(self, endpoint: str) -> dict:
        """Make GET request with retry logic for 202 responses."""
        response = await self.client.get(
            f"{self.host}/{endpoint}", 
            headers={"Authorization": f"Bearer {self.access_token}"}
        )
        
        # Handle 202 (Accepted) responses with retry
        while response.status_code == 202:
            await asyncio.sleep(1)
            response = await self.client.get(
                f"{self.host}/{endpoint}", 
                headers={"Authorization": f"Bearer {self.access_token}"}
            )
        
        if response.status_code >= 400:
            raise Exception(response.text)
        
        return response.json()

    async def list_model_views(self, urn: str) -> List[dict]:
        """List available model views for a given URN."""
        json_response = await self._get(f"modelderivative/v2/designdata/{urn}/metadata")
        return json_response["data"]["metadata"]

    async def fetch_object_tree(self, urn: str, model_guid: str) -> List[dict]:
        """Fetch object tree for a specific model view."""
        json_response = await self._get(f"modelderivative/v2/designdata/{urn}/metadata/{model_guid}")
        return json_response["data"]["objects"]

    async def fetch_all_properties(self, urn: str, model_guid: str) -> List[dict]:
        """Fetch all properties for a specific model view."""
        json_response = await self._get(f"modelderivative/v2/designdata/{urn}/metadata/{model_guid}/properties")
        return json_response["data"]["collection"]

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()


class PropertyParser:
    """Utility class for parsing property values with units."""
    
    @staticmethod
    def _parse_length(value: str) -> float:
        """Parse length values with various units to meters."""
        units = {
            "m": 1,
            "cm": 0.01,
            "mm": 0.001,
            "km": 1000,
            "in": 0.0254,
            "ft": 0.3048,
            "ft-and-fractional-in": 0.3048,
            "yd": 0.9144,
            "mi": 1609.34
        }
        try:
            parts = value.split()
            if len(parts) != 2:
                return None
            number, unit = parts
            return float(number) * units.get(unit, 1)
        except (ValueError, KeyError):
            return None

    @staticmethod
    def _parse_area(value: str) -> float:
        """Parse area values with various units to square meters."""
        units = {
            "m^2": 1,
            "cm^2": 0.0001,
            "mm^2": 0.000001,
            "km^2": 1000000,
            "in^2": 0.00064516,
            "ft^2": 0.092903,
            "yd^2": 0.836127,
            "mi^2": 2589988.11
        }
        try:
            parts = value.split()
            if len(parts) != 2:
                return None
            number, unit = parts
            return float(number) * units.get(unit, 1)
        except (ValueError, KeyError):
            return None

    @staticmethod
    def _parse_volume(value: str) -> float:
        """Parse volume values with various units to cubic meters."""
        units = {
            "m^3": 1,
            "cm^3": 0.000001,
            "mm^3": 0.000000001,
            "km^3": 1000000000,
            "in^3": 0.0000163871,
            "ft^3": 0.0283168,
            "CF": 0.0283168,
            "yd^3": 0.764555
        }
        try:
            parts = value.split()
            if len(parts) != 2:
                return None
            number, unit = parts
            return float(number) * units.get(unit, 1)
        except (ValueError, KeyError):
            return None

    @staticmethod
    def _parse_angle(value: str) -> float:
        """Parse angle values with various units to degrees."""
        units = {
            "degrees": 1,
            "degree": 1,
            "deg": 1,
            "°": 1,
            "radians": 57.2958,
            "radian": 57.2958,
            "rad": 57.2958,
        }
        try:
            parts = value.split()
            if len(parts) != 2:
                return None
            number, unit = parts
            return float(number) * units.get(unit, 1)
        except (ValueError, KeyError):
            return None

    @staticmethod
    def _parse_text(value: str) -> str:
        """Parse text values (no conversion needed)."""
        return value


# Define the properties to extract from the model
# (column name, column type, category name, property name, parsing function)
PROPERTIES = [
    ("width", "REAL", "Dimensions", "Width", PropertyParser._parse_length),
    ("height", "REAL", "Dimensions", "Height", PropertyParser._parse_length),
    ("length", "REAL", "Dimensions", "Length", PropertyParser._parse_length),
    ("area", "REAL", "Dimensions", "Area", PropertyParser._parse_area),
    ("volume", "REAL", "Dimensions", "Volume", PropertyParser._parse_volume),
    ("perimeter", "REAL", "Dimensions", "Perimeter", PropertyParser._parse_length),
    ("slope", "REAL", "Dimensions", "Slope", PropertyParser._parse_angle),
    ("thickness", "REAL", "Dimensions", "Thickness", PropertyParser._parse_length),
    ("radius", "REAL", "Dimensions", "Radius", PropertyParser._parse_length),
    ("level", "TEXT", "Constraints", "Level", PropertyParser._parse_text),
    ("material", "TEXT", "Materials and Finishes", "Structural Material", PropertyParser._parse_text),
]


class SetupDatabaseTool(BaseTool):
    """Tool for setting up SQLite database with model properties."""
    
    def __init__(self, name: str = "setup_database", description: str = None):
        """Initialize the SetupDatabase tool."""
        if description is None:
            description = (
                "Sets up a SQLite database with model properties for a given URN. "
                "Downloads model metadata, properties, and creates a structured database "
                "for querying design element properties."
            )
        super().__init__(name, description)
    
    def _get_parameters_schema(self) -> Dict[str, Any]:
        """Get the parameters schema for this tool."""
        return {
            "type": "object",
            "properties": {
                "urn": {
                    "type": "string",
                    "description": "The URN of the design file to process"
                }
            },
            "required": ["urn"]
        }
    
    async def execute(self, **kwargs) -> ToolResult:
        """Execute the setup database tool."""
        try:
            urn = kwargs.get("urn")
            if not urn:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error="urn parameter is required"
                )
            
            # Get context from kwargs
            auth_context = kwargs.get("auth_context")
            cache_dir = kwargs.get("cache_dir")
            
            if not auth_context or not isinstance(auth_context, AuthContext):
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error="auth_context is required"
                )
            
            if not cache_dir:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error="cache_dir is required"
                )
            
            access_token = auth_context.access_token
            
            # Create cache directory if it doesn't exist
            os.makedirs(cache_dir, exist_ok=True)
            
            propdb_path = os.path.join(cache_dir, "props.sqlite3")
            
            # Check if database already exists
            if os.path.exists(propdb_path):
                return ToolResult(
                    tool_name=self.name,
                    success=True,
                    result=f"Database already exists at {propdb_path}",
                    metadata={"database_path": propdb_path, "cached": True}
                )
            
            client = ModelDerivativesClient(access_token)
            try:
                # Get or fetch model views
                views_path = os.path.join(cache_dir, "views.json")
                if not os.path.exists(views_path):
                    views = await client.list_model_views(urn)
                    with open(views_path, "w") as f:
                        json.dump(views, f)
                else:
                    with open(views_path, "r") as f:
                        views = json.load(f)
                
                if not views:
                    return ToolResult(
                        tool_name=self.name,
                        success=False,
                        error="No model views found for the given URN"
                    )
                
                # Use the first view
                view_guid = views[0]["guid"]
                
                # Get or fetch object tree
                tree_path = os.path.join(cache_dir, "tree.json")
                if not os.path.exists(tree_path):
                    tree = await client.fetch_object_tree(urn, view_guid)
                    with open(tree_path, "w") as f:
                        json.dump(tree, f)
                else:
                    with open(tree_path, "r") as f:
                        tree = json.load(f)
                
                # Get or fetch properties
                props_path = os.path.join(cache_dir, "props.json")
                if not os.path.exists(props_path):
                    props = await client.fetch_all_properties(urn, view_guid)
                    with open(props_path, "w") as f:
                        json.dump(props, f)
                else:
                    with open(props_path, "r") as f:
                        props = json.load(f)
                
                # Create SQLite database
                conn = sqlite3.connect(propdb_path)
                c = conn.cursor()
                
                # Create table with dynamic columns based on PROPERTIES
                columns_def = ', '.join([f'{column_name} {column_type}' for (column_name, column_type, _, _, _) in PROPERTIES])
                c.execute(f"CREATE TABLE properties (object_id INTEGER, name TEXT, external_id TEXT, {columns_def})")
                
                # Insert data
                for row in props:
                    object_id = row["objectid"]
                    name = row["name"]
                    external_id = row["externalId"]
                    object_props = row["properties"]
                    
                    insert_values = [object_id, name, external_id]
                    
                    # Process each defined property
                    for (_, _, category_name, property_name, parse_func) in PROPERTIES:
                        if (category_name in object_props and 
                            property_name in object_props[category_name]):
                            try:
                                parsed_value = parse_func(object_props[category_name][property_name])
                                insert_values.append(parsed_value)
                            except Exception:
                                insert_values.append(None)
                        else:
                            insert_values.append(None)
                    
                    # Insert row
                    placeholders = ', '.join(['?' for _ in insert_values])
                    c.execute(f"INSERT INTO properties VALUES ({placeholders})", insert_values)
                
                conn.commit()
                conn.close()
                
                return ToolResult(
                    tool_name=self.name,
                    success=True,
                    result=f"Database created successfully at {propdb_path}",
                    metadata={
                        "database_path": propdb_path,
                        "view_guid": view_guid,
                        "properties_count": len(props),
                        "cached": False
                    }
                )
            
            finally:
                await client.close()
                
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=str(e)
            )


class SQLQueryTool(BaseTool):
    """Tool for executing SQL queries on the SQLite database."""
    
    def __init__(self, name: str = "sql_query", description: str = None):
        """Initialize the SQLQuery tool."""
        if description is None:
            description = (
                "Executes a SQL query on the SQLite database containing model properties. "
                "Returns the query results as a list of dictionaries."
            )
        super().__init__(name, description)
    
    def _get_parameters_schema(self) -> Dict[str, Any]:
        """Get the parameters schema for this tool."""
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The SQL query to execute"
                }
            },
            "required": ["query"]
        }
    
    async def execute(self, **kwargs) -> ToolResult:
        """Execute the SQL query tool."""
        try:
            query = kwargs.get("query")
            if not query:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error="query parameter is required"
                )
            
            # Get context from kwargs
            cache_dir = kwargs.get("cache_dir")
            
            if not cache_dir:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error="cache_dir is required"
                )
            
            propdb_path = os.path.join(cache_dir, "props.sqlite3")
            
            if not os.path.exists(propdb_path):
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error="Database not found. Please run setup_database first."
                )
            
            # Execute query
            conn = sqlite3.connect(propdb_path)
            conn.row_factory = sqlite3.Row  # Enable column access by name
            c = conn.cursor()
            
            try:
                c.execute(query)
                
                # Handle different query types
                if query.strip().upper().startswith(('SELECT', 'WITH')):
                    # For SELECT queries, fetch results
                    rows = c.fetchall()
                    results = [dict(row) for row in rows]
                    
                    return ToolResult(
                        tool_name=self.name,
                        success=True,
                        result=results,
                        metadata={
                            "query": query,
                            "rows_returned": len(results)
                        }
                    )
                else:
                    # For other queries (INSERT, UPDATE, DELETE), return affected rows
                    affected_rows = c.rowcount
                    conn.commit()
                    
                    return ToolResult(
                        tool_name=self.name,
                        success=True,
                        result=f"Query executed successfully. {affected_rows} rows affected.",
                        metadata={
                            "query": query,
                            "rows_affected": affected_rows
                        }
                    )
            
            finally:
                conn.close()
                
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=str(e)
            )


class GetTableInfoTool(BaseTool):
    """Tool for getting information about database tables and schema."""
    
    def __init__(self, name: str = "get_table_info", description: str = None):
        """Initialize the GetTableInfo tool."""
        if description is None:
            description = (
                "Gets information about the database schema, including table names, "
                "column names, and data types. Useful for understanding the database structure."
            )
        super().__init__(name, description)
    
    def _get_parameters_schema(self) -> Dict[str, Any]:
        """Get the parameters schema for this tool."""
        return {
            "type": "object",
            "properties": {
                "table_name": {
                    "type": "string",
                    "description": "Optional table name to get specific table info. If not provided, returns info for all tables."
                }
            },
            "required": []
        }
    
    async def execute(self, **kwargs) -> ToolResult:
        """Execute the get table info tool."""
        try:
            table_name = kwargs.get("table_name")
            
            # Get context from kwargs
            cache_dir = kwargs.get("cache_dir")
            
            if not cache_dir:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error="cache_dir is required"
                )
            
            propdb_path = os.path.join(cache_dir, "props.sqlite3")
            
            if not os.path.exists(propdb_path):
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error="Database not found. Please run setup_database first."
                )
            
            # Get table information
            conn = sqlite3.connect(propdb_path)
            c = conn.cursor()
            
            try:
                if table_name:
                    # Get info for specific table
                    c.execute(f"PRAGMA table_info({table_name})")
                    columns = c.fetchall()
                    
                    if not columns:
                        return ToolResult(
                            tool_name=self.name,
                            success=False,
                            error=f"Table '{table_name}' not found"
                        )
                    
                    table_info = {
                        "table_name": table_name,
                        "columns": [
                            {
                                "name": col[1],
                                "type": col[2],
                                "not_null": bool(col[3]),
                                "default_value": col[4],
                                "primary_key": bool(col[5])
                            }
                            for col in columns
                        ]
                    }
                    
                    return ToolResult(
                        tool_name=self.name,
                        success=True,
                        result=table_info,
                        metadata={"columns_count": len(columns)}
                    )
                else:
                    # Get info for all tables
                    c.execute("SELECT name FROM sqlite_master WHERE type='table'")
                    tables = c.fetchall()
                    
                    all_tables_info = []
                    for table in tables:
                        table_name = table[0]
                        c.execute(f"PRAGMA table_info({table_name})")
                        columns = c.fetchall()
                        
                        table_info = {
                            "table_name": table_name,
                            "columns": [
                                {
                                    "name": col[1],
                                    "type": col[2],
                                    "not_null": bool(col[3]),
                                    "default_value": col[4],
                                    "primary_key": bool(col[5])
                                }
                                for col in columns
                            ]
                        }
                        all_tables_info.append(table_info)
                    
                    return ToolResult(
                        tool_name=self.name,
                        success=True,
                        result=all_tables_info,
                        metadata={"tables_count": len(all_tables_info)}
                    )
            
            finally:
                conn.close()
                
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=str(e)
            )


class GetSampleDataTool(BaseTool):
    """Tool for getting sample data from database tables."""
    
    def __init__(self, name: str = "get_sample_data", description: str = None):
        """Initialize the GetSampleData tool."""
        if description is None:
            description = (
                "Gets sample data from a database table to help understand the data structure "
                "and content. Returns a limited number of rows from the specified table."
            )
        super().__init__(name, description)
    
    def _get_parameters_schema(self) -> Dict[str, Any]:
        """Get the parameters schema for this tool."""
        return {
            "type": "object",
            "properties": {
                "table_name": {
                    "type": "string",
                    "description": "The name of the table to get sample data from"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of rows to return (default: 5)",
                    "default": 5
                }
            },
            "required": ["table_name"]
        }
    
    async def execute(self, **kwargs) -> ToolResult:
        """Execute the get sample data tool."""
        try:
            table_name = kwargs.get("table_name")
            limit = kwargs.get("limit", 5)
            
            if not table_name:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error="table_name parameter is required"
                )
            
            # Get context from kwargs
            cache_dir = kwargs.get("cache_dir")
            
            if not cache_dir:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error="cache_dir is required"
                )
            
            propdb_path = os.path.join(cache_dir, "props.sqlite3")
            
            if not os.path.exists(propdb_path):
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error="Database not found. Please run setup_database first."
                )
            
            # Get sample data
            conn = sqlite3.connect(propdb_path)
            conn.row_factory = sqlite3.Row  # Enable column access by name
            c = conn.cursor()
            
            try:
                c.execute(f"SELECT * FROM {table_name} LIMIT ?", (limit,))
                rows = c.fetchall()
                
                if not rows:
                    return ToolResult(
                        tool_name=self.name,
                        success=True,
                        result=[],
                        metadata={
                            "table_name": table_name,
                            "rows_returned": 0,
                            "message": "Table is empty"
                        }
                    )
                
                results = [dict(row) for row in rows]
                
                return ToolResult(
                    tool_name=self.name,
                    success=True,
                    result=results,
                    metadata={
                        "table_name": table_name,
                        "rows_returned": len(results),
                        "limit": limit
                    }
                )
            
            finally:
                conn.close()
                
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=str(e)
            )