"""
Model Properties Agent

Real implementation that makes actual calls to Autodesk Platform Services
to retrieve and analyze model properties from design files.
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
from agentcore.tools import BaseTool, ToolCategory, ToolRegistry
from agentcore.models import AgentType


class CreateIndexTool(BaseTool):
    """Tool to create a properties index from Autodesk model data."""
    
    def __init__(self, agent_core):
        super().__init__(
            name="create_index",
            description="Create a searchable index of model properties from Autodesk design files",
            category=ToolCategory.API_CLIENT
        )
        self.agent_core = agent_core
        self.auth_manager = agent_core.auth_manager
        self.cache_manager = agent_core.cache_manager
    
    async def execute(self, project_id: str, version_id: str, **kwargs) -> ToolResult:
        """
        Create properties index for a model version.
        
        Args:
            project_id: Autodesk project ID
            version_id: Model version ID
            
        Returns:
            ToolResult with index creation status and metadata
        """
        try:
            # Get authentication token
            auth_context = await self.auth_manager.get_client_token("data:read")
            
            # Check cache first
            cache_key = f"index_{project_id}_{version_id}"
            cached_index = await self.cache_manager.get("model_properties", cache_key)
            
            if cached_index:
                if self.logger:
                    self.logger.info("Using cached properties index", extra={
                        "project_id": project_id,
                        "version_id": version_id
                    })
                
                return ToolResult(
                    output={
                        "status": "success",
                        "message": "Properties index loaded from cache",
                        "index_size": len(cached_index.get("properties", [])),
                        "cached": True,
                        "index_data": cached_index
                    },
                    success=True,
                    tool_name=self.name
                )
            
            # Fetch model properties from Autodesk API
            properties_data = await self._fetch_model_properties(
                auth_context, project_id, version_id
            )
            
            # Create searchable index
            index_data = await self._create_searchable_index(properties_data)
            
            # Cache the index
            await self.cache_manager.set(
                "model_properties", 
                cache_key, 
                index_data, 
                ttl_seconds=3600,  # 1 hour
                persist=True
            )
            
            if self.logger:
                self.logger.info("Properties index created", extra={
                    "project_id": project_id,
                    "version_id": version_id,
                    "properties_count": len(index_data.get("properties", []))
                })
            
            return ToolResult(
                output={
                    "status": "success",
                    "message": "Properties index created successfully",
                    "index_size": len(index_data.get("properties", [])),
                    "cached": False,
                    "index_data": index_data
                },
                success=True,
                tool_name=self.name
            )
            
        except Exception as e:
            if self.logger:
                self.logger.error("Failed to create properties index", extra={
                    "project_id": project_id,
                    "version_id": version_id,
                    "error": str(e),
                    "error_type": type(e).__name__
                })
            
            return ToolResult.error(
                error_message=f"Failed to create properties index: {str(e)}",
                tool_name=self.name,
                error_type=type(e).__name__
            )
    
    async def _fetch_model_properties(self, auth_context, project_id: str, version_id: str) -> Dict[str, Any]:
        """Fetch model properties from Autodesk Platform Services."""
        
        # Get model URN from version
        urn = await self._get_model_urn(auth_context, project_id, version_id)
        
        # Fetch properties using Model Derivative API
        properties_url = f"https://developer.api.autodesk.com/modelderivative/v2/designdata/{urn}/properties"
        
        headers = auth_context.to_headers()
        
        async with aiohttp.ClientSession() as session:
            async with session.get(properties_url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    return data
                else:
                    error_text = await response.text()
                    raise Exception(f"Failed to fetch properties: {response.status} - {error_text}")
    
    async def _get_model_urn(self, auth_context, project_id: str, version_id: str) -> str:
        """Get model URN from project and version IDs."""
        
        # Get version details
        version_url = f"https://developer.api.autodesk.com/data/v1/projects/{project_id}/versions/{version_id}"
        headers = auth_context.to_headers()
        
        async with aiohttp.ClientSession() as session:
            async with session.get(version_url, headers=headers) as response:
                if response.status == 200:
                    version_data = await response.json()
                    # Extract URN from storage location
                    storage_location = version_data["data"]["relationships"]["storage"]["data"]["id"]
                    # Convert to base64 URN format
                    import base64
                    urn = base64.b64encode(storage_location.encode()).decode()
                    return f"urn:adsk.objects:os.object:{urn}"
                else:
                    error_text = await response.text()
                    raise Exception(f"Failed to get model URN: {response.status} - {error_text}")
    
    async def _create_searchable_index(self, properties_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a searchable index from properties data."""
        
        index = {
            "created_at": time.time(),
            "properties": [],
            "categories": {},
            "statistics": {}
        }
        
        # Process properties data
        if "data" in properties_data and "collection" in properties_data["data"]:
            for item in properties_data["data"]["collection"]:
                if "properties" in item:
                    for prop_group in item["properties"]:
                        category = prop_group.get("displayCategory", "General")
                        
                        if category not in index["categories"]:
                            index["categories"][category] = []
                        
                        for prop_name, prop_value in prop_group.get("properties", {}).items():
                            property_entry = {
                                "name": prop_name,
                                "value": prop_value.get("displayValue", prop_value.get("value")),
                                "category": category,
                                "type": prop_value.get("type", "string"),
                                "units": prop_value.get("units"),
                                "object_id": item.get("objectid")
                            }
                            
                            index["properties"].append(property_entry)
                            index["categories"][category].append(prop_name)
        
        # Calculate statistics
        index["statistics"] = {
            "total_properties": len(index["properties"]),
            "categories_count": len(index["categories"]),
            "unique_names": len(set(prop["name"] for prop in index["properties"]))
        }
        
        return index


