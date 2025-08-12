"""
Model Properties Agent for the AgentCore framework.

This agent provides functionality for working with Autodesk Construction Cloud
Model Properties, including index creation, property listing, querying, and
JSON processing.
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


# System prompts for the Model Properties agent
SYSTEM_PROMPTS = """You are an AI assistant providing data analytics for designs hosted in Autodesk Construction Cloud. You use the Model Properties Query Language and API to retrieve relevant information from individual designs.

When asked about a (Revit) category of elements, look for the property called `_RC`.

When asked about a (Revit) family type of elements, look for the property called `_RFT`.

When asked about a name of an element, look for the property called `__name__`.

Whenever you are referring to one or more specific elements, include an HTML link in your response with all the element SVF2 IDs listed in the `data-dbids` attribute.

Example: `<a href="#" data-dbids="1,2,3,4">Show in Viewer</a>`"""

MPQL_GUIDE = """# Model Properties Query Language Guide

The **Model Properties Query Language (MPQL)** is a JSON-based query syntax for filtering and retrieving design element properties from a **Model Properties index**. The index is generated for design files hosted in **Autodesk Construction Cloud** using the **ACC Model Properties API** (part of **Autodesk Platform Services**). This guide explains how to construct valid MPQL queries.

## Query Structure

A valid MPQL query consists of:

- A `query` object defining custom filter conditions; only elements matching these filters will be returned
- An optional `columns` object specifying which properties to retrieve

### Example Query

```json
{{
  "query": {{
    "$eq": ["s.props.p5678efgh", "'Walls'"]
  }},
  "columns": {{
    "s.svf2Id": true,
    "Name": "s.props.p1234abcd",
    "Width": "s.props.p2233ffee"
  }}
}}
```

## Property Paths

Properties must always be specified using **property paths** such as `s.props.<key>` where the key is a hexadecimal value prefixed with `p`, for example, `p5678efgh`. The list of all available properties and their keys can be retrieved from the Model Properties index.

There are also several **metadata properties** such as:

- `s.svf2Id` - unique ID of the design element
- `s.views` - number of views in which the element is visible

## Conditions

MPQL supports various operators to filter elements based on their properties:

| Operator   | Description                           | Example  |
|------------|---------------------------------------|----------|
| `$eq`      | Exact match                           | `{{ "$eq": ["s.props.p1234abcd", "'Concrete'"] }}` |
| `$ne`      | Not equal                             | `{{ "$ne": ["s.props.p1234abcd", "'Steel'"] }}` |
| `$gt`      | Greater than                          | `{{ "$gt": ["s.props.p2233ffee", 100] }}` |
| `$ge`      | Greater than or equal                 | `{{ "$ge": ["s.props.p2233ffee", 50] }}` |
| `$lt`      | Less than                             | `{{ "$lt": ["s.props.p2233ffee", 500] }}` |
| `$le`      | Less than or equal                    | `{{ "$le": ["s.props.p2233ffee", 200] }}` |
| `$in`      | Match any value in a list             | `{{ "$in": {{ "s.props.p3344ccdd": ["'Steel'", "'Concrete'"] }}}}` |
| `$not`     | Negate a condition                    | `{{ "$not": {{ "$eq": ["s.props.p1234abcd", "'Wood'"] }} }}` |
| `$and`     | Combine multiple conditions (AND)     | `{{ "$and": [{{ "$eq": ["s.props.p5678efgh", "'Doors'"] }}, {{ "$gt": ["s.props.p2233ffee", 200] }}] }}` |
| `$or`      | Combine multiple conditions (OR)      | `{{ "$or": [{{ "$eq": ["s.props.p1234abcd", "'Steel'"] }}, {{ "$eq": ["s.props.p1234abcd", "'Concrete'"] }}] }}` |
| `$like`    | Pattern matching (wildcards `%`)      | `{{ "$like": ["s.props.p5678efgh", "'%Wall%'"] }}` |
| `$between` | Match value within a range            | `{{ "$between": {{ "s.props.p2233ffee": [100, 200] }} }}` |
| `$isnull`  | Match a value that is null            | `{{ "$isnull": "s.props.p1234abcd" }}` |
| `$notnull` | Match a value that is not null        | `{{ "$notnull": "s.props.p1234abcd" }}` |

