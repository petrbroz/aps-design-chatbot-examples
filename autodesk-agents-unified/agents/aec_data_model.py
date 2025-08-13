"""
AEC Data Model Agent

Real implementation that makes actual calls to Autodesk AEC Data Model API
via GraphQL to retrieve building element relationships and properties.
"""

import asyncio
import json
import time
from typing import Dict, Any, List, Optional
import aiohttp

from agentcore import (
    BaseAgent, AgentRequest, AgentResponse, AgentCapabilities,
    ExecutionContext, ToolResult, ErrorCodes
)
from agentcore.tools import BaseTool, ToolCategory
from agentcore.models import AgentType
from agentcore.vector_store import OpenSearchVectorStore, Document


class ExecuteGraphQLQueryTool(BaseTool):
    """Tool to execute GraphQL queries against AEC Data Model API."""
    
    def __init__(self, agent_core):
        super().__init__(
            name="execute_graphql_query",
            description="Execute GraphQL queries against Autodesk AEC Data Model API",
            category=ToolCategory.API_CLIENT
        )
        self.agent_core = agent_core
        self.auth_manager = agent_core.auth_manager
        self.cache_manager = agent_core.cache_manager
        self.graphql_endpoint = "https://developer.api.autodesk.com/aec/graphql"
    
    async def execute(self, query: str, variables: Optional[Dict[str, Any]] = None, **kwargs) -> ToolResult:
        """
        Execute GraphQL query.
        
        Args:
            query: GraphQL query string
            variables: Optional query variables
            
        Returns:
            ToolResult with query results
        """
        try:
            # Get authentication token
            auth_context = await self.auth_manager.get_client_token("data:read")
            
            # Prepare GraphQL request
            request_body = {
                "query": query
            }
            
            if variables:
                request_body["variables"] = variables
            
            # Execute GraphQL query
            headers = auth_context.to_headers()
            headers["Content-Type"] = "application/json"
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.graphql_endpoint,
                    json=request_body,
                    headers=headers
                ) as response:
                    
                    if response.status == 200:
                        data = await response.json()
                        
                        # Check for GraphQL errors
                        if "errors" in data:
                            error_messages = [error.get("message", str(error)) for error in data["errors"]]
                            return ToolResult.error(
                                error_message=f"GraphQL errors: {'; '.join(error_messages)}",
                                tool_name=self.name,
                                error_type="GraphQLError"
                            )
                        
                        if self.logger:
                            self.logger.info("GraphQL query executed successfully", extra={
                                "query_length": len(query),
                                "has_variables": bool(variables),
                                "response_size": len(str(data))
                            })
                        
                        return ToolResult(
                            output=data.get("data", {}),
                            success=True,
                            tool_name=self.name,
                            metadata={
                                "query": query,
                                "variables": variables,
                                "response_size": len(str(data))
                            }
                        )
                    
                    else:
                        error_text = await response.text()
                        return ToolResult.error(
                            error_message=f"GraphQL request failed: {response.status} - {error_text}",
                            tool_name=self.name,
                            error_type="HTTPError"
                        )
            
        except Exception as e:
            if self.logger:
                self.logger.error("GraphQL query execution failed", extra={
                    "query_length": len(query),
                    "error": str(e),
                    "error_type": type(e).__name__
                })
            
            return ToolResult.error(
                error_message=f"Failed to execute GraphQL query: {str(e)}",
                tool_name=self.name,
                error_type=type(e).__name__
            )


