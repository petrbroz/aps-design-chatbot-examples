"""
Model Properties tools for the AgentCore framework.

These tools provide functionality for working with Autodesk Construction Cloud
Model Properties, including index creation, property listing, querying, and
JSON processing with jq.
"""

import os
import asyncio
import json
import jq
from typing import Dict, Any, List, Optional
from datetime import datetime

from ..base_agent import BaseTool
from ..models import ToolResult
from ..auth import AuthContext


class ModelPropertiesClient:
    """Client for interacting with Autodesk Construction Cloud Model Properties API."""
    
    def __init__(self, access_token: str, host: str = "https://developer.api.autodesk.com"):
        """
        Initialize the Model Properties client.
        
        Args:
            access_token: OAuth access token for API authentication
            host: API host URL
        """
        import httpx
        self.client = httpx.AsyncClient()
        self.access_token = access_token
        self.host = host

    def _build_url(self, project_id: str, subpath: str) -> str:
        """Build API URL for Model Properties endpoints."""
        # Remove 'b.' prefix if present
        clean_project_id = project_id[2:] if project_id.startswith('b.') else project_id
        return f"{self.host}/construction/index/v2/projects/{clean_project_id}/indexes{subpath}"

    async def _get_json(self, url: str) -> dict:
        """Make GET request and return JSON response."""
        response = await self.client.get(url, headers={"Authorization": f"Bearer {self.access_token}"})
        if response.status_code >= 400:
            raise Exception(response.json())
        return response.json()

    async def _get_ldjson(self, url: str) -> List[dict]:
        """Make GET request and return line-delimited JSON response."""
        response = await self.client.get(url, headers={"Authorization": f"Bearer {self.access_token}"})
        if response.status_code >= 400:
            raise Exception(response.json())
        return [json.loads(line) for line in response.text.splitlines()]

    async def _post_json(self, url: str, json_data: dict) -> dict:
        """Make POST request with JSON payload."""
        response = await self.client.post(url, json=json_data, headers={"Authorization": f"Bearer {self.access_token}"})
        if response.status_code >= 400:
            raise Exception(response.json())
        return response.json()

    async def create_indexes(self, project_id: str, payload: dict) -> dict:
        """Create model properties indexes."""
        return await self._post_json(self._build_url(project_id, ":batch-status"), payload)

    async def get_index(self, project_id: str, index_id: str) -> dict:
        """Get index information."""
        return await self._get_json(self._build_url(project_id, f"/{index_id}"))

    async def get_index_fields(self, project_id: str, index_id: str) -> List[dict]:
        """Get index fields."""
        index = await self.get_index(project_id, index_id)
        return await self._get_ldjson(index["fieldsUrl"])

    async def create_query(self, project_id: str, index_id: str, payload: dict) -> dict:
        """Create a query on the index."""
        return await self._post_json(self._build_url(project_id, f"/{index_id}/queries"), payload)

    async def get_query(self, project_id: str, index_id: str, query_id: str) -> dict:
        """Get query information."""
        return await self._get_json(self._build_url(project_id, f"/{index_id}/queries/{query_id}"))

    async def get_query_results(self, project_id: str, index_id: str, query_id: str) -> List[dict]:
        """Get query results."""
        query = await self.get_query(project_id, index_id, query_id)
        return await self._get_ldjson(query["queryResultsUrl"])

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()


