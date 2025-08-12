"""
AEC Data Model Agent for the AgentCore framework.

This agent provides functionality for working with Autodesk AEC Data Model API,
including GraphQL queries, element categories, property definitions search,
and JSON processing with OpenSearch vector store integration.
"""

import os
import time
from typing import List, Dict, Any, Optional
from datetime import datetime

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import BaseTool as LangChainBaseTool
from langchain_aws import ChatBedrock
from langchain.agents import AgentExecutor, create_react_agent as create_langchain_react_agent
from langchain.memory import ConversationBufferMemory

from ..base_agent import BaseAgent, BaseTool
from ..models import AgentRequest, AgentResponse, ToolResult
from ..auth import AuthContext
from ..vector_store import OpenSearchVectorStore
from ..tools.aec_data_model import (
    ExecuteGraphQLQueryTool,
    GetElementCategoriesTool,
    ExecuteJQQueryTool,
    FindRelatedPropertyDefinitionsTool,
    PropertyDefinitionsManager
)


# System prompts for the AEC Data Model agent
SYSTEM_PROMPTS = """You are an AI assistant providing data analytics for designs hosted in Autodesk Construction Cloud. You use the AEC Data Model GraphQL API to retrieve relevant information from individual designs.

When asked about a (Revit) category of elements, look for the property called `Revit Category Type Id`.

When asked about a (Revit) family type of elements, look for the property called `Revit Family Type`.

When asked about a name of an element, look for the property called `Name`.

Whenever you are referring to one or more specific elements, include an HTML link in your response with all the element external IDs listed in the `data-dbids` attribute.

Example: `<a href="#" data-dbids="ext1,ext2,ext3,ext4">Show in Viewer</a>`

You have access to property definitions through semantic search. Use the find_related_property_definitions tool to discover relevant properties before constructing GraphQL queries."""

AECDM_GRAPHQL_SCHEMA = """# AEC Data Model GraphQL Schema Reference

The AEC Data Model GraphQL API provides access to design element data and property definitions. Here are the key types and queries:

## Key Types

### ElementGroup
- `id: ID!` - Unique identifier for the element group
- `propertyDefinitions(pagination: PaginationInput)` - Property definitions for this group
- `elements(pagination: PaginationInput)` - Elements in this group

### PropertyDefinition
- `id: ID!` - Unique identifier
- `name: String!` - Property name
- `description: String` - Property description
- `units: Unit` - Property units

### Element
- `id: ID!` - Unique identifier
- `externalId: String` - External element ID
- `properties(filter: PropertyFilter)` - Element properties

### Property
- `definition: PropertyDefinition!` - Property definition
- `value: JSON` - Property value

## Key Queries

### Get Property Definitions
```graphql
query GetPropertyDefinitions($elementGroupId: ID!, $cursor: String) {
  elementGroupAtTip(elementGroupId: $elementGroupId) {
    propertyDefinitions(pagination: {cursor: $cursor}) {
      pagination { cursor }
      results {
        id
        name
        description
        units { id name }
      }
    }
  }
}
```

### Get Elements by Group
```graphql
query GetElements($elementGroupId: ID!, $cursor: String) {
  elementsByElementGroup(
    elementGroupId: $elementGroupId
    pagination: {cursor: $cursor}
  ) {
    pagination { cursor }
    results {
      id
      externalId
      properties {
        results {
          definition { id name }
          value
        }
      }
    }
  }
}
```

### Get Elements with Property Filter
```graphql
query GetElementsWithFilter($elementGroupId: ID!, $propertyNames: [String!]) {
  elementsByElementGroup(elementGroupId: $elementGroupId) {
    results {
      id
      externalId
      properties(filter: {names: $propertyNames}) {
        results {
          definition { id name }
          value
        }
      }
    }
  }
}
```

## Pagination
Most queries support pagination using cursor-based pagination:
- Use `pagination: {cursor: $cursor}` in queries
- Check `pagination.cursor` in responses for next page
- Continue until `cursor` is null

## Property Filtering
Filter properties by names:
```graphql
properties(filter: {names: ["Property Name 1", "Property Name 2"]})
```

## Best Practices
1. Always use pagination for large datasets
2. Filter properties to only what you need
3. Use property definitions to understand available properties
4. Include external IDs when referring to specific elements"""


