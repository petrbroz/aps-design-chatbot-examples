"""
Structured Logging for AgentCore

Provides JSON-structured logging with contextual information,
trace IDs, and integration with monitoring systems.
"""

import json
import logging
import uuid
from typing import Dict, Any, Optional
from datetime import datetime
import contextvars
from pathlib import Path


# Context variable for trace ID
trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar('trace_id')


class StructuredFormatter(logging.Formatter):
    """Custom formatter for structured JSON logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as structured JSON."""
        
        # Base log structure
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        
        # Add trace ID if available
        try:
            trace_id = trace_id_var.get()
            log_entry["trace_id"] = trace_id
        except LookupError:
            pass
        
        # Add extra fields from record
        if hasattr(record, 'extra') and record.extra:
            log_entry.update(record.extra)
        
        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": self.formatException(record.exc_info)
            }
        
        return json.dumps(log_entry, default=str)


class StructuredLogger:
    """
    Structured logger with contextual information and trace IDs.
    
    Provides consistent logging across all AgentCore components
    with JSON formatting and contextual metadata.
    """
    
    def __init__(self, name: str = "agentcore", level: str = "INFO", 
                 service_name: str = "agentcore", log_file: Optional[Path] = None):
        """Initialize structured logger."""
        self.service_name = service_name
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, level.upper()))
        
        # Remove existing handlers to avoid duplicates
        self.logger.handlers.clear()
        
        # Console handler with structured formatting
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(StructuredFormatter())
        self.logger.addHandler(console_handler)
        
        # File handler if specified
        if log_file:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(StructuredFormatter())
            self.logger.addHandler(file_handler)
        
        # Prevent propagation to root logger
        self.logger.propagate = False
    
    def _log_with_context(self, level: int, message: str, extra: Optional[Dict[str, Any]] = None):
        """Log message with contextual information."""
        log_extra = {
            "service": self.service_name,
            **(extra or {})
        }
        
        self.logger.log(level, message, extra=log_extra)
    
    def debug(self, message: str, extra: Optional[Dict[str, Any]] = None):
        """Log debug message."""
        self._log_with_context(logging.DEBUG, message, extra)
    
    def info(self, message: str, extra: Optional[Dict[str, Any]] = None):
        """Log info message."""
        self._log_with_context(logging.INFO, message, extra)
    
    def warning(self, message: str, extra: Optional[Dict[str, Any]] = None):
        """Log warning message."""
        self._log_with_context(logging.WARNING, message, extra)
    
    def error(self, message: str, extra: Optional[Dict[str, Any]] = None):
        """Log error message."""
        self._log_with_context(logging.ERROR, message, extra)
    
    def critical(self, message: str, extra: Optional[Dict[str, Any]] = None):
        """Log critical message."""
        self._log_with_context(logging.CRITICAL, message, extra)
    
    def log_request(self, method: str, url: str, status_code: int, 
                   duration: float, extra: Optional[Dict[str, Any]] = None):
        """Log HTTP request with timing information."""
        request_extra = {
            "request": {
                "method": method,
                "url": url,
                "status_code": status_code,
                "duration_ms": round(duration * 1000, 2)
            },
            **(extra or {})
        }
        
        level = logging.INFO
        if status_code >= 500:
            level = logging.ERROR
        elif status_code >= 400:
            level = logging.WARNING
        
        self._log_with_context(level, f"{method} {url} - {status_code}", request_extra)
    
    def log_agent_execution(self, agent_type: str, prompt: str, 
                          execution_time: float, success: bool,
                          extra: Optional[Dict[str, Any]] = None):
        """Log agent execution with performance metrics."""
        agent_extra = {
            "agent": {
                "type": agent_type,
                "prompt_length": len(prompt),
                "execution_time_ms": round(execution_time * 1000, 2),
                "success": success
            },
            **(extra or {})
        }
        
        level = logging.INFO if success else logging.ERROR
        message = f"Agent {agent_type} executed {'successfully' if success else 'with error'}"
        
        self._log_with_context(level, message, agent_extra)
    
    def log_api_call(self, service: str, endpoint: str, method: str,
                    status_code: int, duration: float, 
                    extra: Optional[Dict[str, Any]] = None):
        """Log external API call."""
        api_extra = {
            "api_call": {
                "service": service,
                "endpoint": endpoint,
                "method": method,
                "status_code": status_code,
                "duration_ms": round(duration * 1000, 2)
            },
            **(extra or {})
        }
        
        level = logging.INFO
        if status_code >= 500:
            level = logging.ERROR
        elif status_code >= 400:
            level = logging.WARNING
        
        message = f"API call to {service} {endpoint} - {status_code}"
        self._log_with_context(level, message, api_extra)


class TraceContext:
    """Context manager for trace ID management."""
    
    def __init__(self, trace_id: Optional[str] = None):
        """Initialize trace context."""
        self.trace_id = trace_id or str(uuid.uuid4())
        self.token = None
    
    def __enter__(self):
        """Enter trace context."""
        self.token = trace_id_var.set(self.trace_id)
        return self.trace_id
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit trace context."""
        if self.token:
            trace_id_var.reset(self.token)


def get_trace_id() -> Optional[str]:
    """Get current trace ID."""
    try:
        return trace_id_var.get()
    except LookupError:
        return None


def set_trace_id(trace_id: str) -> None:
    """Set trace ID for current context."""
    trace_id_var.set(trace_id)