class GetElementCategoriesTool(BaseTool):
    """Tool to get available element categories from AEC Data Model."""
    
    def __init__(self, agent_core):
        super().__init__(
            name="get_element_categories",
            description="Get available building element categories from AEC Data Model",
            category=ToolCategory.API_CLIENT
        )
        self.agent_core = agent_core
        self.graphql_tool = ExecuteGraphQLQueryTool(agent_core)
    
    async def execute(self, project_id: Optional[str] = None, **kwargs) -> ToolResult:
        """
        Get element categories.
        
        Args:
            project_id: Optional project ID to filter categories
            
        Returns:
            ToolResult with available categories
        """
        try:
            # GraphQL query to get element categories
            query = """
            query GetElementCategories($projectId: ID) {
                elementCategories(projectId: $projectId) {
                    id
                    name
                    description
                    elementCount
                    subcategories {
                        id
                        name
                        elementCount
                    }
                }
            }
            """
            
            variables = {}
            if project_id:
                variables["projectId"] = project_id
            
            # Execute GraphQL query
            result = await self.graphql_tool.execute(query, variables)
            
            if result.success:
                categories = result.output.get("elementCategories", [])
                
                # Format categories for better readability
                formatted_categories = []
                for category in categories:
                    formatted_category = {
                        "id": category.get("id"),
                        "name": category.get("name"),
                        "description": category.get("description"),
                        "element_count": category.get("elementCount", 0),
                        "subcategories": category.get("subcategories", [])
                    }
                    formatted_categories.append(formatted_category)
                
                if self.logger:
                    self.logger.info("Element categories retrieved", extra={
                        "project_id": project_id,
                        "categories_count": len(formatted_categories)
                    })
                
                return ToolResult(
                    output={
                        "categories": formatted_categories,
                        "total_categories": len(formatted_categories),
                        "project_id": project_id
                    },
                    success=True,
                    tool_name=self.name
                )
            else:
                return result  # Pass through the error
            
        except Exception as e:
            if self.logger:
                self.logger.error("Failed to get element categories", extra={
                    "project_id": project_id,
                    "error": str(e),
                    "error_type": type(e).__name__
                })
            
            return ToolResult.error(
                error_message=f"Failed to get element categories: {str(e)}",
                tool_name=self.name,
                error_type=type(e).__name__
            )


class FindRelatedPropertyDefinitionsTool(BaseTool):
    """Tool to find related property definitions using vector search."""
    
    def __init__(self, agent_core, vector_store: OpenSearchVectorStore):
        super().__init__(
            name="find_related_property_definitions",
            description="Find related property definitions using vector similarity search",
            category=ToolCategory.VECTOR_SEARCH
        )
        self.agent_core = agent_core
        self.vector_store = vector_store
        self.cache_manager = agent_core.cache_manager
    
    async def initialize(self, **kwargs) -> None:
        """Initialize the tool and vector store."""
        await super().initialize(**kwargs)
        
        # Initialize vector store
        await self.vector_store.initialize()
        
        # Check if we need to populate the vector store
        doc_count = await self.vector_store.get_document_count()
        if doc_count == 0:
            await self._populate_property_definitions()
    
    async def execute(self, query: str, k: int = 8, **kwargs) -> ToolResult:
        """
        Find related property definitions.
        
        Args:
            query: Search query for property definitions
            k: Number of results to return
            
        Returns:
            ToolResult with related property definitions
        """
        try:
            # Perform vector similarity search
            search_results = await self.vector_store.similarity_search(query, k=k)
            
            # Format results
            formatted_results = []
            for result in search_results:
                formatted_result = {
                    "content": result.document.content,
                    "metadata": result.document.metadata,
                    "similarity_score": result.score,
                    "rank": result.rank
                }
                formatted_results.append(formatted_result)
            
            if self.logger:
                self.logger.info("Property definitions search completed", extra={
                    "query": query,
                    "results_count": len(formatted_results),
                    "k": k
                })
            
            return ToolResult(
                output={
                    "query": query,
                    "results": formatted_results,
                    "total_results": len(formatted_results)
                },
                success=True,
                tool_name=self.name
            )
            
        except Exception as e:
            if self.logger:
                self.logger.error("Property definitions search failed", extra={
                    "query": query,
                    "k": k,
                    "error": str(e),
                    "error_type": type(e).__name__
                })
            
            return ToolResult.error(
                error_message=f"Failed to search property definitions: {str(e)}",
                tool_name=self.name,
                error_type=type(e).__name__
            )
    
    async def _populate_property_definitions(self) -> None:
        """Populate vector store with property definitions."""
        try:
            if self.logger:
                self.logger.info("Populating vector store with property definitions")
            
            # Sample property definitions (in production, these would come from AEC Data Model API)
            property_definitions = [
                {
                    "content": "Wall Height: The vertical dimension of a wall element from bottom to top",
                    "metadata": {"category": "Walls", "type": "Dimension", "units": "length"}
                },
                {
                    "content": "Wall Thickness: The horizontal dimension of a wall element perpendicular to its length",
                    "metadata": {"category": "Walls", "type": "Dimension", "units": "length"}
                },
                {
                    "content": "Wall Material: The primary construction material used for the wall element",
                    "metadata": {"category": "Walls", "type": "Material", "units": "text"}
                },
                {
                    "content": "Door Width: The horizontal opening dimension of a door element",
                    "metadata": {"category": "Doors", "type": "Dimension", "units": "length"}
                },
                {
                    "content": "Door Height: The vertical opening dimension of a door element",
                    "metadata": {"category": "Doors", "type": "Dimension", "units": "length"}
                },
                {
                    "content": "Door Type: The classification of door based on operation method (swing, sliding, revolving)",
                    "metadata": {"category": "Doors", "type": "Classification", "units": "text"}
                },
                {
                    "content": "Window Area: The total glazed area of a window element",
                    "metadata": {"category": "Windows", "type": "Area", "units": "area"}
                },
                {
                    "content": "Window Frame Material: The material used for the window frame construction",
                    "metadata": {"category": "Windows", "type": "Material", "units": "text"}
                },
                {
                    "content": "Floor Area: The total surface area of a floor element",
                    "metadata": {"category": "Floors", "type": "Area", "units": "area"}
                },
                {
                    "content": "Floor Load Capacity: The maximum load that a floor element can support",
                    "metadata": {"category": "Floors", "type": "Structural", "units": "force"}
                },
                {
                    "content": "Beam Length: The span dimension of a structural beam element",
                    "metadata": {"category": "Structural", "type": "Dimension", "units": "length"}
                },
                {
                    "content": "Column Cross Section: The geometric properties of a structural column",
                    "metadata": {"category": "Structural", "type": "Geometry", "units": "area"}
                },
                {
                    "content": "HVAC Airflow Rate: The volume of air moved by an HVAC system per unit time",
                    "metadata": {"category": "Mechanical", "type": "Performance", "units": "volume_flow"}
                },
                {
                    "content": "Electrical Load: The power consumption of an electrical element or system",
                    "metadata": {"category": "Electrical", "type": "Performance", "units": "power"}
                },
                {
                    "content": "Pipe Diameter: The internal diameter of a plumbing pipe element",
                    "metadata": {"category": "Plumbing", "type": "Dimension", "units": "length"}
                }
            ]
            
            # Create documents
            documents = [
                Document(content=prop["content"], metadata=prop["metadata"])
                for prop in property_definitions
            ]
            
            # Add to vector store
            await self.vector_store.add_documents(documents)
            
            if self.logger:
                self.logger.info("Vector store populated with property definitions", extra={
                    "document_count": len(documents)
                })
                
        except Exception as e:
            if self.logger:
                self.logger.error("Failed to populate property definitions", extra={
                    "error": str(e),
                    "error_type": type(e).__name__
                })
            raise