class LangChainToolWrapper(LangChainBaseTool):
    """Wrapper to adapt AgentCore BaseTool to LangChain BaseTool interface."""
    
    name: str
    description: str
    
    def __init__(self, agent_tool: BaseTool, auth_context: AuthContext, cache_dir: str):
        """
        Initialize the wrapper.
        
        Args:
            agent_tool: The AgentCore BaseTool to wrap
            auth_context: Authentication context for tool execution
            cache_dir: Cache directory for tool operations
        """
        # Initialize LangChain tool first
        super().__init__(
            name=agent_tool.name,
            description=agent_tool.description
        )
        
        # Store references using object.__setattr__ to bypass Pydantic validation
        object.__setattr__(self, '_agent_tool', agent_tool)
        object.__setattr__(self, '_auth_context', auth_context)
        object.__setattr__(self, '_cache_dir', cache_dir)
    
    def _run(self, **kwargs) -> Any:
        """Synchronous execution (not used in async context)."""
        raise NotImplementedError("Use async version")
    
    async def _arun(self, **kwargs) -> Any:
        """Asynchronous execution."""
        # Add context to kwargs
        kwargs['auth_context'] = self._auth_context
        kwargs['cache_dir'] = self._cache_dir
        
        # Execute the tool
        result = await self._agent_tool.execute(**kwargs)
        
        if result.success:
            return result.result
        else:
            raise Exception(result.error)


