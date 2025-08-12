"""
Centralized error handling infrastructure for the AgentCore framework.
"""

import asyncio
import traceback
import uuid
import time
from typing import Dict, Any, Optional, Callable, Type, List, Union
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum

from .models import ErrorResponse, ErrorCode, AgentRequest, AgentResponse
from .logging import StructuredLogger


class RetryStrategy(Enum):
    """Retry strategy types."""
    EXPONENTIAL_BACKOFF = "exponential_backoff"
    LINEAR_BACKOFF = "linear_backoff"
    FIXED_DELAY = "fixed_delay"
    IMMEDIATE = "immediate"


@dataclass
class RetryPolicy:
    """Retry policy configuration."""
    max_retries: int = 3
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL_BACKOFF
    base_delay: float = 1.0
    max_delay: float = 60.0
    backoff_factor: float = 2.0
    retry_exceptions: List[Type[Exception]] = field(default_factory=lambda: [ConnectionError, TimeoutError])
    jitter: bool = True


@dataclass
class RetryAttempt:
    """Information about a retry attempt."""
    attempt_number: int
    exception: Exception
    delay: float
    timestamp: datetime
    operation_name: str


@dataclass
class ErrorMetrics:
    """Error handling metrics."""
    total_errors: int = 0
    errors_by_type: Dict[str, int] = field(default_factory=dict)
    errors_by_agent: Dict[str, int] = field(default_factory=dict)
    retry_attempts: int = 0
    successful_recoveries: int = 0
    failed_recoveries: int = 0
    last_error_time: Optional[datetime] = None
    error_rate_per_minute: float = 0.0


