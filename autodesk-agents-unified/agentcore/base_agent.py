"""
Base Agent Interface for AgentCore

Defines the abstract base class that all agents must implement,
providing common functionality and enforcing consistent interfaces.
"""

import asyncio
import time
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Type
import uuid

from .models import (
    AgentRequest, AgentResponse, AgentCapabilities, 
    ExecutionContext, ToolResult, ErrorCodes
)
from .logging import StructuredLogger, TraceContext


class BaseAgent(ABC):
    """
    Abstract base class for all AgentCore agents.
    
    Provides common functionality including logging, error handling,
    tool management, and execution context management.
    """
    
    def __init__(self, agent_core, agent_config: Dict[str, Any]):
        """Initialize base agent."""
        self.agent_core = agent_core
        self.config = agent_config
        self.logger = agent_core.logger
        
        # Agent metadata
        self._capabilities: Optional[AgentCapabilities] = None
        self._tools: Dict[str, Any] = {}
        self._initialized = False
        
        # Performance tracking
        self._request_count = 0
        self._total_execution_time = 0.0
        self._error_count = 0
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the agent and its tools."""
        pass
    
    @abstractmethod
    async def process_prompt(self, request: AgentRequest, 
                           context: ExecutionContext) -> AgentResponse:
        """
        Process a user prompt and return a response.
        
        Args:
            request: The user request containing prompt and context
            context: Execution context with metadata and shared state
            
        Returns:
            AgentResponse with the agent's response
        """
        pass
    
    @abstractmethod
    def get_capabilities(self) -> AgentCapabilities:
        """Get agent capabilities and metadata."""
        pass
    
    @abstractmethod
    def get_agent_type(self) -> str:
        """Return the agent type identifier."""
        pass
    
    async def execute_request(self, request: AgentRequest) -> AgentResponse:
        """
        Execute a request with full error handling and logging.
        
        This is the main entry point for agent execution, providing
        consistent error handling, logging, and performance tracking.
        """
        request_id = request.request_id or str(uuid.uuid4())
        start_time = time.time()
        
        # Create execution context
        context = ExecutionContext(
            request_id=request_id,
            project_id=request.context.get("project_id"),
            version_id=request.context.get("version_id"),
            element_group_id=request.context.get("element_group_id"),
            urn=request.context.get("urn"),
            timeout_seconds=self.config.get("timeout_seconds", 300)
        )
        
        # Set up trace context
        with TraceContext(request_id):
            try:
                # Validate request
                validation_error = await self._validate_request(request)
                if validation_error:
                    return validation_error
                
                # Check if agent is initialized
                if not self._initialized:
                    await self.initialize()
                    self._initialized = True
                
                # Log request start
                self.logger.info("Agent request started", extra={
                    "agent_type": self.get_agent_type(),
                    "request_id": request_id,
                    "prompt_length": len(request.prompt),
                    "context_keys": list(request.context.keys())
                })
                
                # Process the request
                response = await self.process_prompt(request, context)
                
                # Calculate execution time
                execution_time = time.time() - start_time
                response.execution_time = execution_time
                response.agent_type = self.get_agent_type()
                response.response_id = str(uuid.uuid4())
                
                # Update performance metrics
                self._request_count += 1
                self._total_execution_time += execution_time
                
                # Log successful completion
                self.logger.log_agent_execution(
                    agent_type=self.get_agent_type(),
                    prompt=request.prompt,
                    execution_time=execution_time,
                    success=True,
                    extra={
                        "request_id": request_id,
                        "response_count": len(response.responses),
                        "metadata_keys": list(response.metadata.keys())
                    }
                )
                
                return response
                
            except asyncio.TimeoutError:
                execution_time = time.time() - start_time
                self._error_count += 1
                
                error_response = AgentResponse.error(
                    error_message="Request timed out",
                    error_code=ErrorCodes.AGENT_TIMEOUT,
                    agent_type=self.get_agent_type()
                )
                error_response.execution_time = execution_time
                
                self.logger.log_agent_execution(
                    agent_type=self.get_agent_type(),
                    prompt=request.prompt,
                    execution_time=execution_time,
                    success=False,
                    extra={
                        "request_id": request_id,
                        "error": "timeout"
                    }
                )
                
                return error_response
                
            except Exception as e:
                execution_time = time.time() - start_time
                self._error_count += 1
                
                error_response = AgentResponse.error(
                    error_message=str(e),
                    error_code=ErrorCodes.UNKNOWN_ERROR,
                    agent_type=self.get_agent_type(),
                    error_details={
                        "error_type": type(e).__name__,
                        "request_id": request_id
                    }
                )
                error_response.execution_time = execution_time
                
                self.logger.log_agent_execution(
                    agent_type=self.get_agent_type(),
                    prompt=request.prompt,
                    execution_time=execution_time,
                    success=False,
                    extra={
                        "request_id": request_id,
                        "error": str(e),
                        "error_type": type(e).__name__
                    }
                )
                
                return error_response
    
    async def _validate_request(self, request: AgentRequest) -> Optional[AgentResponse]:
        """Validate incoming request."""
        if not request.prompt or not request.prompt.strip():
            return AgentResponse.error(
                error_message="Prompt is required and cannot be empty",
                error_code=ErrorCodes.MISSING_PARAMETER,
                agent_type=self.get_agent_type()
            )
        
        # Check prompt length limits
        capabilities = self.get_capabilities()
        if (capabilities.max_prompt_length and 
            len(request.prompt) > capabilities.max_prompt_length):
            return AgentResponse.error(
                error_message=f"Prompt too long (max {capabilities.max_prompt_length} characters)",
                error_code=ErrorCodes.INVALID_PARAMETER,
                agent_type=self.get_agent_type()
            )
        
        # Check authentication if required
        if capabilities.requires_authentication and not request.authentication:
            return AgentResponse.error(
                error_message="Authentication is required for this agent",
                error_code=ErrorCodes.AUTHENTICATION_FAILED,
                agent_type=self.get_agent_type()
            )
        
        # Check project context if required
        if (capabilities.requires_project_context and 
            not request.context.get("project_id")):
            return AgentResponse.error(
                error_message="Project context is required for this agent",
                error_code=ErrorCodes.MISSING_PARAMETER,
                agent_type=self.get_agent_type()
            )
        
        return None
    
    def register_tool(self, name: str, tool: Any) -> None:
        """Register a tool with this agent."""
        self._tools[name] = tool
        self.logger.debug(f"Tool registered: {name}", extra={
            "agent_type": self.get_agent_type(),
            "tool_name": name
        })
    
    def get_tool(self, name: str) -> Optional[Any]:
        """Get a registered tool by name."""
        return self._tools.get(name)
    
    def get_tools(self) -> Dict[str, Any]:
        """Get all registered tools."""
        return self._tools.copy()
    
    async def execute_tool(self, tool_name: str, **kwargs) -> ToolResult:
        """Execute a tool with error handling and logging."""
        tool = self.get_tool(tool_name)
        if not tool:
            return ToolResult.error(
                error_message=f"Tool '{tool_name}' not found",
                tool_name=tool_name,
                error_type="ToolNotFound"
            )
        
        start_time = time.time()
        
        try:
            self.logger.debug(f"Executing tool: {tool_name}", extra={
                "agent_type": self.get_agent_type(),
                "tool_name": tool_name,
                "kwargs_keys": list(kwargs.keys())
            })
            
            # Execute the tool
            if asyncio.iscoroutinefunction(tool):
                result = await tool(**kwargs)
            else:
                result = tool(**kwargs)
            
            execution_time = time.time() - start_time
            
            self.logger.debug(f"Tool executed successfully: {tool_name}", extra={
                "agent_type": self.get_agent_type(),
                "tool_name": tool_name,
                "execution_time": execution_time
            })
            
            return ToolResult(
                output=result,
                success=True,
                tool_name=tool_name,
                execution_time=execution_time
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            
            self.logger.error(f"Tool execution failed: {tool_name}", extra={
                "agent_type": self.get_agent_type(),
                "tool_name": tool_name,
                "error": str(e),
                "error_type": type(e).__name__,
                "execution_time": execution_time
            })
            
            return ToolResult.error(
                error_message=str(e),
                tool_name=tool_name,
                error_type=type(e).__name__
            )
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check for this agent."""
        try:
            capabilities = self.get_capabilities()
            
            # Calculate average response time
            avg_response_time = (
                self._total_execution_time / self._request_count 
                if self._request_count > 0 else 0
            )
            
            # Calculate error rate
            error_rate = (
                self._error_count / self._request_count 
                if self._request_count > 0 else 0
            )
            
            # Determine health status
            status = "healthy"
            if error_rate > 0.1:  # More than 10% errors
                status = "degraded"
            if error_rate > 0.5:  # More than 50% errors
                status = "unhealthy"
            
            return {
                "status": status,
                "agent_type": self.get_agent_type(),
                "initialized": self._initialized,
                "tools_count": len(self._tools),
                "request_count": self._request_count,
                "error_count": self._error_count,
                "error_rate": error_rate,
                "avg_response_time_ms": avg_response_time * 1000,
                "capabilities": capabilities.to_dict()
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "agent_type": self.get_agent_type(),
                "error": str(e),
                "error_type": type(e).__name__
            }
    
    async def shutdown(self) -> None:
        """Shutdown the agent and cleanup resources."""
        self.logger.info(f"Shutting down agent: {self.get_agent_type()}")
        
        # Cleanup tools if they have shutdown methods
        for tool_name, tool in self._tools.items():
            if hasattr(tool, 'shutdown') and callable(tool.shutdown):
                try:
                    if asyncio.iscoroutinefunction(tool.shutdown):
                        await tool.shutdown()
                    else:
                        tool.shutdown()
                except Exception as e:
                    self.logger.error(f"Error shutting down tool {tool_name}", extra={
                        "error": str(e),
                        "error_type": type(e).__name__
                    })
        
        self._initialized = False
        self.logger.info(f"Agent shutdown complete: {self.get_agent_type()}")
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get performance metrics for this agent."""
        avg_response_time = (
            self._total_execution_time / self._request_count 
            if self._request_count > 0 else 0
        )
        
        error_rate = (
            self._error_count / self._request_count 
            if self._request_count > 0 else 0
        )
        
        return {
            "agent_type": self.get_agent_type(),
            "request_count": self._request_count,
            "error_count": self._error_count,
            "error_rate": error_rate,
            "total_execution_time": self._total_execution_time,
            "avg_response_time_ms": avg_response_time * 1000,
            "tools_count": len(self._tools)
        }
    
    def __repr__(self) -> str:
        return (f"{self.__class__.__name__}("
                f"type={self.get_agent_type()}, "
                f"initialized={self._initialized}, "
                f"tools={len(self._tools)})")


class AgentExecutionError(Exception):
    """Custom exception for agent execution errors."""
    
    def __init__(self, message: str, error_code: str = ErrorCodes.UNKNOWN_ERROR,
                 details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.error_code = error_code
        self.details = details or {}