class AECDataModelAgent(BaseAgent):
    """
    Agent for working with Autodesk AEC Data Model API.
    
    This agent provides functionality for:
    - Executing GraphQL queries against AEC Data Model API
    - Getting element categories
    - Finding related property definitions using semantic search
    - Processing JSON data with jq
    """
    
    def __init__(self, agent_core: 'AgentCore', tools: Optional[List[BaseTool]] = None):
        """
        Initialize the AEC Data Model agent.
        
        Args:
            agent_core: The AgentCore instance providing common services
            tools: List of tools available to this agent (optional, will use registry)
        """
        super().__init__(agent_core, tools)
        self._llm: Optional[BaseChatModel] = None
        self._vector_store: Optional[OpenSearchVectorStore] = None
        self._property_manager: Optional[PropertyDefinitionsManager] = None
        self._logs_dir: Optional[str] = None
    
    def get_agent_type(self) -> str:
        """Return the agent type identifier."""
        return "aec_data_model"
    
    async def initialize(self) -> None:
        """Initialize the agent with LLM, vector store, and tools setup."""
        await super().initialize()
        
        # Initialize LLM
        self._llm = ChatBedrock(
            model_id="anthropic.claude-3-5-sonnet-20241022-v2:0",
            model_kwargs={
                "temperature": 0.0,
                "max_tokens": 4096
            }
        )
        
        # Initialize OpenSearch vector store
        self._vector_store = OpenSearchVectorStore(
            opensearch_endpoint=self.agent_core.config.opensearch_endpoint,
            index_name="aec-property-definitions",
            embeddings_model_id="amazon.titan-embed-text-v1",
            aws_region=self.agent_core.config.aws_region
        )
        await self._vector_store.initialize()
        
        # Initialize property definitions manager
        self._property_manager = PropertyDefinitionsManager(self._vector_store)
        
        # Create AEC Data Model specific tools if not provided
        if not self.tools:
            self.tools = [
                ExecuteGraphQLQueryTool(),
                GetElementCategoriesTool(),
                ExecuteJQQueryTool(),
                FindRelatedPropertyDefinitionsTool(self._vector_store)
            ]
            
            # Update tool registry for quick lookup
            self._tool_registry = {tool.name: tool for tool in self.tools}
        
        self.agent_core.logger.info(
            "AECDataModelAgent initialized with LLM and OpenSearch",
            agent_type=self.get_agent_type(),
            model_id="anthropic.claude-3-5-sonnet-20241022-v2:0",
            vector_store_index="aec-property-definitions"
        )
    
    def _create_langchain_agent(self, auth_context: AuthContext, cache_dir: str):
        """Create a LangChain agent with wrapped tools."""
        # Wrap AgentCore tools for LangChain compatibility
        langchain_tools = []
        for tool in self.tools:
            wrapped_tool = LangChainToolWrapper(tool, auth_context, cache_dir)
            langchain_tools.append(wrapped_tool)
        
        # Create system prompts
        element_group_id = auth_context.element_group_id or "the current element group"
        system_prompt = f"""{SYSTEM_PROMPTS}

{AECDM_GRAPHQL_SCHEMA}

Unless specified otherwise, you are working with element group ID "{element_group_id}"

You have access to the following tools:
{{tools}}

Use the following format:

Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{{tool_names}}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: the final answer to the original input question"""
        
        # Create prompt template
        from langchain.prompts import PromptTemplate
        
        # Get tool names and descriptions for the prompt
        tool_names = [tool.name for tool in langchain_tools]
        tools_desc = "\n".join([f"{tool.name}: {tool.description}" for tool in langchain_tools])
        
        prompt_template = PromptTemplate(
            input_variables=["input", "agent_scratchpad"],
            template=system_prompt + "\n\nQuestion: {input}\n{agent_scratchpad}",
            partial_variables={
                "tools": tools_desc,
                "tool_names": ", ".join(tool_names)
            }
        )
        
        # Create LangChain agent
        agent = create_langchain_react_agent(
            self._llm, 
            langchain_tools, 
            prompt_template
        )
        
        # Create memory for conversation
        memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)
        
        # Create agent executor
        return AgentExecutor(
            agent=agent,
            tools=langchain_tools,
            memory=memory,
            verbose=True,
            handle_parsing_errors=True,
            max_iterations=10
        )
    
    def _get_cache_dir(self, auth_context: AuthContext) -> str:
        """Get cache directory for the current context."""
        if not auth_context.element_group_id:
            # Use a default cache directory if no element_group_id
            cache_dir = os.path.join(
                self.agent_core.config.cache_directory,
                "aec_data_model",
                "default"
            )
        else:
            # Create cache directory based on element_group_id
            cache_dir = os.path.join(
                self.agent_core.config.cache_directory,
                "aec_data_model",
                auth_context.element_group_id.replace(":", "_").replace("/", "_")
            )
        
        # Ensure directory exists
        os.makedirs(cache_dir, exist_ok=True)
        return cache_dir
    
    def _get_logs_path(self, cache_dir: str) -> str:
        """Get logs file path for the current context."""
        return os.path.join(cache_dir, "logs.txt")
    
    def _log_interaction(self, logs_path: str, message: str) -> None:
        """Log interaction to file."""
        try:
            with open(logs_path, "a", encoding="utf-8") as log_file:
                timestamp = datetime.now().isoformat()
                log_file.write(f"[{timestamp}] {message}\n\n")
        except Exception as e:
            self.agent_core.logger.warning(
                f"Failed to write to log file: {str(e)}",
                agent_type=self.get_agent_type(),
                logs_path=logs_path
            )
    
    async def _ensure_property_definitions_loaded(
        self, 
        auth_context: AuthContext, 
        cache_dir: str
    ) -> None:
        """Ensure property definitions are loaded in the vector store."""
        if not auth_context.element_group_id:
            self.agent_core.logger.warning(
                "No element group ID provided, skipping property definitions loading",
                agent_type=self.get_agent_type()
            )
            return
        
        try:
            await self._property_manager.ensure_vector_store_populated(
                auth_context.element_group_id,
                auth_context.access_token,
                cache_dir
            )
            
            self.agent_core.logger.debug(
                "Property definitions loaded in vector store",
                agent_type=self.get_agent_type(),
                element_group_id=auth_context.element_group_id
            )
            
        except Exception as e:
            self.agent_core.logger.warning(
                f"Failed to load property definitions: {str(e)}",
                agent_type=self.get_agent_type(),
                element_group_id=auth_context.element_group_id
            )
    
    async def process_prompt(self, request: AgentRequest) -> AgentResponse:
        """
        Process a user prompt and return a response.
        
        Args:
            request: The agent request containing prompt and context
            
        Returns:
            AgentResponse: The processed response
        """
        start_time = time.time()
        
        try:
            # Validate that we have authentication
            if not request.authentication:
                raise ValueError("Authentication context is required for AEC Data Model agent")
            
            auth_context = request.authentication
            
            # Get cache directory
            cache_dir = self._get_cache_dir(auth_context)
            logs_path = self._get_logs_path(cache_dir)
            
            # Log the user prompt
            self._log_interaction(logs_path, f"User: {request.prompt}")
            
            # Ensure property definitions are loaded in vector store
            await self._ensure_property_definitions_loaded(auth_context, cache_dir)
            
            # Create LangChain agent for this request
            langchain_agent = self._create_langchain_agent(auth_context, cache_dir)
            
            # Configure agent with thread ID based on cache directory
            thread_id = os.path.basename(cache_dir)
            
            # Process the prompt
            responses = []
            
            self.agent_core.logger.debug(
                f"Processing prompt with LangChain agent",
                agent_type=self.get_agent_type(),
                prompt_length=len(request.prompt),
                thread_id=thread_id,
                element_group_id=auth_context.element_group_id
            )
            
            # Execute the agent
            try:
                result = await langchain_agent.ainvoke({"input": request.prompt})
                
                # Log the interaction
                self._log_interaction(logs_path, f"Agent result: {result}")
                
                # Extract the output
                if isinstance(result, dict) and "output" in result:
                    responses.append(result["output"])
                elif isinstance(result, str):
                    responses.append(result)
                else:
                    responses.append(str(result))
                    
            except Exception as agent_error:
                error_msg = f"Agent execution error: {str(agent_error)}"
                self._log_interaction(logs_path, error_msg)
                responses.append(error_msg)
            
            execution_time = time.time() - start_time
            
            self.agent_core.logger.info(
                f"Prompt processed successfully",
                agent_type=self.get_agent_type(),
                execution_time=execution_time,
                responses_count=len(responses),
                element_group_id=auth_context.element_group_id
            )
            
            return AgentResponse(
                responses=responses,
                metadata={
                    "cache_dir": cache_dir,
                    "thread_id": thread_id,
                    "element_group_id": auth_context.element_group_id,
                    "tools_used": len(self.tools),
                    "vector_store_index": "aec-property-definitions"
                },
                execution_time=execution_time,
                agent_type=self.get_agent_type(),
                request_id=request.request_id,
                success=True
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            
            self.agent_core.logger.error(
                f"Error processing prompt",
                agent_type=self.get_agent_type(),
                execution_time=execution_time,
                error=str(e)
            )
            
            return AgentResponse(
                responses=[f"Error: {str(e)}"],
                metadata={"error": str(e)},
                execution_time=execution_time,
                agent_type=self.get_agent_type(),
                request_id=request.request_id,
                success=False
            )
    
    async def get_status(self) -> Dict[str, Any]:
        """Get comprehensive agent status."""
        base_status = await super().get_status()
        
        # Add AEC Data Model specific status
        vector_store_health = None
        if self._vector_store:
            try:
                vector_store_health = await self._vector_store.health_check()
            except Exception as e:
                vector_store_health = {"error": str(e)}
        
        base_status.update({
            "llm_initialized": self._llm is not None,
            "llm_model_id": "anthropic.claude-3-5-sonnet-20241022-v2:0" if self._llm else None,
            "vector_store_initialized": self._vector_store is not None,
            "vector_store_health": vector_store_health,
            "property_manager_initialized": self._property_manager is not None,
            "supports_graphql": True,
            "supports_semantic_search": True,
            "supports_caching": True
        })
        
        return base_status
    
    async def shutdown(self) -> None:
        """Shutdown the agent and cleanup resources."""
        await super().shutdown()
        
        # No specific cleanup needed for vector store or property manager
        # as they don't maintain persistent connections
        
        self.agent_core.logger.info(
            f"AECDataModelAgent shutdown completed",
            agent_type=self.get_agent_type()
        )