## Expressions

MPQL supports the following expressions in both filter queries and column selections:

| Expression | Description                               | Example |
|------------|-------------------------------------------|---------|
| `$neg`     | Negates the value of an expression        | `{{ "$neg": "s.props.p1234abcd" }}` |
| `$add`     | Adds two or more expressions              | `{{ "$add": ["s.props.p1234abcd", 100] }}` |
| `$sub`     | Subtracts two or more expressions         | `{{ "$sub": [100, "s.props.p1234abcd"] }}` |
| `$mul`     | Multiplies two or more expressions        | `{{ "$mul": ["s.props.p1234abcd", 2] }}` |
| `$div`     | Divides two or more expressions           | `{{ "$div": ["s.props.p1234abcd", 2] }}` |
| `$mod`     | Module-divides two or more expressions    | `{{ "$mod": ["s.props.p1234abcd", 10] }}` |
| `$nullif`  | Returns 2nd expression if 1st one is null | `{{ "$nullif": ["s.props.p1234abcd", 0] }}` |
| `$count`   | Returns count of values in expression     | `{{ "$count": "s.props.p1234abcd" }}` |
| `$max`     | Returns maximum of values in expression   | `{{ "$max": "s.props.p1234abcd" }}` |
| `$min`     | Returns minimum of values in expression   | `{{ "$min": "s.props.p1234abcd" }}` |

## Column Selection

The `columns` object specifies which properties to retrieve.

### Column Selection Syntax

- **Key-value pairs** where:  
  - The **key** is an alias (or property key).  
  - The **value** is `"s.props.<property_key>"` or `true` (for all properties).

### Examples

#### ✅ Return only specific properties

```json
{{
  "query": {{ "$eq": ["s.props.p5678efgh", "Walls"] }},
  "columns": {{
    "s.svf2Id": true,
    "Name": "s.props.p1234abcd",
    "Height": "s.props.p2233ffee"
  }}
}}
```

#### ✅ Return all properties (omit `columns` field)

```json
{{
  "query": {{ "$eq": ["s.props.p5678efgh", "Walls"] }}
}}
```

#### ✅ Return property values without renaming

```json
{{
  "query": {{ "$eq": ["s.props.p5678efgh", "Doors"] }},
  "columns": {{
    "s.props.p1234abcd": true,
    "s.props.p3344ccdd": true
  }}
}}
```

#### ✅ Return number of elements matching a filter

```json
{{
  "query": {{ "$eq": ["s.props.p5678efgh", "Doors"] }},
  "columns": {{
    "Count": {{ "$count": "s.props.p5678efgh" }}
  }}
}}
```

#### ✅ Return the smallest and largest value of a property

```json
{{
  "query": {{ "$eq": ["s.props.p5678efgh", "Walls"] }},
  "columns": {{
    "Minimum": {{ "$min": "s.props.p1234abcd" }},
    "Maximum": {{ "$max": "s.props.p1234abcd" }}
  }}
}}
```

## Example Queries

### Find all walls and return only their names

```json
{{
  "query": {{
    "$like": ["s.props.p5678efgh", "'%Wall%'"]
  }},
  "columns": {{
    "Name": "s.props.p1234abcd"
  }}
}}
```  

### Find doors taller than 200 and return name, height, and material

```json
{{
  "query": {{
    "$and": [
      {{ "$eq": ["s.props.p5678efgh", "Doors"] }},
      {{ "$gt": ["s.props.p2233ffee", 200] }}
    ]
  }},
  "columns": {{
    "Name": "s.props.p1234abcd",
    "Height": "s.props.p2233ffee",
    "Material": "s.props.p9988aabb"
  }}
}}
```  

### Find elements made of concrete or steel

```json
{{
  "query": {{
    "$in": ["s.props.p4455ccdd", ["Concrete", "Steel"]]
  }}
}}
```

### Find visible beams heavier than 100kg

