"""
Base agent interface for the AgentCore framework.
"""

import asyncio
import time
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime

from .models import AgentRequest, AgentResponse, ErrorResponse, ErrorCode, ToolResult, AgentMetrics
from .auth import AuthContext


class BaseTool(ABC):
    """Base class for agent tools."""
    
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
    
    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """Execute the tool with given parameters."""
        pass
    
    def get_schema(self) -> Dict[str, Any]:
        """Get the tool's parameter schema."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self._get_parameters_schema()
        }
    
    @abstractmethod
    def _get_parameters_schema(self) -> Dict[str, Any]:
        """Get the parameters schema for this tool."""
        pass


class BaseAgent(ABC):
    """
    Abstract base class for all agents in the AgentCore framework.
    
    This class provides the common interface and functionality that all agents
    must implement, including request processing, tool management, and metrics tracking.
    """
    
    def __init__(self, agent_core: 'AgentCore', tools: Optional[List[BaseTool]] = None):
        """
        Initialize the base agent.
        
        Args:
            agent_core: The AgentCore instance providing common services
            tools: List of tools available to this agent (deprecated - use tool registry instead)
        """
        self.agent_core = agent_core
        self.tools = tools or []
        self.metrics = AgentMetrics(agent_type=self.get_agent_type())
        self._initialized = False
        self._start_time = datetime.utcnow()
        
        # Tool registry for quick lookup (legacy support)
        self._tool_registry: Dict[str, BaseTool] = {
            tool.name: tool for tool in self.tools
        }
    
    async def initialize(self) -> None:
        """Initialize the agent. Override in subclasses for custom initialization."""
        if self._initialized:
            return
        
        self.agent_core.logger.info(
            f"Initializing {self.get_agent_type()} agent",
            agent_type=self.get_agent_type(),
            tools_count=len(self.tools)
        )
        
        # Get tools from registry if available
        if self.agent_core.tool_registry and hasattr(self.agent_core.tool_registry, 'get_tools_for_agent'):
            try:
                registry_tools = self.agent_core.tool_registry.get_tools_for_agent(self.get_agent_type())
                if isinstance(registry_tools, list):
                    # Merge with any directly provided tools
                    all_tools = list(self.tools) + registry_tools
                    self.tools = all_tools
                    
                    # Update tool registry for quick lookup
                    self._tool_registry = {tool.name: tool for tool in self.tools}
            except Exception as e:
                # Log error but continue with existing tools
                self.agent_core.logger.warning(
                    f"Failed to get tools from registry for {self.get_agent_type()}",
                    error=str(e)
                )
        
        # Initialize tools if they have initialization methods
        for tool in self.tools:
            if hasattr(tool, 'initialize'):
                await tool.initialize()
        
        self._initialized = True
        self.agent_core.logger.info(
            f"{self.get_agent_type()} agent initialized successfully",
            agent_type=self.get_agent_type()
        )
    
    async def shutdown(self) -> None:
        """Shutdown the agent. Override in subclasses for custom cleanup."""
        if not self._initialized:
            return
        
        self.agent_core.logger.info(
            f"Shutting down {self.get_agent_type()} agent",
            agent_type=self.get_agent_type()
        )
        
        # Shutdown tools if they have shutdown methods
        for tool in self.tools:
            if hasattr(tool, 'shutdown'):
                await tool.shutdown()
        
        self._initialized = False
        self.agent_core.logger.info(
            f"{self.get_agent_type()} agent shutdown completed",
            agent_type=self.get_agent_type()
        )
    
    @abstractmethod
    async def process_prompt(self, request: AgentRequest) -> AgentResponse:
        """
        Process a user prompt and return a response.
        
        This is the main entry point for agent functionality. Subclasses must
        implement this method to handle their specific processing logic.
        
        Args:
            request: The agent request containing prompt and context
            
        Returns:
            AgentResponse: The processed response
            
        Raises:
            Various exceptions that will be handled by the error handling system
        """
        pass
    
    @abstractmethod
    def get_agent_type(self) -> str:
        """
        Return the agent type identifier.
        
        This should be a unique string that identifies the agent type,
        such as 'model_properties', 'aec_data_model', or 'model_derivatives'.
        
        Returns:
            str: The agent type identifier
        """
        pass
    
    async def execute_tool(self, tool_name: str, **kwargs) -> ToolResult:
        """
        Execute a specific tool by name.
        
        Args:
            tool_name: Name of the tool to execute
            **kwargs: Parameters to pass to the tool
            
        Returns:
            ToolResult: The result of tool execution
            
        Raises:
            ValueError: If tool is not found
        """
        if tool_name not in self._tool_registry:
            raise ValueError(f"Tool '{tool_name}' not found in agent '{self.get_agent_type()}'")
        
        tool = self._tool_registry[tool_name]
        start_time = time.time()
        
        try:
            self.agent_core.logger.debug(
                f"Executing tool {tool_name}",
                agent_type=self.get_agent_type(),
                tool_name=tool_name,
                parameters=kwargs
            )
            
            result = await tool.execute(**kwargs)
            execution_time = time.time() - start_time
            result.execution_time = execution_time
            
            self.agent_core.logger.debug(
                f"Tool {tool_name} executed successfully",
                agent_type=self.get_agent_type(),
                tool_name=tool_name,
                execution_time=execution_time,
                success=result.success
            )
            
            return result
            
        except Exception as e:
            execution_time = time.time() - start_time
            self.agent_core.logger.error(
                f"Tool {tool_name} execution failed",
                agent_type=self.get_agent_type(),
                tool_name=tool_name,
                execution_time=execution_time,
                error=str(e)
            )
            
            return ToolResult(
                tool_name=tool_name,
                success=False,
                error=str(e),
                execution_time=execution_time
            )
    
    def get_available_tools(self) -> List[Dict[str, Any]]:
        """
        Get list of available tools with their schemas.
        
        Returns:
            List of tool schemas
        """
        return [tool.get_schema() for tool in self.tools]
    
    def has_tool(self, tool_name: str) -> bool:
        """
        Check if agent has a specific tool.
        
        Args:
            tool_name: Name of the tool to check
            
        Returns:
            bool: True if tool exists, False otherwise
        """
        return tool_name in self._tool_registry
    
    async def validate_request(self, request: AgentRequest) -> None:
        """
        Validate an incoming request.
        
        Args:
            request: The request to validate
            
        Raises:
            ValueError: If request is invalid
        """
        if not request.agent_type:
            raise ValueError("agent_type is required")
        
        if request.agent_type != self.get_agent_type():
            raise ValueError(f"Request agent_type '{request.agent_type}' does not match agent '{self.get_agent_type()}'")
        
        if not request.prompt:
            raise ValueError("prompt is required")
        
        # Validate authentication if required
        if self.agent_core.auth_manager.enabled and not request.authentication:
            raise ValueError("authentication is required")
    
    async def handle_request(self, request: AgentRequest) -> AgentResponse:
        """
        Handle a complete request with error handling and metrics tracking.
        
        This method wraps the process_prompt method with common functionality
        like validation, error handling, and metrics tracking.
        
        Args:
            request: The agent request
            
        Returns:
            AgentResponse: The processed response
        """
        start_time = time.time()
        success = False
        
        try:
            # Validate request
            await self.validate_request(request)
            
            # Validate authentication if provided
            if request.authentication and self.agent_core.auth_manager.enabled:
                await self.agent_core.auth_manager.validate_token(request.authentication.access_token)
            
            # Process the request
            response = await self.process_prompt(request)
            
            # Ensure response has correct metadata
            response.agent_type = self.get_agent_type()
            response.request_id = request.request_id
            response.execution_time = time.time() - start_time
            response.success = True
            
            success = True
            return response
            
        except Exception as e:
            execution_time = time.time() - start_time
            
            self.agent_core.logger.error(
                f"Request processing failed for {self.get_agent_type()}",
                agent_type=self.get_agent_type(),
                request_id=request.request_id,
                execution_time=execution_time,
                error=str(e)
            )
            
            # Return error response
            error_response = ErrorResponse.from_exception(
                e, 
                ErrorCode.INTERNAL_ERROR,
                request_id=request.request_id
            )
            
            return AgentResponse(
                responses=[f"Error: {error_response.message}"],
                metadata={"error": error_response.to_dict()},
                execution_time=execution_time,
                agent_type=self.get_agent_type(),
                request_id=request.request_id,
                success=False
            )
        
        finally:
            # Update metrics
            execution_time = time.time() - start_time
            self.metrics.update_request_metrics(success, execution_time)
            self.metrics.uptime_seconds = (datetime.utcnow() - self._start_time).total_seconds()
    
    def get_metrics(self) -> AgentMetrics:
        """
        Get current agent metrics.
        
        Returns:
            AgentMetrics: Current metrics for this agent
        """
        self.metrics.uptime_seconds = (datetime.utcnow() - self._start_time).total_seconds()
        return self.metrics
    
    def is_healthy(self) -> bool:
        """
        Check if the agent is healthy.
        
        Returns:
            bool: True if agent is healthy, False otherwise
        """
        return self._initialized and self.agent_core.is_healthy()
    
    async def get_status(self) -> Dict[str, Any]:
        """
        Get comprehensive agent status.
        
        Returns:
            Dict containing agent status information
        """
        metrics = self.get_metrics()
        
        return {
            "agent_type": self.get_agent_type(),
            "initialized": self._initialized,
            "healthy": self.is_healthy(),
            "tools_count": len(self.tools),
            "available_tools": [tool.name for tool in self.tools],
            "metrics": {
                "total_requests": metrics.total_requests,
                "successful_requests": metrics.successful_requests,
                "failed_requests": metrics.failed_requests,
                "success_rate": metrics.success_rate,
                "average_response_time": metrics.average_response_time,
                "uptime_seconds": metrics.uptime_seconds,
                "last_request_time": metrics.last_request_time.isoformat() if metrics.last_request_time else None
            }
        }