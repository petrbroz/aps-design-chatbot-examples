"""
Common data models for AgentCore

Defines request/response models, authentication context,
and error handling structures used across all agents.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum


class AgentType(Enum):
    """Supported agent types."""
    MODEL_PROPERTIES = "model_properties"
    AEC_DATA_MODEL = "aec_data_model"
    MODEL_DERIVATIVES = "model_derivatives"


@dataclass
class AgentRequest:
    """
    Standard request format for all agents.
    
    Contains the user prompt, authentication context,
    and any additional metadata needed for processing.
    """
    agent_type: str
    prompt: str
    context: Dict[str, Any] = field(default_factory=dict)
    authentication: Optional['AuthContext'] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Request tracking
    request_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "agent_type": self.agent_type,
            "prompt": self.prompt,
            "context": self.context,
            "metadata": self.metadata,
            "request_id": self.request_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None
        }


@dataclass
class AgentResponse:
    """
    Standard response format for all agents.
    
    Contains the agent's responses, execution metadata,
    and any additional information for the client.
    """
    responses: List[str]
    success: bool = True
    agent_type: Optional[str] = None
    execution_time: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Error information
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    error_details: Optional[Dict[str, Any]] = None
    
    # Response tracking
    response_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        result = {
            "responses": self.responses,
            "success": self.success,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None
        }
        
        if self.agent_type:
            result["agent_type"] = self.agent_type
        if self.execution_time is not None:
            result["execution_time"] = self.execution_time
        if self.response_id:
            result["response_id"] = self.response_id
        
        # Include error information if present
        if not self.success:
            result.update({
                "error_code": self.error_code,
                "error_message": self.error_message,
                "error_details": self.error_details
            })
        
        return result
    
    @classmethod
    def error(cls, error_message: str, error_code: str = "AGENT_ERROR",
              agent_type: Optional[str] = None, 
              error_details: Optional[Dict[str, Any]] = None) -> 'AgentResponse':
        """Create an error response."""
        return cls(
            responses=[f"Error: {error_message}"],
            success=False,
            agent_type=agent_type,
            error_code=error_code,
            error_message=error_message,
            error_details=error_details or {}
        )


@dataclass
class ToolResult:
    """
    Result from tool execution.
    
    Contains the tool output, success status,
    and any metadata from the tool execution.
    """
    output: Any
    success: bool = True
    tool_name: Optional[str] = None
    execution_time: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Error information
    error_message: Optional[str] = None
    error_type: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "output": self.output,
            "success": self.success,
            "metadata": self.metadata
        }
        
        if self.tool_name:
            result["tool_name"] = self.tool_name
        if self.execution_time is not None:
            result["execution_time"] = self.execution_time
        
        if not self.success:
            result.update({
                "error_message": self.error_message,
                "error_type": self.error_type
            })
        
        return result
    
    @classmethod
    def error(cls, error_message: str, tool_name: Optional[str] = None,
              error_type: Optional[str] = None) -> 'ToolResult':
        """Create an error result."""
        return cls(
            output=None,
            success=False,
            tool_name=tool_name,
            error_message=error_message,
            error_type=error_type
        )


@dataclass
class CacheKey:
    """
    Cache key structure for consistent caching across agents.
    """
    namespace: str
    key: str
    version: Optional[str] = None
    
    def __str__(self) -> str:
        """String representation for cache key."""
        if self.version:
            return f"{self.namespace}:{self.key}:v{self.version}"
        return f"{self.namespace}:{self.key}"


@dataclass
class ExecutionContext:
    """
    Execution context for agent operations.
    
    Contains information about the current execution environment,
    user context, and any shared state.
    """
    request_id: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    trace_id: Optional[str] = None
    
    # Autodesk context
    project_id: Optional[str] = None
    version_id: Optional[str] = None
    element_group_id: Optional[str] = None
    urn: Optional[str] = None
    
    # Execution metadata
    start_time: datetime = field(default_factory=datetime.utcnow)
    timeout_seconds: Optional[int] = None
    
    # Shared state
    shared_data: Dict[str, Any] = field(default_factory=dict)
    
    def elapsed_time(self) -> float:
        """Get elapsed execution time in seconds."""
        return (datetime.utcnow() - self.start_time).total_seconds()
    
    def is_timeout(self) -> bool:
        """Check if execution has timed out."""
        if not self.timeout_seconds:
            return False
        return self.elapsed_time() > self.timeout_seconds


@dataclass
class AgentCapabilities:
    """
    Agent capabilities and metadata.
    
    Describes what an agent can do, its tools,
    and any limitations or requirements.
    """
    agent_type: str
    name: str
    description: str
    version: str
    
    # Capabilities
    tools: List[str] = field(default_factory=list)
    supported_formats: List[str] = field(default_factory=list)
    max_prompt_length: Optional[int] = None
    max_response_length: Optional[int] = None
    
    # Requirements
    requires_authentication: bool = True
    requires_project_context: bool = False
    requires_internet: bool = True
    
    # Performance characteristics
    typical_response_time_ms: Optional[int] = None
    max_concurrent_requests: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "agent_type": self.agent_type,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "tools": self.tools,
            "supported_formats": self.supported_formats,
            "max_prompt_length": self.max_prompt_length,
            "max_response_length": self.max_response_length,
            "requires_authentication": self.requires_authentication,
            "requires_project_context": self.requires_project_context,
            "requires_internet": self.requires_internet,
            "typical_response_time_ms": self.typical_response_time_ms,
            "max_concurrent_requests": self.max_concurrent_requests
        }


# Error codes for consistent error handling
class ErrorCodes:
    """Standard error codes used across all agents."""
    
    # General errors
    UNKNOWN_ERROR = "UNKNOWN_ERROR"
    INVALID_REQUEST = "INVALID_REQUEST"
    MISSING_PARAMETER = "MISSING_PARAMETER"
    INVALID_PARAMETER = "INVALID_PARAMETER"
    
    # Authentication errors
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    AUTHORIZATION_FAILED = "AUTHORIZATION_FAILED"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    INVALID_TOKEN = "INVALID_TOKEN"
    
    # Agent errors
    AGENT_NOT_FOUND = "AGENT_NOT_FOUND"
    AGENT_UNAVAILABLE = "AGENT_UNAVAILABLE"
    AGENT_TIMEOUT = "AGENT_TIMEOUT"
    AGENT_OVERLOADED = "AGENT_OVERLOADED"
    
    # Tool errors
    TOOL_NOT_FOUND = "TOOL_NOT_FOUND"
    TOOL_EXECUTION_FAILED = "TOOL_EXECUTION_FAILED"
    TOOL_TIMEOUT = "TOOL_TIMEOUT"
    
    # External service errors
    AUTODESK_API_ERROR = "AUTODESK_API_ERROR"
    AWS_SERVICE_ERROR = "AWS_SERVICE_ERROR"
    OPENSEARCH_ERROR = "OPENSEARCH_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"
    
    # Data errors
    DATA_NOT_FOUND = "DATA_NOT_FOUND"
    DATA_INVALID = "DATA_INVALID"
    DATA_TOO_LARGE = "DATA_TOO_LARGE"
    CACHE_ERROR = "CACHE_ERROR"