class CreateIndexTool(BaseTool):
    """Tool for creating Model Properties indexes."""
    
    # Filter categories to reduce noise
    FILTER_CATEGORIES = ["__name__", "__category__", "Dimensions", "Materials and Finishes"]
    
    def __init__(self, name: str = "create_index", description: str = None):
        """Initialize the CreateIndex tool."""
        if description is None:
            description = (
                "Builds a Model Properties index for a given design ID, including all available "
                "properties and property values for individual design elements. Returns the ID "
                "of the created index."
            )
        super().__init__(name, description)
        self.cache_dir: Optional[str] = None
    
    def _get_parameters_schema(self) -> Dict[str, Any]:
        """Get the parameters schema for this tool."""
        return {
            "type": "object",
            "properties": {
                "design_id": {
                    "type": "string",
                    "description": "The ID of the input design file hosted in Autodesk Construction Cloud"
                }
            },
            "required": ["design_id"]
        }
    
    async def execute(self, **kwargs) -> ToolResult:
        """Execute the create index tool."""
        try:
            design_id = kwargs.get("design_id")
            if not design_id:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error="design_id parameter is required"
                )
            
            # Get context from kwargs
            auth_context = kwargs.get("auth_context")
            cache_dir = kwargs.get("cache_dir", self.cache_dir)
            
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
            
            project_id = auth_context.project_id
            access_token = auth_context.access_token
            
            if not project_id:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error="project_id is required in auth_context"
                )
            
            # Create cache directory if it doesn't exist
            os.makedirs(cache_dir, exist_ok=True)
            
            client = ModelPropertiesClient(access_token)
            try:
                index_path = os.path.join(cache_dir, "index.json")
                
                # Check if index already exists in cache
                if not os.path.exists(index_path):
                    payload = {"versions": [{"versionUrn": design_id}]}
                    result = await client.create_indexes(project_id, payload)
                    index = result["indexes"][0]
                    index_id = index["indexId"]
                    
                    # Wait for index processing to complete
                    while index["state"] == "PROCESSING":
                        await asyncio.sleep(1)
                        index = await client.get_index(project_id, index_id)
                    
                    # Save index to cache
                    with open(index_path, "w") as f:
                        json.dump(index, f)
                
                # Load index from cache
                with open(index_path) as f:
                    index = json.load(f)
                    
                    if "errors" in index:
                        return ToolResult(
                            tool_name=self.name,
                            success=False,
                            error=f"Index creation failed with errors: {index['errors']}"
                        )
                    
                    return ToolResult(
                        tool_name=self.name,
                        success=True,
                        result=index["indexId"],
                        metadata={"index_state": index.get("state")}
                    )
            
            finally:
                await client.close()
                
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=str(e)
            )


class ListIndexPropertiesTool(BaseTool):
    """Tool for listing available properties in a Model Properties index."""
    
    # Filter categories to reduce noise
    FILTER_CATEGORIES = ["__name__", "__category__", "Dimensions", "Materials and Finishes"]
    
    def __init__(self, name: str = "list_index_properties", description: str = None):
        """Initialize the ListIndexProperties tool."""
        if description is None:
            description = (
                "Lists available properties for a Model Properties index of given ID. "
                "Returns a JSON with property categories, names, and keys."
            )
        super().__init__(name, description)
        self.cache_dir: Optional[str] = None
    
    def _get_parameters_schema(self) -> Dict[str, Any]:
        """Get the parameters schema for this tool."""
        return {
            "type": "object",
            "properties": {
                "index_id": {
                    "type": "string",
                    "description": "The ID of the Model Properties index to list the available properties for"
                }
            },
            "required": ["index_id"]
        }
    
    async def execute(self, **kwargs) -> ToolResult:
        """Execute the list index properties tool."""
        try:
            index_id = kwargs.get("index_id")
            if not index_id:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error="index_id parameter is required"
                )
            
            # Get context from kwargs
            auth_context = kwargs.get("auth_context")
            cache_dir = kwargs.get("cache_dir", self.cache_dir)
            
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
            
            project_id = auth_context.project_id
            access_token = auth_context.access_token
            
            if not project_id:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error="project_id is required in auth_context"
                )
            
            # Create cache directory if it doesn't exist
            os.makedirs(cache_dir, exist_ok=True)
            
            client = ModelPropertiesClient(access_token)
            try:
                fields_path = os.path.join(cache_dir, "fields.json")
                
                # Check if fields already exist in cache
                if not os.path.exists(fields_path):
                    fields = await client.get_index_fields(project_id, index_id)
                    categories = {}
                    
                    for field in fields:
                        category = field["category"]
                        # Filter out irrelevant categories
                        if category not in self.FILTER_CATEGORIES:
                            continue
                        
                        name = field["name"]
                        key = field["key"]
                        
                        if category not in categories:
                            categories[category] = {}
                        categories[category][name] = key
                    
                    # Save fields to cache
                    with open(fields_path, "w") as f:
                        json.dump(categories, f)
                
                # Load fields from cache
                with open(fields_path) as f:
                    categories = json.load(f)
                    
                    return ToolResult(
                        tool_name=self.name,
                        success=True,
                        result=categories,
                        metadata={"categories_count": len(categories)}
                    )
            
            finally:
                await client.close()
                
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=str(e)
            )


