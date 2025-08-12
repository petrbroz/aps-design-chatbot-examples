"""
Model Derivatives Agent for the AgentCore framework.

This agent provides functionality for working with Autodesk Platform Services
Model Derivatives, including SQLite database setup, management, and querying
for design element properties.
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


# System prompts for the Model Derivatives agent
SYSTEM_PROMPTS = """You are an AI assistant providing data analytics for design properties stored in sqlite database.

Dimension values stored in the database use standard units such as 'm', 'm^2', 'm^3', or '°'.

Whenever you are referring to one or more specific elements, include an HTML link in your response with all the element IDs listed in the `data-dbids` attribute.

Example: `<a href="#" data-dbids="1,2,3,4">Show in Viewer</a>`"""


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


class ModelDerivativesAgent(BaseAgent):
    """
    Agent for working with Autodesk Platform Services Model Derivatives.
    
    This agent provides functionality for:
    - Setting up SQLite databases with model properties
    - Executing SQL queries on design element data
    - Getting database schema information
    - Retrieving sample data for analysis
    """
    
    def __init__(self, agent_core: 'AgentCore', tools: Optional[List[BaseTool]] = None):
        """
        Initialize the Model Derivatives agent.
        
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
        return "model_derivatives"
    
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
            "ModelDerivativesAgent initialized with LLM",
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
        urn = auth_context.urn or "the current design"
        system_prompt = f"""{SYSTEM_PROMPTS}

Unless specified otherwise, you are working with design URN "{urn}"

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
        if not auth_context.urn:
            # Use a default cache directory if no URN
            cache_dir = os.path.join(
                self.agent_core.config.cache_directory,
                "model_derivatives",
                "default"
            )
        else:
            # Create cache directory based on URN
            cache_dir = os.path.join(
                self.agent_core.config.cache_directory,
                "model_derivatives",
                auth_context.urn.replace(":", "_").replace("/", "_")
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
                raise ValueError("Authentication context is required for Model Derivatives agent")
            
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
                    "tools_used": len(self.tools),
                    "urn": auth_context.urn
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
        
        # Add Model Derivatives specific status
        base_status.update({
            "llm_initialized": self._llm is not None,
            "llm_model_id": "anthropic.claude-3-5-sonnet-20241022-v2:0" if self._llm else None,
            "supports_sqlite": True,
            "supports_caching": True,
            "database_tools": [
                "setup_database",
                "sql_query", 
                "get_table_info",
                "get_sample_data"
            ]
        })
        
        return base_status