"""
AEC Data Model tools for the AgentCore framework.

This module provides tools for working with Autodesk AEC Data Model API,
including GraphQL queries, element categories, JSON processing, and
property definition search using OpenSearch.
"""

import json
import jq
from typing import Dict, Any, List, Optional
from gql import Client, gql
from gql.transport.aiohttp import AIOHTTPTransport
from langchain_core.documents import Document

from ..base_agent import BaseTool
from ..models import ToolResult
from ..vector_store import OpenSearchVectorStore
from ..auth import AuthContext


class ExecuteGraphQLQueryTool(BaseTool):
    """Tool for executing GraphQL queries against the AEC Data Model API."""
    
    def __init__(self):
        super().__init__(
            name="execute_graphql_query",
            description="Executes the given GraphQL query in Autodesk AEC Data Model API, and returns the result as a JSON."
        )
        self.aecdm_endpoint = "https://developer.api.autodesk.com/aec/graphql"
        self.max_response_size = (1 << 16)  # 64KB limit
    
    def _get_parameters_schema(self) -> Dict[str, Any]:
        """Get the parameters schema for this tool."""
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The GraphQL query to execute"
                }
            },
            "required": ["query"]
        }
    
    async def execute(self, query: str, auth_context: AuthContext, **kwargs) -> ToolResult:
        """
        Execute a GraphQL query against the AEC Data Model API.
        
        Args:
            query: The GraphQL query to execute
            auth_context: Authentication context with access token
            **kwargs: Additional parameters (ignored)
            
        Returns:
            ToolResult with the query result or error
        """
        try:
            if not auth_context or not auth_context.access_token:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error="Authentication context with access token is required"
                )
            
            # Create GraphQL client
            transport = AIOHTTPTransport(
                url=self.aecdm_endpoint,
                headers={"Authorization": f"Bearer {auth_context.access_token}"}
            )
            client = Client(transport=transport, fetch_schema_from_transport=True)
            
            # Execute the query
            result = await client.execute_async(gql(query))
            
            # Check response size to avoid overwhelming the context window
            result_json = json.dumps(result)
            if len(result_json) > self.max_response_size:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error=f"Result is too large ({len(result_json)} bytes). Please refine your query to return less data."
                )
            
            return ToolResult(
                tool_name=self.name,
                success=True,
                result=result
            )
            
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"GraphQL query execution failed: {str(e)}"
            )


class GetElementCategoriesTool(BaseTool):
    """Tool for retrieving all element categories from the AEC Data Model."""
    
    def __init__(self):
        super().__init__(
            name="get_element_categories",
            description="Returns all element categories available in the AEC Data Model API for the current element group."
        )
    
    def _get_parameters_schema(self) -> Dict[str, Any]:
        """Get the parameters schema for this tool."""
        return {
            "type": "object",
            "properties": {},
            "required": []
        }
    
    async def execute(self, auth_context: AuthContext, cache_dir: str, **kwargs) -> ToolResult:
        """
        Get all element categories for the current element group.
        
        Args:
            auth_context: Authentication context with access token and element_group_id
            cache_dir: Directory for caching results
            **kwargs: Additional parameters (ignored)
            
        Returns:
            ToolResult with list of element categories or error
        """
        try:
            if not auth_context or not auth_context.access_token:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error="Authentication context with access token is required"
                )
            
            if not auth_context.element_group_id:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error="Element group ID is required in authentication context"
                )
            
            # Check cache first
            import os
            categories_cache_path = os.path.join(cache_dir, "categories.json")
            
            if os.path.exists(categories_cache_path):
                with open(categories_cache_path, 'r') as f:
                    element_categories = json.load(f)
                
                return ToolResult(
                    tool_name=self.name,
                    success=True,
                    result=element_categories
                )
            
            # Fetch from API if not cached
            transport = AIOHTTPTransport(
                url="https://developer.api.autodesk.com/aec/graphql",
                headers={"Authorization": f"Bearer {auth_context.access_token}"}
            )
            client = Client(transport=transport, fetch_schema_from_transport=True)
            
            query = gql("""
                query GetElementsFromCategory($elementGroupId: ID!, $cursor: String) {
                    elementsByElementGroup(
                        elementGroupId: $elementGroupId
                        pagination: {cursor: $cursor}
                    ) {
                        pagination {
                            cursor
                        }
                        results {
                            properties(filter: {names: ["Revit Category Type Id"]}) {
                                results {
                                    value
                                }
                            }
                        }
                    }
                }
            """)
            
            element_categories_set = set()
            response = await client.execute_async(
                query, 
                variable_values={"elementGroupId": auth_context.element_group_id}
            )
            
            # Process first page
            for element in response["elementsByElementGroup"]["results"]:
                element_categories_set.update(
                    result["value"] for result in element["properties"]["results"]
                )
            
            # Process remaining pages
            while response["elementsByElementGroup"]["pagination"]["cursor"]:
                cursor = response["elementsByElementGroup"]["pagination"]["cursor"]
                response = await client.execute_async(
                    query, 
                    variable_values={
                        "elementGroupId": auth_context.element_group_id, 
                        "cursor": cursor
                    }
                )
                
                for element in response["elementsByElementGroup"]["results"]:
                    element_categories_set.update(
                        result["value"] for result in element["properties"]["results"]
                    )
            
            element_categories = list(element_categories_set)
            
            # Cache the results
            os.makedirs(cache_dir, exist_ok=True)
            with open(categories_cache_path, 'w') as f:
                json.dump(element_categories, f)
            
            return ToolResult(
                tool_name=self.name,
                success=True,
                result=element_categories
            )
            
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"Failed to get element categories: {str(e)}"
            )