class QueryIndexTool(BaseTool):
    """Tool for querying a Model Properties index."""
    
    MAX_RESULTS = 256
    
    def __init__(self, name: str = "query_index", description: str = None):
        """Initialize the QueryIndex tool."""
        if description is None:
            description = (
                "Queries a Model Properties index of the given ID with a Model Property Service "
                "Query Language query. Returns a JSON list with properties of matching design elements."
            )
        super().__init__(name, description)
        self.cache_dir: Optional[str] = None
    
    def _get_parameters_schema(self) -> Dict[str, Any]:
        """Get the parameters schema for this tool."""
        return {
            "type": "object",
            "properties": {
                "index_id": {
                    "type": "string",
                    "description": "The ID of the Model Properties index to query"
                },
                "query_str": {
                    "type": "string",
                    "description": "The Model Property Service Query Language query"
                }
            },
            "required": ["index_id", "query_str"]
        }
    
    async def execute(self, **kwargs) -> ToolResult:
        """Execute the query index tool."""
        try:
            index_id = kwargs.get("index_id")
            query_str = kwargs.get("query_str")
            
            if not index_id:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error="index_id parameter is required"
                )
            
            if not query_str:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error="query_str parameter is required"
                )
            
            # Get context from kwargs
            auth_context = kwargs.get("auth_context")
            cache_dir = kwargs.get("cache_dir", self.cache_dir)
            
            if not auth_context or not isinstance(auth_context, AuthContext):
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error="auth_context is required"
                )
            
            project_id = auth_context.project_id
            access_token = auth_context.access_token
            
            if not project_id:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error="project_id is required in auth_context"
                )
            
            client = ModelPropertiesClient(access_token)
            try:
                # Parse query string as JSON
                try:
                    payload = json.loads(query_str)
                except json.JSONDecodeError as e:
                    return ToolResult(
                        tool_name=self.name,
                        success=False,
                        error=f"Invalid JSON in query_str: {str(e)}"
                    )
                
                # Create and execute query
                query = await client.create_query(project_id, index_id, payload)
                query_id = query["queryId"]
                
                # Wait for query processing to complete
                while query["state"] == "PROCESSING":
                    await asyncio.sleep(1)
                    query = await client.get_query(project_id, index_id, query_id)
                
                if query["state"] == "FINISHED":
                    results = await client.get_query_results(project_id, index_id, query_id)
                    
                    if len(results) > self.MAX_RESULTS:
                        return ToolResult(
                            tool_name=self.name,
                            success=False,
                            error=f"Query returned too many results ({len(results)}), please refine the query."
                        )
                    
                    return ToolResult(
                        tool_name=self.name,
                        success=True,
                        result=results,
                        metadata={
                            "results_count": len(results),
                            "query_id": query_id
                        }
                    )
                else:
                    return ToolResult(
                        tool_name=self.name,
                        success=False,
                        error=f"Query failed with errors: {query.get('errors', 'Unknown error')}"
                    )
            
            finally:
                await client.close()
                
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=str(e)
            )


class ExecuteJQQueryTool(BaseTool):
    """Tool for executing jq queries on JSON data."""
    
    def __init__(self, name: str = "execute_jq_query", description: str = None):
        """Initialize the ExecuteJQQuery tool."""
        if description is None:
            description = (
                "Processes the given JSON input with the given jq query, and returns the result as a JSON."
            )
        super().__init__(name, description)
    
    def _get_parameters_schema(self) -> Dict[str, Any]:
        """Get the parameters schema for this tool."""
        return {
            "type": "object",
            "properties": {
                "jq_query": {
                    "type": "string",
                    "description": "The jq query to execute. For example: '.[] | .Width'"
                },
                "input_json": {
                    "type": "string",
                    "description": "The JSON input to process with the jq query"
                }
            },
            "required": ["jq_query", "input_json"]
        }
    
    async def execute(self, **kwargs) -> ToolResult:
        """Execute the jq query tool."""
        try:
            jq_query = kwargs.get("jq_query")
            input_json = kwargs.get("input_json")
            
            if not jq_query:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error="jq_query parameter is required"
                )
            
            if not input_json:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error="input_json parameter is required"
                )
            
            # Execute jq query
            try:
                result = jq.compile(jq_query).input_text(input_json).all()
                
                return ToolResult(
                    tool_name=self.name,
                    success=True,
                    result=result,
                    metadata={"query": jq_query}
                )
                
            except Exception as jq_error:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error=f"jq query execution failed: {str(jq_error)}"
                )
                
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=str(e)
            )