class ExecuteJQQueryTool(BaseTool):
    """Tool to execute JQ-style queries on AEC data."""
    
    def __init__(self, agent_core):
        super().__init__(
            name="execute_jq_query",
            description="Execute JQ-style queries to filter and transform AEC data",
            category=ToolCategory.DATA_PROCESSING
        )
        self.agent_core = agent_core
        self.cache_manager = agent_core.cache_manager
    
    async def execute(self, data: Dict[str, Any], jq_query: str, **kwargs) -> ToolResult:
        """
        Execute JQ query on data.
        
        Args:
            data: Data to query
            jq_query: JQ-style query string
            
        Returns:
            ToolResult with query results
        """
        try:
            # Execute simplified JQ-like query
            results = await self._execute_query(data, jq_query)
            
            if self.logger:
                self.logger.info("JQ query executed on AEC data", extra={
                    "query": jq_query,
                    "data_keys": list(data.keys()) if isinstance(data, dict) else "non_dict",
                    "results_type": type(results).__name__
                })
            
            return ToolResult(
                output={
                    "query": jq_query,
                    "results": results
                },
                success=True,
                tool_name=self.name
            )
            
        except Exception as e:
            if self.logger:
                self.logger.error("Failed to execute JQ query on AEC data", extra={
                    "query": jq_query,
                    "error": str(e),
                    "error_type": type(e).__name__
                })
            
            return ToolResult.error(
                error_message=f"Failed to execute JQ query: {str(e)}",
                tool_name=self.name,
                error_type=type(e).__name__
            )
    
    async def _execute_query(self, data: Dict[str, Any], query: str) -> Any:
        """Execute simplified JQ-like query."""
        # Simplified JQ implementation for AEC data
        
        if query == ".":
            return data
        elif query == ".categories":
            return data.get("categories", [])
        elif query == ".elements":
            return data.get("elements", [])
        elif query.startswith(".categories[] | select(.name =="):
            # Extract category name from query
            category_name = query.split('"')[1]
            categories = data.get("categories", [])
            return [cat for cat in categories if cat.get("name") == category_name]
        elif query.startswith(".elements[] | select(.category =="):
            # Extract category from query
            category = query.split('"')[1]
            elements = data.get("elements", [])
            return [elem for elem in elements if elem.get("category") == category]
        elif query == ".categories | length":
            return len(data.get("categories", []))
        elif query == ".elements | length":
            return len(data.get("elements", []))
        else:
            # Default: return the whole data
            return data