class ExecuteJQQueryTool(BaseTool):
    """Tool for processing JSON data with jq queries."""
    
    def __init__(self):
        super().__init__(
            name="execute_jq_query",
            description="Processes the given JSON input with the given jq query, and returns the result as a JSON."
        )
    
    def _get_parameters_schema(self) -> Dict[str, Any]:
        """Get the parameters schema for this tool."""
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The jq query to execute"
                },
                "input_json": {
                    "type": "string",
                    "description": "The JSON input to process"
                }
            },
            "required": ["query", "input_json"]
        }
    
    async def execute(self, query: str, input_json: str, **kwargs) -> ToolResult:
        """
        Execute a jq query on JSON input.
        
        Args:
            query: The jq query to execute
            input_json: The JSON input to process
            **kwargs: Additional parameters (ignored)
            
        Returns:
            ToolResult with the processed result or error
        """
        try:
            # Compile and execute the jq query
            result = jq.compile(query).input_text(input_json).all()
            
            return ToolResult(
                tool_name=self.name,
                success=True,
                result=result
            )
            
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"jq query execution failed: {str(e)}"
            )


class FindRelatedPropertyDefinitionsTool(BaseTool):
    """Tool for finding related property definitions using OpenSearch vector search."""
    
    def __init__(self, vector_store: OpenSearchVectorStore):
        super().__init__(
            name="find_related_property_definitions",
            description="Finds property definitions in the AEC Data Model API that are relevant to the input query using semantic search."
        )
        self.vector_store = vector_store
    
    def _get_parameters_schema(self) -> Dict[str, Any]:
        """Get the parameters schema for this tool."""
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query to find related property definitions"
                },
                "k": {
                    "type": "integer",
                    "description": "Number of results to return (default: 8)",
                    "default": 8
                }
            },
            "required": ["query"]
        }
    
    async def execute(self, query: str, k: int = 8, **kwargs) -> ToolResult:
        """
        Find property definitions related to the query using vector search.
        
        Args:
            query: The search query
            k: Number of results to return
            **kwargs: Additional parameters (ignored)
            
        Returns:
            ToolResult with related property definitions or error
        """
        try:
            # Ensure vector store is initialized
            if not self.vector_store._initialized:
                await self.vector_store.initialize()
            
            # Perform similarity search
            documents = await self.vector_store.similarity_search(query, k=k)
            
            # Extract property information from documents
            properties = []
            for doc in documents:
                # Parse the document content to extract property information
                content = doc.page_content
                metadata = doc.metadata
                
                # Try to extract structured property information
                property_info = {
                    "content": content,
                    "score": metadata.get("_score", 0.0),
                    "id": metadata.get("_id"),
                    "timestamp": metadata.get("timestamp")
                }
                
                # Try to parse property details from content
                if "Property Name:" in content:
                    lines = content.split('\n')
                    for line in lines:
                        if line.startswith("Property Name:"):
                            property_info["name"] = line.replace("Property Name:", "").strip()
                        elif line.startswith("ID:"):
                            property_info["property_id"] = line.replace("ID:", "").strip()
                        elif line.startswith("Description:"):
                            property_info["description"] = line.replace("Description:", "").strip()
                        elif line.startswith("Units:"):
                            property_info["units"] = line.replace("Units:", "").strip()
                
                properties.append(property_info)
            
            return ToolResult(
                tool_name=self.name,
                success=True,
                result={
                    "query": query,
                    "results_count": len(properties),
                    "properties": properties
                }
            )
            
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"Property definition search failed: {str(e)}"
            )


