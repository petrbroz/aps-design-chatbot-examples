"""
Centralized Error Handling for AgentCore

Provides consistent error handling, recovery mechanisms,
and error reporting across all agents and services.
"""

import asyncio
import traceback
from typing import Dict, Any, Optional, Callable, List
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum

from .models import AgentResponse, ErrorCodes
from .logging import StructuredLogger


class ErrorSeverity(Enum):
    """Error severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ErrorContext:
    """Context information for error handling."""
    component: str
    operation: str
    request_id: Optional[str] = None
    user_id: Optional[str] = None
    additional_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ErrorRecord:
    """Record of an error occurrence."""
    error_id: str
    error_code: str
    message: str
    severity: ErrorSeverity
    context: ErrorContext
    timestamp: datetime
    stack_trace: Optional[str] = None
    resolved: bool = False
    resolution_notes: Optional[str] = None


class ErrorHandler:
    """
    Centralized error handler for AgentCore system.
    
    Provides consistent error handling, logging, recovery,
    and reporting across all components.
    """
    
    def __init__(self, logger: StructuredLogger):
        """Initialize error handler."""
        self.logger = logger
        
        # Error tracking
        self._error_records: List[ErrorRecord] = []
        self._error_counts: Dict[str, int] = {}
        self._recovery_handlers: Dict[str, Callable] = {}
        
        # Configuration
        self.max_error_records = 1000
        self.enable_stack_traces = True
    
    def register_recovery_handler(self, error_code: str, handler: Callable) -> None:
        """Register a recovery handler for specific error codes."""
        self._recovery_handlers[error_code] = handler
        self.logger.info(f"Recovery handler registered for error code: {error_code}")
    
    async def handle_error(self, error: Exception, context: ErrorContext,
                          severity: ErrorSeverity = ErrorSeverity.MEDIUM) -> AgentResponse:
        """
        Handle an error with logging, recovery, and response generation.
        
        Args:
            error: The exception that occurred
            context: Context information about where the error occurred
            severity: Severity level of the error
            
        Returns:
            AgentResponse with appropriate error information
        """
        # Determine error code
        error_code = self._determine_error_code(error)
        
        # Generate error ID
        error_id = f"{context.component}_{context.operation}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        
        # Create error record
        error_record = ErrorRecord(
            error_id=error_id,
            error_code=error_code,
            message=str(error),
            severity=severity,
            context=context,
            timestamp=datetime.utcnow(),
            stack_trace=traceback.format_exc() if self.enable_stack_traces else None
        )
        
        # Store error record
        self._store_error_record(error_record)
        
        # Log the error
        self._log_error(error_record)
        
        # Attempt recovery
        recovery_result = await self._attempt_recovery(error_record)
        
        # Generate response
        return self._generate_error_response(error_record, recovery_result)
    
    def _determine_error_code(self, error: Exception) -> str:
        """Determine appropriate error code based on exception type."""
        error_type = type(error).__name__
        
        # Map common exception types to error codes
        error_mapping = {
            'ValueError': ErrorCodes.INVALID_PARAMETER,
            'KeyError': ErrorCodes.MISSING_PARAMETER,
            'FileNotFoundError': ErrorCodes.DATA_NOT_FOUND,
            'PermissionError': ErrorCodes.AUTHORIZATION_FAILED,
            'TimeoutError': ErrorCodes.AGENT_TIMEOUT,
            'ConnectionError': ErrorCodes.AUTODESK_API_ERROR,
            'HTTPError': ErrorCodes.AUTODESK_API_ERROR,
            'DatabaseError': ErrorCodes.DATABASE_ERROR,
            'SQLAlchemyError': ErrorCodes.DATABASE_ERROR,
        }
        
        # Check if error has a custom error_code attribute
        if hasattr(error, 'error_code'):
            return error.error_code
        
        # Use mapping or default
        return error_mapping.get(error_type, ErrorCodes.UNKNOWN_ERROR)
    
    def _store_error_record(self, error_record: ErrorRecord) -> None:
        """Store error record for tracking and analysis."""
        self._error_records.append(error_record)
        
        # Update error counts
        self._error_counts[error_record.error_code] = (
            self._error_counts.get(error_record.error_code, 0) + 1
        )
        
        # Limit stored records
        if len(self._error_records) > self.max_error_records:
            self._error_records = self._error_records[-self.max_error_records:]
    
    def _log_error(self, error_record: ErrorRecord) -> None:
        """Log error with appropriate level and context."""
        log_level_mapping = {
            ErrorSeverity.LOW: self.logger.debug,
            ErrorSeverity.MEDIUM: self.logger.warning,
            ErrorSeverity.HIGH: self.logger.error,
            ErrorSeverity.CRITICAL: self.logger.critical
        }
        
        log_func = log_level_mapping.get(error_record.severity, self.logger.error)
        
        log_func(f"Error in {error_record.context.component}", extra={
            "error_id": error_record.error_id,
            "error_code": error_record.error_code,
            "component": error_record.context.component,
            "operation": error_record.context.operation,
            "request_id": error_record.context.request_id,
            "user_id": error_record.context.user_id,
            "severity": error_record.severity.value,
            "message": error_record.message,
            "additional_data": error_record.context.additional_data,
            "stack_trace": error_record.stack_trace
        })
    
    async def _attempt_recovery(self, error_record: ErrorRecord) -> Optional[Dict[str, Any]]:
        """Attempt to recover from the error using registered handlers."""
        recovery_handler = self._recovery_handlers.get(error_record.error_code)
        
        if not recovery_handler:
            return None
        
        try:
            self.logger.info(f"Attempting recovery for error: {error_record.error_code}", extra={
                "error_id": error_record.error_id,
                "component": error_record.context.component
            })
            
            # Execute recovery handler
            if asyncio.iscoroutinefunction(recovery_handler):
                recovery_result = await recovery_handler(error_record)
            else:
                recovery_result = recovery_handler(error_record)
            
            if recovery_result:
                error_record.resolved = True
                error_record.resolution_notes = "Automatic recovery successful"
                
                self.logger.info(f"Recovery successful for error: {error_record.error_code}", extra={
                    "error_id": error_record.error_id,
                    "recovery_result": recovery_result
                })
            
            return recovery_result
            
        except Exception as recovery_error:
            self.logger.error(f"Recovery failed for error: {error_record.error_code}", extra={
                "error_id": error_record.error_id,
                "recovery_error": str(recovery_error),
                "recovery_error_type": type(recovery_error).__name__
            })
            return None
    
    def _generate_error_response(self, error_record: ErrorRecord, 
                                recovery_result: Optional[Dict[str, Any]]) -> AgentResponse:
        """Generate appropriate error response."""
        # Determine user-friendly message
        user_message = self._get_user_friendly_message(error_record.error_code, error_record.message)
        
        # Create error details
        error_details = {
            "error_id": error_record.error_id,
            "component": error_record.context.component,
            "operation": error_record.context.operation,
            "timestamp": error_record.timestamp.isoformat(),
            "severity": error_record.severity.value
        }
        
        # Add recovery information if available
        if recovery_result:
            error_details["recovery_attempted"] = True
            error_details["recovery_result"] = recovery_result
            error_details["resolved"] = error_record.resolved
        
        # Add request context if available
        if error_record.context.request_id:
            error_details["request_id"] = error_record.context.request_id
        
        return AgentResponse.error(
            error_message=user_message,
            error_code=error_record.error_code,
            error_details=error_details
        )
    
    def _get_user_friendly_message(self, error_code: str, original_message: str) -> str:
        """Convert technical error messages to user-friendly ones."""
        user_friendly_messages = {
            ErrorCodes.AUTHENTICATION_FAILED: "Authentication failed. Please check your credentials.",
            ErrorCodes.AUTHORIZATION_FAILED: "You don't have permission to access this resource.",
            ErrorCodes.TOKEN_EXPIRED: "Your session has expired. Please log in again.",
            ErrorCodes.AGENT_TIMEOUT: "The request took too long to process. Please try again.",
            ErrorCodes.AGENT_OVERLOADED: "The system is currently busy. Please try again in a moment.",
            ErrorCodes.AUTODESK_API_ERROR: "There was an issue connecting to Autodesk services.",
            ErrorCodes.DATA_NOT_FOUND: "The requested data could not be found.",
            ErrorCodes.DATA_INVALID: "The provided data is invalid or corrupted.",
            ErrorCodes.MISSING_PARAMETER: "Required information is missing from your request.",
            ErrorCodes.INVALID_PARAMETER: "Some of the provided information is invalid."
        }
        
        return user_friendly_messages.get(error_code, original_message)
    
    def get_error_statistics(self) -> Dict[str, Any]:
        """Get error statistics and trends."""
        total_errors = len(self._error_records)
        
        if total_errors == 0:
            return {
                "total_errors": 0,
                "error_codes": {},
                "severity_distribution": {},
                "resolution_rate": 0.0
            }
        
        # Calculate severity distribution
        severity_counts = {}
        resolved_count = 0
        
        for record in self._error_records:
            severity_counts[record.severity.value] = (
                severity_counts.get(record.severity.value, 0) + 1
            )
            if record.resolved:
                resolved_count += 1
        
        return {
            "total_errors": total_errors,
            "error_codes": self._error_counts.copy(),
            "severity_distribution": severity_counts,
            "resolution_rate": resolved_count / total_errors,
            "most_common_errors": sorted(
                self._error_counts.items(), 
                key=lambda x: x[1], 
                reverse=True
            )[:5]
        }
    
    def get_recent_errors(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent error records."""
        recent_errors = sorted(
            self._error_records, 
            key=lambda x: x.timestamp, 
            reverse=True
        )[:limit]
        
        return [
            {
                "error_id": record.error_id,
                "error_code": record.error_code,
                "message": record.message,
                "severity": record.severity.value,
                "component": record.context.component,
                "operation": record.context.operation,
                "timestamp": record.timestamp.isoformat(),
                "resolved": record.resolved
            }
            for record in recent_errors
        ]
    
    def clear_resolved_errors(self) -> int:
        """Clear resolved error records and return count cleared."""
        initial_count = len(self._error_records)
        self._error_records = [r for r in self._error_records if not r.resolved]
        cleared_count = initial_count - len(self._error_records)
        
        if cleared_count > 0:
            self.logger.info(f"Cleared {cleared_count} resolved error records")
        
        return cleared_count