class QueryIndexTool(BaseTool):
    """Tool to query the properties index."""
    
    def __init__(self, agent_core):
        super().__init__(
            name="query_index",
            description="Query the properties index to find specific properties or values",
            category=ToolCategory.QUERY_EXECUTION
        )
        self.agent_core = agent_core
        self.cache_manager = agent_core.cache_manager
    
    async def execute(self, project_id: str, version_id: str, query: str, **kwargs) -> ToolResult:
        """
        Query the properties index.
        
        Args:
            project_id: Autodesk project ID
            version_id: Model version ID
            query: Search query
            
        Returns:
            ToolResult with matching properties
        """
        try:
            # Get cached index
            cache_key = f"index_{project_id}_{version_id}"
            index_data = await self.cache_manager.get("model_properties", cache_key)
            
            if not index_data:
                return ToolResult.error(
                    error_message="Properties index not found. Please create index first.",
                    tool_name=self.name,
                    error_type="IndexNotFound"
                )
            
            # Perform search
            results = await self._search_properties(index_data, query)
            
            if self.logger:
                self.logger.info("Properties query executed", extra={
                    "project_id": project_id,
                    "version_id": version_id,
                    "query": query,
                    "results_count": len(results)
                })
            
            return ToolResult(
                output={
                    "query": query,
                    "results_count": len(results),
                    "results": results,
                    "index_stats": index_data.get("statistics", {})
                },
                success=True,
                tool_name=self.name
            )
            
        except Exception as e:
            if self.logger:
                self.logger.error("Failed to query properties index", extra={
                    "project_id": project_id,
                    "version_id": version_id,
                    "query": query,
                    "error": str(e),
                    "error_type": type(e).__name__
                })
            
            return ToolResult.error(
                error_message=f"Failed to query properties: {str(e)}",
                tool_name=self.name,
                error_type=type(e).__name__
            )
    
    async def _search_properties(self, index_data: Dict[str, Any], query: str) -> List[Dict[str, Any]]:
        """Search properties in the index."""
        query_lower = query.lower()
        results = []
        
        for prop in index_data.get("properties", []):
            # Search in property name and value
            if (query_lower in prop["name"].lower() or 
                (prop["value"] and query_lower in str(prop["value"]).lower()) or
                query_lower in prop["category"].lower()):
                results.append(prop)
        
        return results