class PropertyDefinitionsManager:
    """Manager for property definitions caching and vector store population."""
    
    def __init__(self, vector_store: OpenSearchVectorStore):
        self.vector_store = vector_store
        self.aecdm_endpoint = "https://developer.api.autodesk.com/aec/graphql"
    
    async def get_property_definitions(
        self, 
        element_group_id: str, 
        access_token: str, 
        cache_dir: str
    ) -> List[Dict[str, Any]]:
        """
        Get property definitions for an element group, with caching.
        
        Args:
            element_group_id: The element group ID
            access_token: Access token for API authentication
            cache_dir: Directory for caching results
            
        Returns:
            List of property definitions
        """
        import os
        
        props_cache_path = os.path.join(cache_dir, "props.json")
        
        # Check cache first
        if os.path.exists(props_cache_path):
            with open(props_cache_path, 'r') as f:
                return json.load(f)
        
        # Fetch from API if not cached
        transport = AIOHTTPTransport(
            url=self.aecdm_endpoint,
            headers={"Authorization": f"Bearer {access_token}"}
        )
        client = Client(transport=transport, fetch_schema_from_transport=True)
        
        query = gql("""
            query GetPropertyDefinitions($elementGroupId: ID!, $cursor: String) {
                elementGroupAtTip(elementGroupId:$elementGroupId) {
                    propertyDefinitions(pagination:{cursor:$cursor}) {
                        pagination {
                            cursor
                        }
                        results {
                            id
                            name
                            description
                            units {
                                id
                                name
                            }
                        }
                    }
                }
            }
        """)
        
        property_definitions = []
        response = await client.execute_async(
            query, 
            variable_values={"elementGroupId": element_group_id}
        )
        
        # Process first page
        property_definitions.extend(
            response["elementGroupAtTip"]["propertyDefinitions"]["results"]
        )
        
        # Process remaining pages
        while response["elementGroupAtTip"]["propertyDefinitions"]["pagination"]["cursor"]:
            cursor = response["elementGroupAtTip"]["propertyDefinitions"]["pagination"]["cursor"]
            response = await client.execute_async(
                query, 
                variable_values={"elementGroupId": element_group_id, "cursor": cursor}
            )
            property_definitions.extend(
                response["elementGroupAtTip"]["propertyDefinitions"]["results"]
            )
        
        # Cache the results
        os.makedirs(cache_dir, exist_ok=True)
        with open(props_cache_path, 'w') as f:
            json.dump(property_definitions, f)
        
        return property_definitions
    
    async def populate_vector_store(
        self, 
        element_group_id: str, 
        access_token: str, 
        cache_dir: str
    ) -> None:
        """
        Populate the vector store with property definitions.
        
        Args:
            element_group_id: The element group ID
            access_token: Access token for API authentication
            cache_dir: Directory for caching results
        """
        # Get property definitions
        property_definitions = await self.get_property_definitions(
            element_group_id, access_token, cache_dir
        )
        
        # Convert to documents for vector store
        documents = []
        for prop in property_definitions:
            content = (
                f"Property Name: {prop['name']}\n"
                f"ID: {prop['id']}\n"
                f"Description: {prop['description']}\n"
                f"Units: {prop['units']['name'] if prop['units'] and prop['units']['name'] else ''}"
            )
            
            doc = Document(
                page_content=content,
                metadata={
                    "property_id": prop['id'],
                    "property_name": prop['name'],
                    "element_group_id": element_group_id,
                    "type": "property_definition"
                }
            )
            documents.append(doc)
        
        # Add documents to vector store
        if documents:
            await self.vector_store.add_documents(documents)
    
    async def ensure_vector_store_populated(
        self, 
        element_group_id: str, 
        access_token: str, 
        cache_dir: str
    ) -> None:
        """
        Ensure the vector store is populated with property definitions.
        
        Args:
            element_group_id: The element group ID
            access_token: Access token for API authentication
            cache_dir: Directory for caching results
        """
        # Check if vector store has documents for this element group
        try:
            # Try a test search to see if we have data
            test_results = await self.vector_store.similarity_search(
                "test", k=1, filter_dict={"element_group_id": element_group_id}
            )
            
            # If no results, populate the vector store
            if not test_results:
                await self.populate_vector_store(element_group_id, access_token, cache_dir)
                
        except Exception:
            # If there's any error, try to populate the vector store
            await self.populate_vector_store(element_group_id, access_token, cache_dir)