```json
{{
  "query": {{
    "$and": [
      {{ "$eq": ["s.props.p5678efgh", "Beams"] }},
      {{ "$eq": ["s.props.p1122aabb", true] }},
      {{ "$gt": ["s.props.p3344ccdd", 100] }}
    ]
  }},
  "columns": {{
    "Name": "s.props.p1234abcd",
    "Weight": "s.props.p3344ccdd"
  }}
}}
```

## Limitations

- When calculating aggregates such as the maximum value of a property, **metadata properties** such as `s.svf2Id` cannot be used in `columns`.
- When using pattern matching, always wrap the string containing wildcards with single-quotes, for example, `{{ "$like": ["s.props.p5678efgh", "'%Wall%'"] }}`.

## Resources

- https://aps.autodesk.com/en/docs/acc/v1/tutorials/model-properties/query-ref/"""


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


class ModelPropertiesAgent(BaseAgent):
    """
    Agent for working with Autodesk Construction Cloud Model Properties.
    
    This agent provides functionality for:
    - Creating Model Properties indexes
    - Listing available properties
    - Querying indexes with MPQL
    - Processing JSON data with jq
    """
    
    def __init__(self, agent_core: 'AgentCore', tools: Optional[List[BaseTool]] = None):
        """
        Initialize the Model Properties agent.
        
        Args:
            agent_core: The AgentCore instance providing common services
            tools: List of tools available to this agent (optional, will use registry)
        """
        super().__init__(agent_core, tools)
        self._llm: Optional[BaseChatModel] = None
        self._langgraph_agent = None
        self._logs_dir: Optional[str] = None
    
    def get_agent_type(self) -> str:
        """Return the agent type identifier."""
        return "model_properties"
    
    async def initialize(self) -> None:
        """Initialize the agent with LLM and LangGraph setup."""
        await super().initialize()
        
        # Initialize LLM
        self._llm = ChatBedrock(
            model_id="anthropic.claude-3-5-sonnet-20241022-v2:0",
            model_kwargs={
                "temperature": 0.0,
                "max_tokens": 4096
            }
        )
        
        self.agent_core.logger.info(
            "ModelPropertiesAgent initialized with LLM",
            agent_type=self.get_agent_type(),
            model_id="anthropic.claude-3-5-sonnet-20241022-v2:0"
        )
    
    def _create_langchain_agent(self, auth_context: AuthContext, cache_dir: str):
        """Create a LangChain agent with wrapped tools."""
        # Wrap AgentCore tools for LangChain compatibility
        langchain_tools = []
        for tool in self.tools:
            wrapped_tool = LangChainToolWrapper(tool, auth_context, cache_dir)
            langchain_tools.append(wrapped_tool)
        
        # Create system prompts
        version_id = auth_context.version_id or "the current design"
        system_prompt = f"""{SYSTEM_PROMPTS}

{MPQL_GUIDE}

Unless specified otherwise, you are working with design ID "{version_id}"

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
        if not auth_context.version_id:
            # Use a default cache directory if no version_id
            cache_dir = os.path.join(
                self.agent_core.config.cache_directory,
                "model_properties",
                "default"
            )
        else:
            # Create cache directory based on version_id
            cache_dir = os.path.join(
                self.agent_core.config.cache_directory,
                "model_properties",
                auth_context.version_id.replace(":", "_").replace("/", "_")
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
                raise ValueError("Authentication context is required for Model Properties agent")
            
            auth_context = request.authentication
            
            # Get cache directory
            cache_dir = self._get_cache_dir(auth_context)
            logs_path = self._get_logs_path(cache_dir)
            
            # Log the user prompt
            self._log_interaction(logs_path, f"User: {request.prompt}")
            
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
                thread_id=thread_id
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
                responses_count=len(responses)
            )
            
            return AgentResponse(
                responses=responses,
                metadata={
                    "cache_dir": cache_dir,
                    "thread_id": thread_id,
                    "tools_used": len(self.tools)
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
        
        # Add Model Properties specific status
        base_status.update({
            "llm_initialized": self._llm is not None,
            "llm_model_id": "anthropic.claude-3-5-sonnet-20241022-v2:0" if self._llm else None,
            "supports_mpql": True,
            "supports_caching": True
        })
        
        return base_status