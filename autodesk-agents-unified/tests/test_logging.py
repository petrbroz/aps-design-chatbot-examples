"""
Unit tests for structured logging.
"""

import pytest
import json
import io
import sys
import time
from unittest.mock import patch
from agent_core.logging import StructuredLogger, LogAggregator


class TestStructuredLogger:
    """Test structured logging functionality."""
    
    def test_logger_initialization(self):
        """Test logger initialization."""
        logger = StructuredLogger(log_level="DEBUG", service_name="test-service")
        
        assert logger.service_name == "test-service"
        assert logger.trace_id is None
    
    def test_set_trace_id(self):
        """Test setting trace ID."""
        logger = StructuredLogger()
        
        # Test with custom trace ID
        trace_id = logger.set_trace_id("custom-trace-123")
        assert trace_id == "custom-trace-123"
        assert logger.trace_id == "custom-trace-123"
        
        # Test with auto-generated trace ID
        auto_trace_id = logger.set_trace_id()
        assert auto_trace_id is not None
        assert logger.trace_id == auto_trace_id
    
    def test_get_base_context(self):
        """Test getting base logging context."""
        logger = StructuredLogger(service_name="test-service")
        logger.set_trace_id("test-trace")
        
        context = logger.get_base_context()
        
        assert context["service"] == "test-service"
        assert context["trace_id"] == "test-trace"
        assert "timestamp" in context
    
    def test_info_logging(self):
        """Test info level logging."""
        logger = StructuredLogger(log_level="INFO")
        logger.set_trace_id("test-trace")
        
        # Test that the method executes without error
        # In a real implementation, we would capture the log output
        logger.info("Test message", extra_field="extra_value")
        
        # Verify trace ID is set
        assert logger.trace_id == "test-trace"
    
    def test_error_logging(self):
        """Test error level logging."""
        logger = StructuredLogger(log_level="ERROR")
        
        test_error = ValueError("Test error")
        # Test that the method executes without error
        logger.error("Error occurred", error=test_error, context="test")
        
        # Verify logger is properly configured
        assert logger.service_name == "agent-core"
    
    def test_request_logging(self):
        """Test HTTP request logging."""
        logger = StructuredLogger(log_level="INFO")
        
        # Test that the method executes without error
        logger.log_request("POST", "/api/test", 200, 0.123, user_id="user123")
        
        # Verify logger is properly configured
        assert logger.service_name == "agent-core"
    
    def test_agent_execution_logging(self):
        """Test agent execution logging."""
        logger = StructuredLogger(log_level="INFO")
        
        # Test that the method executes without error
        logger.log_agent_execution(
            "model_properties", 
            "test prompt", 
            1.5, 
            True, 
            response_count=3
        )
        
        # Verify logger is properly configured
        assert logger.service_name == "agent-core"
    
    def test_tool_execution_logging(self):
        """Test tool execution logging."""
        logger = StructuredLogger(log_level="INFO")
        
        # Test that the method executes without error
        logger.log_tool_execution("create_index", 0.5, False, error="Connection failed")
        
        # Verify logger is properly configured
        assert logger.service_name == "agent-core"
    
    def test_context_preservation(self):
        """Test that context is preserved across log calls."""
        logger = StructuredLogger(service_name="test-service")
        logger.set_trace_id("persistent-trace")
        
        # Multiple log calls should maintain the same trace ID
        context1 = logger.get_base_context()
        context2 = logger.get_base_context()
        
        assert context1["trace_id"] == context2["trace_id"]
        assert context1["service"] == context2["service"]


class TestLogAggregator:
    """Test log aggregation functionality."""
    
    def setup_method(self):
        """Setup for each test method."""
        self.aggregator = LogAggregator()
    
    def test_add_log(self):
        """Test adding logs to aggregator."""
        log_entry = {
            "level": "info",
            "message": "Test message",
            "timestamp": "2024-01-01T00:00:00Z"
        }
        
        self.aggregator.add_log(log_entry)
        logs = self.aggregator.get_logs()
        
        assert len(logs) == 1
        assert logs[0] == log_entry
    
    def test_get_logs_with_limit(self):
        """Test getting logs with limit."""
        # Add multiple logs
        for i in range(5):
            self.aggregator.add_log({
                "level": "info",
                "message": f"Message {i}",
                "index": i
            })
        
        # Get limited logs
        logs = self.aggregator.get_logs(limit=3)
        assert len(logs) == 3
        
        # Should get the most recent logs
        assert logs[0]["index"] == 2
        assert logs[1]["index"] == 3
        assert logs[2]["index"] == 4
    
    def test_get_logs_by_trace_id(self):
        """Test filtering logs by trace ID."""
        self.aggregator.add_log({
            "level": "info",
            "message": "Message 1",
            "trace_id": "trace-123"
        })
        self.aggregator.add_log({
            "level": "error",
            "message": "Message 2",
            "trace_id": "trace-456"
        })
        self.aggregator.add_log({
            "level": "info",
            "message": "Message 3",
            "trace_id": "trace-123"
        })
        
        logs = self.aggregator.get_logs_by_trace_id("trace-123")
        assert len(logs) == 2
        assert all(log["trace_id"] == "trace-123" for log in logs)
    
    def test_get_logs_by_level(self):
        """Test filtering logs by level."""
        self.aggregator.add_log({"level": "info", "message": "Info message"})
        self.aggregator.add_log({"level": "error", "message": "Error message"})
        self.aggregator.add_log({"level": "info", "message": "Another info"})
        
        info_logs = self.aggregator.get_logs_by_level("info")
        error_logs = self.aggregator.get_logs_by_level("error")
        
        assert len(info_logs) == 2
        assert len(error_logs) == 1
        assert error_logs[0]["message"] == "Error message"
    
    def test_get_error_logs(self):
        """Test getting error logs specifically."""
        self.aggregator.add_log({"level": "info", "message": "Info message"})
        self.aggregator.add_log({"level": "error", "message": "Error 1"})
        self.aggregator.add_log({"level": "error", "message": "Error 2"})
        
        error_logs = self.aggregator.get_error_logs()
        assert len(error_logs) == 2
        assert all(log["level"] == "error" for log in error_logs)
    
    def test_add_filter(self):
        """Test adding custom filters."""
        self.aggregator.add_log({"level": "info", "duration_ms": 100})
        self.aggregator.add_log({"level": "info", "duration_ms": 500})
        self.aggregator.add_log({"level": "info", "duration_ms": 1000})
        
        # Add filter for slow operations (>200ms)
        self.aggregator.add_filter(lambda log: log.get("duration_ms", 0) > 200)
        
        filtered_logs = self.aggregator.get_logs()
        assert len(filtered_logs) == 2
        assert all(log["duration_ms"] > 200 for log in filtered_logs)
    
    def test_clear_logs(self):
        """Test clearing all logs."""
        self.aggregator.add_log({"level": "info", "message": "Test"})
        assert len(self.aggregator.get_logs()) == 1
        
        self.aggregator.clear_logs()
        assert len(self.aggregator.get_logs()) == 0
    
    def test_max_logs_limit(self):
        """Test that aggregator respects max logs limit."""
        # Set a small max limit for testing
        self.aggregator._max_logs = 5
        
        # Add more logs than the limit
        for i in range(10):
            self.aggregator.add_log({"level": "info", "message": f"Message {i}"})
        
        logs = self.aggregator.get_logs()
        assert len(logs) == 5
        
        # Should keep the most recent logs
        assert logs[0]["message"] == "Message 5"
        assert logs[4]["message"] == "Message 9"