class AlertSeverity(Enum):
    """Alert severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ErrorAlert:
    """Error alert information."""
    severity: AlertSeverity
    message: str
    error_type: str
    count: int
    first_occurrence: datetime
    last_occurrence: datetime
    details: Dict[str, Any] = field(default_factory=dict)


class ErrorHandler:
    """
    Centralized error handling and recovery system.
    
    This class provides consistent error handling across all agents and tools,
    with support for error recovery, retry mechanisms, and detailed logging.
    """
    
    def __init__(self, logger: StructuredLogger):
        """
        Initialize the error handler.
        
        Args:
            logger: The structured logger instance
        """
        self.logger = logger
        self._error_handlers: Dict[Type[Exception], Callable] = {}
        self._retry_policies: Dict[str, RetryPolicy] = {}
        self._metrics = ErrorMetrics()
        self._error_history: List[Dict[str, Any]] = []
        self._alert_thresholds: Dict[str, Dict[str, Any]] = {}
        self._alert_callbacks: List[Callable[[ErrorAlert], None]] = []
        self._circuit_breakers: Dict[str, Dict[str, Any]] = {}
    
    def register_error_handler(self, exception_type: Type[Exception], 
                             handler: Callable[[Exception, Dict[str, Any]], ErrorResponse]) -> None:
        """
        Register a custom error handler for a specific exception type.
        
        Args:
            exception_type: The exception type to handle
            handler: The handler function that takes (exception, context) and returns ErrorResponse
        """
        self._error_handlers[exception_type] = handler
        self.logger.debug(f"Registered error handler for {exception_type.__name__}")
    
    def set_retry_policy(self, operation_name: str, policy: RetryPolicy) -> None:
        """
        Set retry policy for a specific operation.
        
        Args:
            operation_name: Name of the operation
            policy: Retry policy configuration
        """
        self._retry_policies[operation_name] = policy
        self.logger.debug(f"Set retry policy for {operation_name}", policy={
            "max_retries": policy.max_retries,
            "strategy": policy.strategy.value,
            "base_delay": policy.base_delay,
            "max_delay": policy.max_delay,
            "backoff_factor": policy.backoff_factor,
            "retry_exceptions": [exc.__name__ for exc in policy.retry_exceptions]
        })
    
    def set_alert_threshold(self, error_type: str, threshold: int, time_window_minutes: int = 5,
                           severity: AlertSeverity = AlertSeverity.MEDIUM) -> None:
        """
        Set alert threshold for specific error types.
        
        Args:
            error_type: Type of error to monitor
            threshold: Number of errors to trigger alert
            time_window_minutes: Time window for counting errors
            severity: Alert severity level
        """
        self._alert_thresholds[error_type] = {
            "threshold": threshold,
            "time_window_minutes": time_window_minutes,
            "severity": severity
        }
        self.logger.debug(f"Set alert threshold for {error_type}", 
                         threshold=threshold, time_window=time_window_minutes, severity=severity.value)
    
    def register_alert_callback(self, callback: Callable[[ErrorAlert], None]) -> None:
        """
        Register a callback function for error alerts.
        
        Args:
            callback: Function to call when an alert is triggered
        """
        self._alert_callbacks.append(callback)
        self.logger.debug("Registered alert callback")
    
    def set_circuit_breaker(self, operation_name: str, failure_threshold: int = 5,
                           recovery_timeout: int = 60, half_open_max_calls: int = 3) -> None:
        """
        Set circuit breaker for an operation.
        
        Args:
            operation_name: Name of the operation
            failure_threshold: Number of failures to open circuit
            recovery_timeout: Seconds to wait before trying to close circuit
            half_open_max_calls: Max calls allowed in half-open state
        """
        self._circuit_breakers[operation_name] = {
            "failure_threshold": failure_threshold,
            "recovery_timeout": recovery_timeout,
            "half_open_max_calls": half_open_max_calls,
            "failure_count": 0,
            "last_failure_time": None,
            "state": "closed",  # closed, open, half_open
            "half_open_calls": 0
        }
        self.logger.debug(f"Set circuit breaker for {operation_name}", 
                         failure_threshold=failure_threshold, recovery_timeout=recovery_timeout)
    
    async def handle_agent_error(self, error: Exception, context: AgentRequest) -> AgentResponse:
        """
        Handle agent-specific errors with context.
        
        Args:
            error: The exception that occurred
            context: The agent request context
            
        Returns:
            AgentResponse: Error response with appropriate error information
        """
        trace_id = str(uuid.uuid4())
        
        # Log the error with full context
        self.logger.error(
            "Agent error occurred",
            agent_type=context.agent_type,
            request_id=context.request_id,
            trace_id=trace_id,
            error_type=type(error).__name__,
            error_message=str(error),
            traceback=traceback.format_exc(),
            context={
                "prompt_length": len(context.prompt),
                "has_authentication": context.authentication is not None,
                "metadata_keys": list(context.metadata.keys()) if context.metadata else []
            }
        )
        
        # Determine error code based on exception type
        error_code = self._determine_error_code(error)
        
        # Check for custom error handler
        error_response = None
        for exc_type, handler in self._error_handlers.items():
            if isinstance(error, exc_type):
                try:
                    error_response = handler(error, {
                        "agent_type": context.agent_type,
                        "request_id": context.request_id,
                        "trace_id": trace_id
                    })
                    break
                except Exception as handler_error:
                    self.logger.error(
                        "Error handler failed",
                        trace_id=trace_id,
                        handler_error=str(handler_error)
                    )
        
        # Create default error response if no custom handler succeeded
        if not error_response:
            error_response = ErrorResponse.from_exception(
                error, 
                error_code, 
                trace_id=trace_id,
                request_id=context.request_id
            )
        
        # Create agent response with error information
        return AgentResponse(
            responses=[f"Error: {error_response.message}"],
            metadata={
                "error": error_response.to_dict(),
                "trace_id": trace_id,
                "recoverable": self._is_recoverable_error(error)
            },
            execution_time=0.0,
            agent_type=context.agent_type,
            request_id=context.request_id,
            success=False
        )
    
    async def handle_tool_error(self, error: Exception, tool_name: str, 
                              context: Optional[Dict[str, Any]] = None) -> ErrorResponse:
        """
        Handle tool execution errors.
        
        Args:
            error: The exception that occurred
            tool_name: Name of the tool that failed
            context: Additional context information
            
        Returns:
            ErrorResponse: Structured error response
        """
        trace_id = str(uuid.uuid4())
        context = context or {}
        
        # Log the tool error
        self.logger.error(
            "Tool execution error",
            tool_name=tool_name,
            trace_id=trace_id,
            error_type=type(error).__name__,
            error_message=str(error),
            traceback=traceback.format_exc(),
            context=context
        )
        
        # Determine error code
        error_code = self._determine_error_code(error)
        
        # Create error response
        error_response = ErrorResponse(
            error_code=error_code.value,
            message=f"Tool '{tool_name}' execution failed: {str(error)}",
            details={
                "tool_name": tool_name,
                "exception_type": type(error).__name__,
                "context": context,
                "recoverable": self._is_recoverable_error(error)
            },
            trace_id=trace_id
        )
        
        return error_response
    
    async def handle_validation_error(self, error: Exception, field_name: str = None, 
                                    value: Any = None) -> ErrorResponse:
        """
        Handle validation errors with specific field information.
        
        Args:
            error: The validation exception
            field_name: Name of the field that failed validation
            value: The invalid value
            
        Returns:
            ErrorResponse: Structured validation error response
        """
        trace_id = str(uuid.uuid4())
        
        self.logger.warning(
            "Validation error",
            trace_id=trace_id,
            field_name=field_name,
            error_message=str(error),
            invalid_value=str(value) if value is not None else None
        )
        
        return ErrorResponse(
            error_code=ErrorCode.VALIDATION_ERROR.value,
            message=str(error),
            details={
                "field_name": field_name,
                "invalid_value": str(value) if value is not None else None,
                "validation_type": type(error).__name__
            },
            trace_id=trace_id
        )
    
    async def handle_authentication_error(self, error: Exception, 
                                        auth_context: Optional[Dict[str, Any]] = None) -> ErrorResponse:
        """
        Handle authentication and authorization errors.
        
        Args:
            error: The authentication exception
            auth_context: Authentication context information
            
        Returns:
            ErrorResponse: Structured authentication error response
        """
        trace_id = str(uuid.uuid4())
        
        self.logger.warning(
            "Authentication error",
            trace_id=trace_id,
            error_message=str(error),
            auth_context=auth_context or {}
        )
        
        # Determine if it's authentication or authorization
        error_code = ErrorCode.AUTHENTICATION_ERROR
        if "unauthorized" in str(error).lower() or "forbidden" in str(error).lower():
            error_code = ErrorCode.AUTHORIZATION_ERROR
        
        return ErrorResponse(
            error_code=error_code.value,
            message=str(error),
            details={
                "auth_context": auth_context or {},
                "error_type": type(error).__name__
            },
            trace_id=trace_id
        )
    
    def _determine_error_code(self, error: Exception) -> ErrorCode:
        """
        Determine the appropriate error code for an exception.
        
        Args:
            error: The exception to categorize
            
        Returns:
            ErrorCode: The appropriate error code
        """
        error_type = type(error).__name__.lower()
        error_message = str(error).lower()
        
        # Authentication/Authorization errors (check first)
        if any(keyword in error_message for keyword in ["unauthorized", "forbidden", "invalid token", "expired token"]):
            return ErrorCode.AUTHENTICATION_ERROR
        
        # External service errors (check before validation)
        if any(keyword in error_message for keyword in ["connection", "timeout", "service unavailable", "api"]):
            return ErrorCode.EXTERNAL_SERVICE_ERROR
        
        # Configuration errors (check before validation)
        if any(keyword in error_message for keyword in ["config", "setting", "environment"]):
            return ErrorCode.CONFIGURATION_ERROR
        
        # Rate limit errors (check before validation)
        if any(keyword in error_message for keyword in ["rate limit", "too many requests", "quota"]):
            return ErrorCode.RATE_LIMIT_ERROR
        
        # Timeout errors (check before validation)
        if "timeout" in error_type or "timeout" in error_message:
            return ErrorCode.TIMEOUT_ERROR
        
        # Validation errors (check after more specific errors)
        if any(keyword in error_type for keyword in ["validation", "value", "type"]):
            return ErrorCode.VALIDATION_ERROR
        
        # Default to internal error
        return ErrorCode.INTERNAL_ERROR
    
    def _is_recoverable_error(self, error: Exception) -> bool:
        """
        Determine if an error is recoverable (can be retried).
        
        Args:
            error: The exception to check
            
        Returns:
            bool: True if the error is recoverable
        """
        recoverable_types = [
            ConnectionError,
            TimeoutError,
        ]
        
        recoverable_messages = [
            "connection timeout",
            "service unavailable",
            "temporary failure",
            "rate limit"
        ]
        
        # Check exception type
        if any(isinstance(error, exc_type) for exc_type in recoverable_types):
            return True
        
        # Check error message
        error_message = str(error).lower()
        if any(msg in error_message for msg in recoverable_messages):
            return True
        
        return False
    
    async def create_system_error(self, message: str, details: Dict[str, Any] = None) -> ErrorResponse:
        """
        Create a system-level error response.
        
        Args:
            message: Error message
            details: Additional error details
            
        Returns:
            ErrorResponse: System error response
        """
        trace_id = str(uuid.uuid4())
        
        self.logger.error(
            "System error",
            trace_id=trace_id,
            message=message,
            details=details or {}
        )
        
        return ErrorResponse(
            error_code=ErrorCode.INTERNAL_ERROR.value,
            message=message,
            details=details or {},
            trace_id=trace_id
        )
    
    async def execute_with_retry(self, operation_name: str, operation: Callable, 
                               *args, **kwargs) -> Any:
        """
        Execute an operation with retry logic.
        
        Args:
            operation_name: Name of the operation for policy lookup
            operation: The operation to execute
            *args: Arguments to pass to the operation
            **kwargs: Keyword arguments to pass to the operation
            
        Returns:
            Result of the operation
            
        Raises:
            Exception: The last exception if all retries fail
        """
        policy = self._retry_policies.get(operation_name, RetryPolicy())
        retry_attempts = []
        last_exception = None
        
        # Check circuit breaker
        if not self._check_circuit_breaker(operation_name):
            raise RuntimeError(f"Circuit breaker is open for operation: {operation_name}")
        
        for attempt in range(policy.max_retries + 1):
            try:
                # Execute the operation
                if asyncio.iscoroutinefunction(operation):
                    result = await operation(*args, **kwargs)
                else:
                    result = operation(*args, **kwargs)
                
                # Success - update metrics and circuit breaker
                if attempt > 0:
                    self._metrics.successful_recoveries += 1
                    self.logger.info(f"Operation {operation_name} succeeded after {attempt} retries")
                
                self._update_circuit_breaker_success(operation_name)
                return result
                
            except Exception as e:
                last_exception = e
                self._update_error_metrics(e, operation_name)
                self._update_circuit_breaker_failure(operation_name)
                
                # Check if this exception should trigger a retry
                should_retry = any(isinstance(e, exc_type) for exc_type in policy.retry_exceptions)
                
                if not should_retry or attempt >= policy.max_retries:
                    self._metrics.failed_recoveries += 1
                    break
                
                # Calculate delay
                delay = self._calculate_retry_delay(policy, attempt)
                
                # Record retry attempt
                retry_attempt = RetryAttempt(
                    attempt_number=attempt + 1,
                    exception=e,
                    delay=delay,
                    timestamp=datetime.utcnow(),
                    operation_name=operation_name
                )
                retry_attempts.append(retry_attempt)
                self._metrics.retry_attempts += 1
                
                self.logger.warning(
                    f"Operation {operation_name} failed, retrying in {delay}s",
                    attempt=attempt + 1,
                    max_retries=policy.max_retries,
                    error=str(e),
                    delay=delay
                )
                
                # Wait before retry
                await asyncio.sleep(delay)
        
        # All retries failed
        self.logger.error(
            f"Operation {operation_name} failed after {policy.max_retries} retries",
            total_attempts=len(retry_attempts) + 1,
            final_error=str(last_exception)
        )
        
        raise last_exception
    
    def _calculate_retry_delay(self, policy: RetryPolicy, attempt: int) -> float:
        """
        Calculate delay for retry attempt based on strategy.
        
        Args:
            policy: Retry policy
            attempt: Current attempt number (0-based)
            
        Returns:
            Delay in seconds
        """
        if policy.strategy == RetryStrategy.EXPONENTIAL_BACKOFF:
            delay = policy.base_delay * (policy.backoff_factor ** attempt)
        elif policy.strategy == RetryStrategy.LINEAR_BACKOFF:
            delay = policy.base_delay * (attempt + 1)
        elif policy.strategy == RetryStrategy.FIXED_DELAY:
            delay = policy.base_delay
        else:  # IMMEDIATE
            delay = 0.0
        
        # Apply max delay limit
        delay = min(delay, policy.max_delay)
        
        # Add jitter if enabled
        if policy.jitter and delay > 0:
            import random
            delay = delay * (0.5 + random.random() * 0.5)
        
        return delay
    
    def _check_circuit_breaker(self, operation_name: str) -> bool:
        """
        Check if circuit breaker allows operation execution.
        
        Args:
            operation_name: Name of the operation
            
        Returns:
            True if operation can proceed, False if circuit is open
        """
        if operation_name not in self._circuit_breakers:
            return True
        
        breaker = self._circuit_breakers[operation_name]
        current_time = datetime.utcnow()
        
        if breaker["state"] == "open":
            # Check if recovery timeout has passed
            if (breaker["last_failure_time"] and 
                (current_time - breaker["last_failure_time"]).total_seconds() >= breaker["recovery_timeout"]):
                breaker["state"] = "half_open"
                breaker["half_open_calls"] = 0
                self.logger.info(f"Circuit breaker for {operation_name} moved to half-open state")
                return True
            return False
        
        elif breaker["state"] == "half_open":
            # Allow limited calls in half-open state
            if breaker["half_open_calls"] < breaker["half_open_max_calls"]:
                breaker["half_open_calls"] += 1
                return True
            return False
        
        # Closed state - allow operation
        return True
    
    def _update_circuit_breaker_success(self, operation_name: str) -> None:
        """
        Update circuit breaker on successful operation.
        
        Args:
            operation_name: Name of the operation
        """
        if operation_name not in self._circuit_breakers:
            return
        
        breaker = self._circuit_breakers[operation_name]
        
        if breaker["state"] == "half_open":
            # Success in half-open state - close the circuit
            breaker["state"] = "closed"
            breaker["failure_count"] = 0
            breaker["half_open_calls"] = 0
            self.logger.info(f"Circuit breaker for {operation_name} closed after successful recovery")
        elif breaker["state"] == "closed":
            # Reset failure count on success
            breaker["failure_count"] = 0
    
    def _update_circuit_breaker_failure(self, operation_name: str) -> None:
        """
        Update circuit breaker on operation failure.
        
        Args:
            operation_name: Name of the operation
        """
        if operation_name not in self._circuit_breakers:
            return
        
        breaker = self._circuit_breakers[operation_name]
        breaker["failure_count"] += 1
        breaker["last_failure_time"] = datetime.utcnow()
        
        if breaker["state"] == "closed" and breaker["failure_count"] >= breaker["failure_threshold"]:
            breaker["state"] = "open"
            self.logger.warning(f"Circuit breaker for {operation_name} opened after {breaker['failure_count']} failures")
        elif breaker["state"] == "half_open":
            # Failure in half-open state - back to open
            breaker["state"] = "open"
            self.logger.warning(f"Circuit breaker for {operation_name} reopened after failure in half-open state")
    
    def _update_error_metrics(self, error: Exception, operation_name: str = None) -> None:
        """
        Update error metrics and check for alerts.
        
        Args:
            error: The exception that occurred
            operation_name: Name of the operation (optional)
        """
        current_time = datetime.utcnow()
        error_type = type(error).__name__
        
        # Update metrics
        self._metrics.total_errors += 1
        self._metrics.errors_by_type[error_type] = self._metrics.errors_by_type.get(error_type, 0) + 1
        self._metrics.last_error_time = current_time
        
        if operation_name:
            self._metrics.errors_by_agent[operation_name] = self._metrics.errors_by_agent.get(operation_name, 0) + 1
        
        # Add to error history
        error_record = {
            "timestamp": current_time,
            "error_type": error_type,
            "error_message": str(error),
            "operation_name": operation_name,
            "trace_id": str(uuid.uuid4())
        }
        self._error_history.append(error_record)
        
        # Keep only recent history (last 1000 errors)
        if len(self._error_history) > 1000:
            self._error_history = self._error_history[-1000:]
        
        # Calculate error rate
        self._calculate_error_rate()
        
        # Check for alerts
        self._check_error_alerts(error_type, current_time)
    
    def _calculate_error_rate(self) -> None:
        """Calculate current error rate per minute."""
        current_time = datetime.utcnow()
        one_minute_ago = current_time - timedelta(minutes=1)
        
        recent_errors = [
            error for error in self._error_history
            if error["timestamp"] >= one_minute_ago
        ]
        
        self._metrics.error_rate_per_minute = len(recent_errors)
    
    def _check_error_alerts(self, error_type: str, current_time: datetime) -> None:
        """
        Check if error thresholds are exceeded and trigger alerts.
        
        Args:
            error_type: Type of error that occurred
            current_time: Current timestamp
        """
        if error_type not in self._alert_thresholds:
            return
        
        threshold_config = self._alert_thresholds[error_type]
        time_window = timedelta(minutes=threshold_config["time_window_minutes"])
        window_start = current_time - time_window
        
        # Count errors of this type in the time window
        error_count = len([
            error for error in self._error_history
            if (error["error_type"] == error_type and 
                error["timestamp"] >= window_start)
        ])
        
        if error_count >= threshold_config["threshold"]:
            # Find first occurrence in this window
            first_occurrence = min([
                error["timestamp"] for error in self._error_history
                if (error["error_type"] == error_type and 
                    error["timestamp"] >= window_start)
            ])
            
            # Create alert
            alert = ErrorAlert(
                severity=threshold_config["severity"],
                message=f"Error threshold exceeded: {error_count} {error_type} errors in {threshold_config['time_window_minutes']} minutes",
                error_type=error_type,
                count=error_count,
                first_occurrence=first_occurrence,
                last_occurrence=current_time,
                details={
                    "threshold": threshold_config["threshold"],
                    "time_window_minutes": threshold_config["time_window_minutes"],
                    "error_rate": error_count / threshold_config["time_window_minutes"]
                }
            )
            
            # Trigger alert callbacks
            self._trigger_alert(alert)
    
    def _trigger_alert(self, alert: ErrorAlert) -> None:
        """
        Trigger alert callbacks.
        
        Args:
            alert: The error alert to send
        """
        self.logger.warning(
            "Error alert triggered",
            severity=alert.severity.value,
            error_type=alert.error_type,
            count=alert.count,
            alert_message=alert.message
        )
        
        for callback in self._alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                self.logger.error(f"Alert callback failed: {str(e)}")
    
    def get_error_statistics(self) -> Dict[str, Any]:
        """
        Get comprehensive error handling statistics.
        
        Returns:
            Dict containing error statistics
        """
        return {
            "total_errors": self._metrics.total_errors,
            "errors_by_type": dict(self._metrics.errors_by_type),
            "errors_by_agent": dict(self._metrics.errors_by_agent),
            "retry_attempts": self._metrics.retry_attempts,
            "successful_recoveries": self._metrics.successful_recoveries,
            "failed_recoveries": self._metrics.failed_recoveries,
            "last_error_time": self._metrics.last_error_time.isoformat() if self._metrics.last_error_time else None,
            "error_rate_per_minute": self._metrics.error_rate_per_minute,
            "circuit_breakers": {
                name: {
                    "state": breaker["state"],
                    "failure_count": breaker["failure_count"],
                    "last_failure_time": breaker["last_failure_time"].isoformat() if breaker["last_failure_time"] else None
                }
                for name, breaker in self._circuit_breakers.items()
            },
            "active_retry_policies": list(self._retry_policies.keys()),
            "alert_thresholds": list(self._alert_thresholds.keys())
        }
    
    def get_recent_errors(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get recent error history.
        
        Args:
            limit: Maximum number of errors to return
            
        Returns:
            List of recent error records
        """
        return self._error_history[-limit:] if self._error_history else []
    
    def clear_error_history(self) -> None:
        """Clear error history and reset metrics."""
        self._error_history.clear()
        self._metrics = ErrorMetrics()
        self.logger.info("Error history and metrics cleared")