"""
Structured logging system for AgentCore framework.
"""

import structlog
import logging
import sys
from typing import Any, Dict, Optional, List, Callable
from datetime import datetime
import uuid
import threading
from collections import defaultdict
import time


class LogAggregator:
    """Log aggregation and filtering system."""
    
    def __init__(self):
        self._logs: List[Dict[str, Any]] = []
        self._filters: List[Callable[[Dict[str, Any]], bool]] = []
        self._lock = threading.Lock()
        self._max_logs = 10000  # Maximum logs to keep in memory
    
    def add_log(self, log_entry: Dict[str, Any]) -> None:
        """Add a log entry to the aggregator."""
        with self._lock:
            self._logs.append(log_entry)
            # Keep only the most recent logs
            if len(self._logs) > self._max_logs:
                self._logs = self._logs[-self._max_logs:]
    
    def add_filter(self, filter_func: Callable[[Dict[str, Any]], bool]) -> None:
        """Add a filter function for log entries."""
        self._filters.append(filter_func)
    
    def get_logs(self, limit: Optional[int] = None, **filters) -> List[Dict[str, Any]]:
        """Get logs with optional filtering."""
        with self._lock:
            filtered_logs = self._logs.copy()
        
        # Apply custom filters
        for filter_func in self._filters:
            filtered_logs = [log for log in filtered_logs if filter_func(log)]
        
        # Apply keyword filters
        for key, value in filters.items():
            filtered_logs = [log for log in filtered_logs if log.get(key) == value]
        
        # Apply limit
        if limit:
            filtered_logs = filtered_logs[-limit:]
        
        return filtered_logs
    
    def get_logs_by_trace_id(self, trace_id: str) -> List[Dict[str, Any]]:
        """Get all logs for a specific trace ID."""
        return self.get_logs(trace_id=trace_id)
    
    def get_logs_by_level(self, level: str) -> List[Dict[str, Any]]:
        """Get logs by log level."""
        return self.get_logs(level=level)
    
    def get_error_logs(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get error level logs."""
        return self.get_logs_by_level("error")[-limit:] if limit else self.get_logs_by_level("error")
    
    def clear_logs(self) -> None:
        """Clear all stored logs."""
        with self._lock:
            self._logs.clear()


class StructuredLogger:
    """Structured logger with JSON formatting and contextual information."""
    
    _aggregator = LogAggregator()  # Shared aggregator across all logger instances
    
    def __init__(self, log_level: str = "INFO", service_name: str = "agent-core", enable_aggregation: bool = True):
        self.service_name = service_name
        self.trace_id: Optional[str] = None
        self.enable_aggregation = enable_aggregation
        
        # Configure structlog
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.UnicodeDecoder(),
                structlog.processors.JSONRenderer()
            ],
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
        
        # Configure standard logging
        logging.basicConfig(
            format="%(message)s",
            stream=sys.stdout,
            level=getattr(logging, log_level.upper())
        )
        
        self.logger = structlog.get_logger(service_name)
    
    def set_trace_id(self, trace_id: str = None) -> str:
        """Set trace ID for request correlation."""
        self.trace_id = trace_id or str(uuid.uuid4())
        return self.trace_id
    
    def get_base_context(self) -> Dict[str, Any]:
        """Get base logging context."""
        context = {
            "service": self.service_name,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        if self.trace_id:
            context["trace_id"] = self.trace_id
        
        return context
    
    def _log_with_aggregation(self, level: str, message: str, context: Dict[str, Any]) -> None:
        """Log message and optionally add to aggregator."""
        # Add to aggregator if enabled
        if self.enable_aggregation:
            log_entry = {
                "level": level,
                "message": message,
                **context
            }
            self._aggregator.add_log(log_entry)
        
        # Log using structlog
        getattr(self.logger, level)(message, **context)
    
    def info(self, message: str, **kwargs) -> None:
        """Log info message with context."""
        context = self.get_base_context()
        context.update(kwargs)
        self._log_with_aggregation("info", message, context)
    
    def error(self, message: str, error: Exception = None, **kwargs) -> None:
        """Log error message with context."""
        context = self.get_base_context()
        context.update(kwargs)
        
        if error:
            context["error_type"] = type(error).__name__
            context["error_message"] = str(error)
        
        self._log_with_aggregation("error", message, context)
    
    def warning(self, message: str, **kwargs) -> None:
        """Log warning message with context."""
        context = self.get_base_context()
        context.update(kwargs)
        self._log_with_aggregation("warning", message, context)
    
    def debug(self, message: str, **kwargs) -> None:
        """Log debug message with context."""
        context = self.get_base_context()
        context.update(kwargs)
        self._log_with_aggregation("debug", message, context)
    
    def log_request(self, method: str, path: str, status_code: int, duration: float, **kwargs) -> None:
        """Log HTTP request with timing information."""
        context = self.get_base_context()
        context.update({
            "method": method,
            "path": path,
            "status_code": status_code,
            "duration_ms": round(duration * 1000, 2),
            "log_type": "http_request",
            **kwargs
        })
        self._log_with_aggregation("info", "HTTP request processed", context)
    
    def log_agent_execution(self, agent_type: str, prompt: str, duration: float, success: bool, **kwargs) -> None:
        """Log agent execution with performance metrics."""
        context = self.get_base_context()
        context.update({
            "agent_type": agent_type,
            "prompt_length": len(prompt),
            "duration_ms": round(duration * 1000, 2),
            "success": success,
            "log_type": "agent_execution",
            **kwargs
        })
        self._log_with_aggregation("info", "Agent execution completed", context)
    
    def log_tool_execution(self, tool_name: str, duration: float, success: bool, **kwargs) -> None:
        """Log tool execution with performance metrics."""
        context = self.get_base_context()
        context.update({
            "tool_name": tool_name,
            "duration_ms": round(duration * 1000, 2),
            "success": success,
            "log_type": "tool_execution",
            **kwargs
        })
        self._log_with_aggregation("info", "Tool execution completed", context)
    
    @classmethod
    def get_aggregated_logs(cls, limit: Optional[int] = None, **filters) -> List[Dict[str, Any]]:
        """Get aggregated logs with optional filtering."""
        return cls._aggregator.get_logs(limit=limit, **filters)
    
    @classmethod
    def get_logs_by_trace_id(cls, trace_id: str) -> List[Dict[str, Any]]:
        """Get all logs for a specific trace ID."""
        return cls._aggregator.get_logs_by_trace_id(trace_id)
    
    @classmethod
    def get_error_logs(cls, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get error level logs."""
        return cls._aggregator.get_error_logs(limit)
    
    @classmethod
    def add_log_filter(cls, filter_func: Callable[[Dict[str, Any]], bool]) -> None:
        """Add a custom filter function for log aggregation."""
        cls._aggregator.add_filter(filter_func)
    
    @classmethod
    def clear_aggregated_logs(cls) -> None:
        """Clear all aggregated logs."""
        cls._aggregator.clear_logs()


def get_logger(name: str) -> StructuredLogger:
    """
    Get a structured logger instance.
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        StructuredLogger instance
    """
    return StructuredLogger(service_name=name)