class AECDataModelAgent(BaseAgent):
    """
    AEC Data Model Agent that makes real calls to Autodesk AEC Data Model API.
    
    Provides functionality to query building element relationships, categories,
    and property definitions using GraphQL and vector search.
    """
    
    def __init__(self, agent_core, agent_config: Dict[str, Any]):
        """Initialize AEC Data Model agent."""
        super().__init__(agent_core, agent_config)
        
        # Initialize AWS OpenSearch vector store
        specific_config = agent_config.get("specific_config", {})
        opensearch_endpoint = (
            specific_config.get("aws_opensearch_endpoint") or 
            agent_core.config.aws_opensearch_endpoint
        )
        
        self.vector_store = OpenSearchVectorStore(
            opensearch_endpoint=opensearch_endpoint,
            region_name=agent_core.config.aws_region,
            index_name=f"agentcore_aec_{agent_config.get('environment', 'dev')}",
            use_aws_auth=agent_core.config.opensearch_use_aws_auth
        )
        
        self.vector_store.set_logger(self.logger)
    
    async def initialize(self) -> None:
        """Initialize the agent and register tools."""
        if self._initialized:
            return
        
        # Create and register tools
        tools = [
            ExecuteGraphQLQueryTool(self.agent_core),
            GetElementCategoriesTool(self.agent_core),
            FindRelatedPropertyDefinitionsTool(self.agent_core, self.vector_store),
            ExecuteJQQueryTool(self.agent_core)
        ]
        
        for tool in tools:
            await tool.initialize()
            self.register_tool(tool.name, tool)
        
        self.logger.info("AEC Data Model agent initialized", extra={
            "tools_count": len(tools),
            "tools": [tool.name for tool in tools],
            "vector_store_index": self.vector_store.index_name
        })
        
        await super().initialize()
    
    async def process_prompt(self, request: AgentRequest, context: ExecutionContext) -> AgentResponse:
        """Process user prompt for AEC data model operations."""
        
        prompt = request.prompt.lower()
        project_id = context.project_id or request.context.get("project_id")
        
        try:
            responses = []
            
            # Determine operation based on prompt
            if "categories" in prompt or "category" in prompt:
                # Get element categories
                tool_result = await self.execute_tool(
                    "get_element_categories",
                    project_id=project_id
                )
                
                if tool_result.success:
                    output = tool_result.output
                    categories = output.get("categories", [])
                    
                    responses.extend([
                        f"🏗️ Building Element Categories",
                        f"📊 Found {len(categories)} categories"
                    ])
                    
                    if project_id:
                        responses.append(f"🏢 Project: {project_id}")
                    
                    responses.append("\n📂 Available Categories:")
                    
                    for category in categories[:10]:  # Show first 10
                        element_count = category.get("element_count", 0)
                        responses.append(f"  • {category['name']}: {element_count} elements")
                        
                        # Show subcategories if available
                        subcategories = category.get("subcategories", [])
                        if subcategories:
                            for subcat in subcategories[:3]:  # Show first 3 subcategories
                                responses.append(f"    - {subcat['name']}: {subcat.get('elementCount', 0)} elements")
                    
                    if len(categories) > 10:
                        responses.append(f"  ... and {len(categories) - 10} more categories")
                else:
                    responses.append(f"❌ Failed to get categories: {tool_result.error_message}")
            
            elif "property" in prompt or "definition" in prompt:
                # Search property definitions
                search_terms = self._extract_search_terms(prompt)
                
                tool_result = await self.execute_tool(
                    "find_related_property_definitions",
                    query=search_terms,
                    k=8
                )
                
                if tool_result.success:
                    output = tool_result.output
                    results = output.get("results", [])
                    
                    responses.extend([
                        f"🔍 Property Definition Search: '{search_terms}'",
                        f"📊 Found {len(results)} related definitions"
                    ])
                    
                    responses.append("\n📋 Related Property Definitions:")
                    
                    for i, result in enumerate(results[:5]):  # Show top 5
                        score = result.get("similarity_score", 0)
                        content = result.get("content", "")
                        metadata = result.get("metadata", {})
                        
                        responses.append(f"\n  {i+1}. {content}")
                        responses.append(f"     Category: {metadata.get('category', 'Unknown')}")
                        responses.append(f"     Type: {metadata.get('type', 'Unknown')}")
                        responses.append(f"     Similarity: {score:.3f}")
                    
                    if len(results) > 5:
                        responses.append(f"\n  ... and {len(results) - 5} more definitions")
                else:
                    responses.append(f"❌ Property search failed: {tool_result.error_message}")
            
            elif "graphql" in prompt or "query" in prompt:
                # Help with GraphQL queries
                responses.extend([
                    "📊 GraphQL Query Examples for AEC Data Model:",
                    "",
                    "🏗️ Get Element Categories:",
                    "```graphql",
                    "query GetCategories {",
                    "  elementCategories {",
                    "    id name description elementCount",
                    "  }",
                    "}",
                    "```",
                    "",
                    "🔍 Get Elements by Category:",
                    "```graphql", 
                    "query GetElements($category: String!) {",
                    "  elements(category: $category) {",
                    "    id name properties { key value }",
                    "  }",
                    "}",
                    "```",
                    "",
                    "💡 Use 'Execute GraphQL query' with your custom queries!"
                ])
            
            else:
                # General help
                responses.extend([
                    "🏢 AEC Data Model Agent - Real GraphQL API Integration",
                    "",
                    "I can help you work with building element data and relationships:",
                    "",
                    "📋 Available Operations:",
                    "• 'Show categories' - List all building element categories",
                    "• 'Find property definitions for [term]' - Search property definitions",
                    "• 'GraphQL examples' - Show sample GraphQL queries",
                    "• 'Execute GraphQL query' - Run custom GraphQL queries",
                    "",
                    "🔧 Real API Integration:",
                    "• Autodesk AEC Data Model GraphQL API",
                    "• OpenSearch vector search for property definitions",
                    "• AWS Bedrock embeddings for semantic search",
                    "",
                    f"📋 Current Context: {f'Project {project_id}' if project_id else 'No project specified'}",
                    "",
                    "💡 Try: 'Show categories' to explore building elements!"
                ])
            
            return AgentResponse(
                responses=responses,
                success=True,
                metadata={
                    "project_id": project_id,
                    "operation_detected": self._detect_operation(prompt),
                    "tools_available": list(self._tools.keys()),
                    "vector_store_ready": await self.vector_store.get_document_count() > 0
                }
            )
            
        except Exception as e:
            self.logger.error("Error processing AEC data model prompt", extra={
                "prompt": request.prompt,
                "project_id": project_id,
                "error": str(e),
                "error_type": type(e).__name__
            })
            
            return AgentResponse.error(
                error_message=f"Failed to process request: {str(e)}",
                error_code=ErrorCodes.UNKNOWN_ERROR,
                agent_type=self.get_agent_type()
            )
    
    def _extract_search_terms(self, prompt: str) -> str:
        """Extract search terms from user prompt."""
        words = prompt.split()
        
        # Look for terms after trigger words
        trigger_words = ["property", "definition", "find", "search", "for"]
        search_terms = []
        
        capture = False
        for word in words:
            if word.lower() in trigger_words:
                capture = True
                continue
            if capture and word.lower() not in ["definitions", "properties", "in", "the"]:
                search_terms.append(word)
        
        return " ".join(search_terms) if search_terms else "building properties"
    
    def _detect_operation(self, prompt: str) -> str:
        """Detect the intended operation from prompt."""
        prompt_lower = prompt.lower()
        
        if "categories" in prompt_lower or "category" in prompt_lower:
            return "get_categories"
        elif "property" in prompt_lower or "definition" in prompt_lower:
            return "search_properties"
        elif "graphql" in prompt_lower:
            return "graphql_help"
        else:
            return "help"
    
    def get_capabilities(self) -> AgentCapabilities:
        """Get agent capabilities."""
        return AgentCapabilities(
            agent_type=self.get_agent_type(),
            name="AEC Data Model Agent",
            description="Analyzes building element relationships and properties using GraphQL and vector search",
            version="1.0.0",
            tools=["execute_graphql_query", "get_element_categories", "find_related_property_definitions", "execute_jq_query"],
            supported_formats=["json", "text", "graphql"],
            max_prompt_length=2000,
            requires_authentication=True,
            requires_project_context=False,
            requires_internet=True,
            typical_response_time_ms=3000
        )
    
    def get_agent_type(self) -> str:
        """Return agent type."""
        return AgentType.AEC_DATA_MODEL.value
    
    async def shutdown(self) -> None:
        """Shutdown the agent and cleanup resources."""
        await super().shutdown()
        
        # Shutdown vector store
        if hasattr(self, 'vector_store'):
            await self.vector_store.shutdown()