class ListIndexPropertiesTool(BaseTool):
    """Tool to list all properties in the index."""
    
    def __init__(self, agent_core):
        super().__init__(
            name="list_index_properties",
            description="List all properties available in the model properties index",
            category=ToolCategory.QUERY_EXECUTION
        )
        self.agent_core = agent_core
        self.cache_manager = agent_core.cache_manager
    
    async def execute(self, project_id: str, version_id: str, category: Optional[str] = None, **kwargs) -> ToolResult:
        """
        List properties in the index.
        
        Args:
            project_id: Autodesk project ID
            version_id: Model version ID
            category: Optional category filter
            
        Returns:
            ToolResult with properties list
        """
        try:
            # Get cached index
            cache_key = f"index_{project_id}_{version_id}"
            index_data = await self.cache_manager.get("model_properties", cache_key)
            
            if not index_data:
                return ToolResult.error(
                    error_message="Properties index not found. Please create index first.",
                    tool_name=self.name,
                    error_type="IndexNotFound"
                )
            
            # Filter by category if specified
            properties = index_data.get("properties", [])
            if category:
                properties = [prop for prop in properties if prop["category"].lower() == category.lower()]
            
            # Group by category
            categories = {}
            for prop in properties:
                cat = prop["category"]
                if cat not in categories:
                    categories[cat] = []
                categories[cat].append({
                    "name": prop["name"],
                    "type": prop["type"],
                    "sample_value": prop["value"]
                })
            
            if self.logger:
                self.logger.info("Properties listed", extra={
                    "project_id": project_id,
                    "version_id": version_id,
                    "category_filter": category,
                    "properties_count": len(properties)
                })
            
            return ToolResult(
                output={
                    "total_properties": len(properties),
                    "categories": categories,
                    "statistics": index_data.get("statistics", {}),
                    "filter_applied": category
                },
                success=True,
                tool_name=self.name
            )
            
        except Exception as e:
            if self.logger:
                self.logger.error("Failed to list properties", extra={
                    "project_id": project_id,
                    "version_id": version_id,
                    "error": str(e),
                    "error_type": type(e).__name__
                })
            
            return ToolResult.error(
                error_message=f"Failed to list properties: {str(e)}",
                tool_name=self.name,
                error_type=type(e).__name__
            )


