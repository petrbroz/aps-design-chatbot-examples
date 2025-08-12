"""
Core data models for the AgentCore framework.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum


@dataclass
class AgentRequest:
    """Request model for agent interactions."""
    agent_type: str
    prompt: str
    context: Dict[str, Any] = field(default_factory=dict)
    authentication: Optional['AuthContext'] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    request_id: Optional[str] = None
    timestamp: datetime = field(default_factory=lambda: datetime.utcnow())
    
    def __post_init__(self):
        """Post-initialization validation."""
        if not self.agent_type:
            raise ValueError("agent_type is required")
        if not self.prompt:
            raise ValueError("prompt is required")


@dataclass
class AgentResponse:
    """Response model for agent interactions."""
    responses: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)
    execution_time: float = 0.0
    agent_type: str = ""
    request_id: Optional[str] = None
    timestamp: datetime = field(default_factory=lambda: datetime.utcnow())
    success: bool = True
    
    def __post_init__(self):
        """Post-initialization validation."""
        if not isinstance(self.responses, list):
            raise ValueError("responses must be a list")


class ErrorCode(Enum):
    """Standard error codes for the system."""
    VALIDATION_ERROR = "VALIDATION_ERROR"
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    AUTHORIZATION_ERROR = "AUTHORIZATION_ERROR"
    AGENT_NOT_FOUND = "AGENT_NOT_FOUND"
    TOOL_ERROR = "TOOL_ERROR"
    EXTERNAL_SERVICE_ERROR = "EXTERNAL_SERVICE_ERROR"
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    TIMEOUT_ERROR = "TIMEOUT_ERROR"
    RATE_LIMIT_ERROR = "RATE_LIMIT_ERROR"


@dataclass
class ErrorResponse:
    """Standardized error response model."""
    error_code: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    trace_id: Optional[str] = None
    timestamp: datetime = field(default_factory=lambda: datetime.utcnow())
    request_id: Optional[str] = None
    
    def __post_init__(self):
        """Post-initialization validation."""
        if not self.error_code:
            raise ValueError("error_code is required")
        if not self.message:
            raise ValueError("message is required")
    
    @classmethod
    def from_exception(cls, error: Exception, error_code: ErrorCode = ErrorCode.INTERNAL_ERROR, 
                      trace_id: Optional[str] = None, request_id: Optional[str] = None) -> 'ErrorResponse':
        """Create ErrorResponse from an exception."""
        return cls(
            error_code=error_code.value,
            message=str(error),
            details={
                "exception_type": type(error).__name__,
                "exception_args": error.args
            },
            trace_id=trace_id,
            request_id=request_id
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "error_code": self.error_code,
            "message": self.message,
            "details": self.details,
            "trace_id": self.trace_id,
            "timestamp": self.timestamp.isoformat(),
            "request_id": self.request_id
        }


@dataclass
class ToolResult:
    """Result from tool execution."""
    tool_name: str
    success: bool
    result: Any = None
    error: Optional[str] = None
    execution_time: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Post-initialization validation."""
        if not self.tool_name:
            raise ValueError("tool_name is required")
        if not self.success and not self.error:
            raise ValueError("error message is required when success is False")


@dataclass
class AgentMetrics:
    """Metrics for agent performance tracking."""
    agent_type: str
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    average_response_time: float = 0.0
    last_request_time: Optional[datetime] = None
    uptime_seconds: float = 0.0
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate as a percentage."""
        if self.total_requests == 0:
            return 0.0
        return (self.successful_requests / self.total_requests) * 100.0
    
    def update_request_metrics(self, success: bool, response_time: float) -> None:
        """Update metrics with new request data."""
        self.total_requests += 1
        if success:
            self.successful_requests += 1
        else:
            self.failed_requests += 1
        
        # Update rolling average response time
        if self.total_requests == 1:
            self.average_response_time = response_time
        else:
            self.average_response_time = (
                (self.average_response_time * (self.total_requests - 1) + response_time) 
                / self.total_requests
            )
        
        self.last_request_time = datetime.utcnow()