class TestStructuredLoggerAggregation:
    """Test structured logger with aggregation features."""
    
    def setup_method(self):
        """Setup for each test method."""
        # Clear aggregated logs before each test
        StructuredLogger.clear_aggregated_logs()
    
    def test_log_aggregation_enabled(self):
        """Test that logs are aggregated when enabled."""
        logger = StructuredLogger(enable_aggregation=True)
        logger.set_trace_id("test-trace")
        
        logger.info("Test message", extra_field="value")
        
        logs = StructuredLogger.get_aggregated_logs()
        assert len(logs) == 1
        assert logs[0]["message"] == "Test message"
        assert logs[0]["trace_id"] == "test-trace"
        assert logs[0]["extra_field"] == "value"
    
    def test_log_aggregation_disabled(self):
        """Test that logs are not aggregated when disabled."""
        logger = StructuredLogger(enable_aggregation=False)
        logger.info("Test message")
        
        logs = StructuredLogger.get_aggregated_logs()
        assert len(logs) == 0
    
    def test_get_logs_by_trace_id_class_method(self):
        """Test getting logs by trace ID using class method."""
        logger1 = StructuredLogger(enable_aggregation=True)
        logger2 = StructuredLogger(enable_aggregation=True)
        
        logger1.set_trace_id("trace-1")
        logger2.set_trace_id("trace-2")
        
        logger1.info("Message from logger 1")
        logger2.info("Message from logger 2")
        logger1.error("Error from logger 1")
        
        trace1_logs = StructuredLogger.get_logs_by_trace_id("trace-1")
        trace2_logs = StructuredLogger.get_logs_by_trace_id("trace-2")
        
        assert len(trace1_logs) == 2
        assert len(trace2_logs) == 1
        assert all(log["trace_id"] == "trace-1" for log in trace1_logs)
        assert trace2_logs[0]["trace_id"] == "trace-2"
    
    def test_get_error_logs_class_method(self):
        """Test getting error logs using class method."""
        logger = StructuredLogger(enable_aggregation=True)
        
        logger.info("Info message")
        logger.error("Error message 1")
        logger.warning("Warning message")
        logger.error("Error message 2")
        
        error_logs = StructuredLogger.get_error_logs()
        assert len(error_logs) == 2
        assert all(log["level"] == "error" for log in error_logs)
    
    def test_log_types_in_aggregation(self):
        """Test that different log types are properly tagged."""
        logger = StructuredLogger(enable_aggregation=True)
        
        logger.log_request("POST", "/api/test", 200, 0.5)
        logger.log_agent_execution("test_agent", "test prompt", 1.0, True)
        logger.log_tool_execution("test_tool", 0.3, False)
        
        logs = StructuredLogger.get_aggregated_logs()
        assert len(logs) == 3
        
        log_types = [log["log_type"] for log in logs]
        assert "http_request" in log_types
        assert "agent_execution" in log_types
        assert "tool_execution" in log_types
    
    def test_add_custom_filter(self):
        """Test adding custom filters to logger aggregation."""
        logger = StructuredLogger(enable_aggregation=True)
        
        logger.log_request("GET", "/fast", 200, 0.1)
        logger.log_request("POST", "/slow", 200, 2.0)
        logger.log_agent_execution("agent", "prompt", 0.5, True)
        
        # Add filter for slow operations (>1000ms)
        StructuredLogger.add_log_filter(lambda log: log.get("duration_ms", 0) > 1000)
        
        filtered_logs = StructuredLogger.get_aggregated_logs()
        assert len(filtered_logs) == 1
        assert filtered_logs[0]["path"] == "/slow"