class ExecuteJQQueryTool(BaseTool):
    """Tool to execute JQ-style queries on properties data."""
    
    def __init__(self, agent_core):
        super().__init__(
            name="execute_jq_query",
            description="Execute JQ-style queries to filter and transform properties data",
            category=ToolCategory.DATA_PROCESSING
        )
        self.agent_core = agent_core
        self.cache_manager = agent_core.cache_manager
    
    async def execute(self, project_id: str, version_id: str, jq_query: str, **kwargs) -> ToolResult:
        """
        Execute JQ query on properties data.
        
        Args:
            project_id: Autodesk project ID
            version_id: Model version ID
            jq_query: JQ-style query string
            
        Returns:
            ToolResult with query results
        """
        try:
            # Get cached index
            cache_key = f"index_{project_id}_{version_id}"
            index_data = await self.cache_manager.get("model_properties", cache_key)
            
            if not index_data:
                return ToolResult.error(
                    error_message="Properties index not found. Please create index first.",
                    tool_name=self.name,
                    error_type="IndexNotFound"
                )
            
            # Execute simplified JQ-like query
            results = await self._execute_query(index_data, jq_query)
            
            if self.logger:
                self.logger.info("JQ query executed", extra={
                    "project_id": project_id,
                    "version_id": version_id,
                    "query": jq_query,
                    "results_count": len(results) if isinstance(results, list) else 1
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
                self.logger.error("Failed to execute JQ query", extra={
                    "project_id": project_id,
                    "version_id": version_id,
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
        # This is a simplified implementation
        # In production, you might want to use a proper JQ library
        
        if query == ".properties":
            return data.get("properties", [])
        elif query == ".categories":
            return data.get("categories", {})
        elif query == ".statistics":
            return data.get("statistics", {})
        elif query.startswith(".properties[] | select(.category =="):
            # Extract category from query
            category = query.split('"')[1]
            return [prop for prop in data.get("properties", []) if prop["category"] == category]
        elif query.startswith(".properties[] | select(.name =="):
            # Extract name from query
            name = query.split('"')[1]
            return [prop for prop in data.get("properties", []) if prop["name"] == name]
        else:
            # Default: return the whole data
            return data


class ModelPropertiesAgent(BaseAgent):
    """
    Model Properties Agent that makes real calls to Autodesk Platform Services.
    
    Provides functionality to create searchable indexes of model properties,
    query properties, and analyze building element data from design files.
    """
    
    def __init__(self, agent_core, agent_config: Dict[str, Any]):
        """Initialize Model Properties agent."""
        super().__init__(agent_core, agent_config)
        self.tool_registry = None
    
    async def initialize(self) -> None:
        """Initialize the agent and register tools."""
        if self._initialized:
            return
        
        # Create and register tools
        tools = [
            CreateIndexTool(self.agent_core),
            QueryIndexTool(self.agent_core),
            ListIndexPropertiesTool(self.agent_core),
            ExecuteJQQueryTool(self.agent_core)
        ]
        
        for tool in tools:
            await tool.initialize()
            self.register_tool(tool.name, tool)
        
        self.logger.info("Model Properties agent initialized", extra={
            "tools_count": len(tools),
            "tools": [tool.name for tool in tools]
        })
        
        await super().initialize()
    
    async def process_prompt(self, request: AgentRequest, context: ExecutionContext) -> AgentResponse:
        """Process user prompt for model properties operations."""
        
        prompt = request.prompt.lower()
        project_id = context.project_id or request.context.get("project_id")
        version_id = context.version_id or request.context.get("version_id")
        
        if not project_id or not version_id:
            return AgentResponse.error(
                error_message="Project ID and Version ID are required for model properties operations",
                error_code=ErrorCodes.MISSING_PARAMETER,
                agent_type=self.get_agent_type()
            )
        
        try:
            responses = []
            
            # Determine operation based on prompt
            if "create" in prompt and "index" in prompt:
                # Create properties index
                tool_result = await self.execute_tool(
                    "create_index",
                    project_id=project_id,
                    version_id=version_id
                )
                
                if tool_result.success:
                    output = tool_result.output
                    responses.extend([
                        f"✅ Properties index {'loaded from cache' if output.get('cached') else 'created successfully'}",
                        f"📊 Index contains {output.get('index_size', 0)} properties",
                        f"🏗️ Project: {project_id}",
                        f"📋 Version: {version_id}"
                    ])
                    
                    # Add category breakdown
                    if "index_data" in output:
                        categories = output["index_data"].get("categories", {})
                        if categories:
                            responses.append("\n📂 Property Categories:")
                            for category, props in categories.items():
                                responses.append(f"  • {category}: {len(set(props))} unique properties")
                else:
                    responses.append(f"❌ Failed to create index: {tool_result.error_message}")
            
            elif "query" in prompt or "search" in prompt or "find" in prompt:
                # Extract search terms from prompt
                search_terms = self._extract_search_terms(prompt)
                
                tool_result = await self.execute_tool(
                    "query_index",
                    project_id=project_id,
                    version_id=version_id,
                    query=search_terms
                )
                
                if tool_result.success:
                    output = tool_result.output
                    results = output.get("results", [])
                    
                    responses.extend([
                        f"🔍 Search results for '{search_terms}':",
                        f"📊 Found {len(results)} matching properties"
                    ])
                    
                    # Show top results
                    for i, result in enumerate(results[:10]):  # Limit to top 10
                        responses.append(
                            f"  {i+1}. {result['name']}: {result['value']} ({result['category']})"
                        )
                    
                    if len(results) > 10:
                        responses.append(f"  ... and {len(results) - 10} more results")
                else:
                    responses.append(f"❌ Search failed: {tool_result.error_message}")
            
            elif "list" in prompt or "show" in prompt:
                # List properties
                category = self._extract_category(prompt)
                
                tool_result = await self.execute_tool(
                    "list_index_properties",
                    project_id=project_id,
                    version_id=version_id,
                    category=category
                )
                
                if tool_result.success:
                    output = tool_result.output
                    categories = output.get("categories", {})
                    
                    if category:
                        responses.append(f"📂 Properties in category '{category}':")
                    else:
                        responses.append("📂 All property categories:")
                    
                    for cat_name, props in categories.items():
                        responses.append(f"\n  {cat_name} ({len(props)} properties):")
                        for prop in props[:5]:  # Show first 5
                            responses.append(f"    • {prop['name']} ({prop['type']})")
                        if len(props) > 5:
                            responses.append(f"    ... and {len(props) - 5} more")
                else:
                    responses.append(f"❌ Failed to list properties: {tool_result.error_message}")
            
            else:
                # General help
                responses.extend([
                    "🏗️ Model Properties Agent - Real Autodesk API Integration",
                    "",
                    "I can help you work with building model properties from Autodesk design files:",
                    "",
                    "📋 Available Operations:",
                    "• 'Create index' - Build searchable index of model properties",
                    "• 'Search for [term]' - Find properties matching your query",
                    "• 'List properties' - Show all available properties by category",
                    "• 'Show [category] properties' - List properties in specific category",
                    "",
                    "🔧 Real API Integration:",
                    "• Autodesk Platform Services for model data",
                    "• Model Derivative API for properties extraction",
                    "• Intelligent caching for performance",
                    "",
                    f"📋 Current Context: Project {project_id}, Version {version_id}",
                    "",
                    "💡 Try: 'Create index' to get started!"
                ])
            
            return AgentResponse(
                responses=responses,
                success=True,
                metadata={
                    "project_id": project_id,
                    "version_id": version_id,
                    "operation_detected": self._detect_operation(prompt),
                    "tools_available": list(self._tools.keys())
                }
            )
            
        except Exception as e:
            self.logger.error("Error processing model properties prompt", extra={
                "prompt": request.prompt,
                "project_id": project_id,
                "version_id": version_id,
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
        # Simple extraction - in production you might use NLP
        words = prompt.split()
        
        # Look for terms after "search", "find", "query"
        trigger_words = ["search", "find", "query", "for"]
        search_terms = []
        
        capture = False
        for word in words:
            if word.lower() in trigger_words:
                capture = True
                continue
            if capture and word.lower() not in ["properties", "property", "in", "the"]:
                search_terms.append(word)
        
        return " ".join(search_terms) if search_terms else prompt
    
    def _extract_category(self, prompt: str) -> Optional[str]:
        """Extract category from user prompt."""
        # Common categories in building models
        categories = [
            "structural", "mechanical", "electrical", "plumbing", 
            "architectural", "general", "materials", "dimensions"
        ]
        
        prompt_lower = prompt.lower()
        for category in categories:
            if category in prompt_lower:
                return category.title()
        
        return None
    
    def _detect_operation(self, prompt: str) -> str:
        """Detect the intended operation from prompt."""
        prompt_lower = prompt.lower()
        
        if "create" in prompt_lower and "index" in prompt_lower:
            return "create_index"
        elif any(word in prompt_lower for word in ["search", "find", "query"]):
            return "search"
        elif "list" in prompt_lower or "show" in prompt_lower:
            return "list"
        else:
            return "help"
    
    def get_capabilities(self) -> AgentCapabilities:
        """Get agent capabilities."""
        return AgentCapabilities(
            agent_type=self.get_agent_type(),
            name="Model Properties Agent",
            description="Analyzes building model properties from Autodesk design files using real API integration",
            version="1.0.0",
            tools=["create_index", "query_index", "list_index_properties", "execute_jq_query"],
            supported_formats=["json", "text"],
            max_prompt_length=2000,
            requires_authentication=True,
            requires_project_context=True,
            requires_internet=True,
            typical_response_time_ms=2000
        )
    
    def get_agent_type(self) -> str:
        """Return agent type."""
        return AgentType.MODEL_PROPERTIES.value