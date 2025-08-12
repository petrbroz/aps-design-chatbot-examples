"""
Unit tests for AgentCore data models.
"""

import pytest
from datetime import datetime
from unittest.mock import Mock

from agent_core.models import (
    AgentRequest, AgentResponse, ErrorResponse, ErrorCode, 
    ToolResult, AgentMetrics
)
from agent_core.auth import AuthContext


class TestAgentRequest:
    """Test cases for AgentRequest model."""
    
    def test_valid_request_creation(self):
        """Test creating a valid AgentRequest."""
        auth_context = AuthContext(access_token="test_token")
        request = AgentRequest(
            agent_type="test_agent",
            prompt="Test prompt",
            context={"key": "value"},
            authentication=auth_context,
            metadata={"meta": "data"},
            request_id="req_123"
        )
        
        assert request.agent_type == "test_agent"
        assert request.prompt == "Test prompt"
        assert request.context == {"key": "value"}
        assert request.authentication == auth_context
        assert request.metadata == {"meta": "data"}
        assert request.request_id == "req_123"
        assert isinstance(request.timestamp, datetime)
    
    def test_minimal_request_creation(self):
        """Test creating a minimal AgentRequest with required fields only."""
        request = AgentRequest(
            agent_type="test_agent",
            prompt="Test prompt"
        )
        
        assert request.agent_type == "test_agent"
        assert request.prompt == "Test prompt"
        assert request.context == {}
        assert request.authentication is None
        assert request.metadata == {}
        assert request.request_id is None
        assert isinstance(request.timestamp, datetime)
    
    def test_empty_agent_type_validation(self):
        """Test validation fails for empty agent_type."""
        with pytest.raises(ValueError, match="agent_type is required"):
            AgentRequest(agent_type="", prompt="Test prompt")
    
    def test_empty_prompt_validation(self):
        """Test validation fails for empty prompt."""
        with pytest.raises(ValueError, match="prompt is required"):
            AgentRequest(agent_type="test_agent", prompt="")


class TestAgentResponse:
    """Test cases for AgentResponse model."""
    
    def test_valid_response_creation(self):
        """Test creating a valid AgentResponse."""
        response = AgentResponse(
            responses=["Response 1", "Response 2"],
            metadata={"key": "value"},
            execution_time=1.5,
            agent_type="test_agent",
            request_id="req_123",
            success=True
        )
        
        assert response.responses == ["Response 1", "Response 2"]
        assert response.metadata == {"key": "value"}
        assert response.execution_time == 1.5
        assert response.agent_type == "test_agent"
        assert response.request_id == "req_123"
        assert response.success is True
        assert isinstance(response.timestamp, datetime)
    
    def test_minimal_response_creation(self):
        """Test creating a minimal AgentResponse."""
        response = AgentResponse(responses=["Test response"])
        
        assert response.responses == ["Test response"]
        assert response.metadata == {}
        assert response.execution_time == 0.0
        assert response.agent_type == ""
        assert response.request_id is None
        assert response.success is True
        assert isinstance(response.timestamp, datetime)
    
    def test_invalid_responses_type(self):
        """Test validation fails for non-list responses."""
        with pytest.raises(ValueError, match="responses must be a list"):
            AgentResponse(responses="not a list")


class TestErrorResponse:
    """Test cases for ErrorResponse model."""
    
    def test_valid_error_response_creation(self):
        """Test creating a valid ErrorResponse."""
        error_response = ErrorResponse(
            error_code="TEST_ERROR",
            message="Test error message",
            details={"key": "value"},
            trace_id="trace_123",
            request_id="req_123"
        )
        
        assert error_response.error_code == "TEST_ERROR"
        assert error_response.message == "Test error message"
        assert error_response.details == {"key": "value"}
        assert error_response.trace_id == "trace_123"
        assert error_response.request_id == "req_123"
        assert isinstance(error_response.timestamp, datetime)
    
    def test_minimal_error_response_creation(self):
        """Test creating a minimal ErrorResponse."""
        error_response = ErrorResponse(
            error_code="TEST_ERROR",
            message="Test error message"
        )
        
        assert error_response.error_code == "TEST_ERROR"
        assert error_response.message == "Test error message"
        assert error_response.details == {}
        assert error_response.trace_id is None
        assert error_response.request_id is None
        assert isinstance(error_response.timestamp, datetime)
    
    def test_empty_error_code_validation(self):
        """Test validation fails for empty error_code."""
        with pytest.raises(ValueError, match="error_code is required"):
            ErrorResponse(error_code="", message="Test message")
    
    def test_empty_message_validation(self):
        """Test validation fails for empty message."""
        with pytest.raises(ValueError, match="message is required"):
            ErrorResponse(error_code="TEST_ERROR", message="")
    
    def test_from_exception_method(self):
        """Test creating ErrorResponse from exception."""
        test_exception = ValueError("Test exception message")
        error_response = ErrorResponse.from_exception(
            test_exception,
            ErrorCode.VALIDATION_ERROR,
            trace_id="trace_123",
            request_id="req_123"
        )
        
        assert error_response.error_code == ErrorCode.VALIDATION_ERROR.value
        assert error_response.message == "Test exception message"
        assert error_response.details["exception_type"] == "ValueError"
        assert error_response.details["exception_args"] == ("Test exception message",)
        assert error_response.trace_id == "trace_123"
        assert error_response.request_id == "req_123"
    
    def test_to_dict_method(self):
        """Test converting ErrorResponse to dictionary."""
        error_response = ErrorResponse(
            error_code="TEST_ERROR",
            message="Test message",
            details={"key": "value"},
            trace_id="trace_123",
            request_id="req_123"
        )
        
        result_dict = error_response.to_dict()
        
        assert result_dict["error_code"] == "TEST_ERROR"
        assert result_dict["message"] == "Test message"
        assert result_dict["details"] == {"key": "value"}
        assert result_dict["trace_id"] == "trace_123"
        assert result_dict["request_id"] == "req_123"
        assert "timestamp" in result_dict


class TestToolResult:
    """Test cases for ToolResult model."""
    
    def test_successful_tool_result(self):
        """Test creating a successful ToolResult."""
        result = ToolResult(
            tool_name="test_tool",
            success=True,
            result={"data": "value"},
            execution_time=0.5,
            metadata={"meta": "data"}
        )
        
        assert result.tool_name == "test_tool"
        assert result.success is True
        assert result.result == {"data": "value"}
        assert result.error is None
        assert result.execution_time == 0.5
        assert result.metadata == {"meta": "data"}
    
    def test_failed_tool_result(self):
        """Test creating a failed ToolResult."""
        result = ToolResult(
            tool_name="test_tool",
            success=False,
            error="Tool execution failed",
            execution_time=0.2
        )
        
        assert result.tool_name == "test_tool"
        assert result.success is False
        assert result.result is None
        assert result.error == "Tool execution failed"
        assert result.execution_time == 0.2
        assert result.metadata == {}
    
    def test_empty_tool_name_validation(self):
        """Test validation fails for empty tool_name."""
        with pytest.raises(ValueError, match="tool_name is required"):
            ToolResult(tool_name="", success=True)
    
    def test_failed_without_error_validation(self):
        """Test validation fails for failed result without error message."""
        with pytest.raises(ValueError, match="error message is required when success is False"):
            ToolResult(tool_name="test_tool", success=False)


class TestAgentMetrics:
    """Test cases for AgentMetrics model."""
    
    def test_initial_metrics(self):
        """Test initial AgentMetrics state."""
        metrics = AgentMetrics(agent_type="test_agent")
        
        assert metrics.agent_type == "test_agent"
        assert metrics.total_requests == 0
        assert metrics.successful_requests == 0
        assert metrics.failed_requests == 0
        assert metrics.average_response_time == 0.0
        assert metrics.last_request_time is None
        assert metrics.uptime_seconds == 0.0
        assert metrics.success_rate == 0.0
    
    def test_success_rate_calculation(self):
        """Test success rate calculation."""
        metrics = AgentMetrics(agent_type="test_agent")
        
        # No requests
        assert metrics.success_rate == 0.0
        
        # All successful
        metrics.total_requests = 10
        metrics.successful_requests = 10
        assert metrics.success_rate == 100.0
        
        # Partial success
        metrics.successful_requests = 7
        metrics.failed_requests = 3
        assert metrics.success_rate == 70.0
        
        # All failed
        metrics.successful_requests = 0
        metrics.failed_requests = 10
        assert metrics.success_rate == 0.0
    
    def test_update_request_metrics_success(self):
        """Test updating metrics with successful request."""
        metrics = AgentMetrics(agent_type="test_agent")
        
        metrics.update_request_metrics(success=True, response_time=1.5)
        
        assert metrics.total_requests == 1
        assert metrics.successful_requests == 1
        assert metrics.failed_requests == 0
        assert metrics.average_response_time == 1.5
        assert isinstance(metrics.last_request_time, datetime)
    
    def test_update_request_metrics_failure(self):
        """Test updating metrics with failed request."""
        metrics = AgentMetrics(agent_type="test_agent")
        
        metrics.update_request_metrics(success=False, response_time=0.8)
        
        assert metrics.total_requests == 1
        assert metrics.successful_requests == 0
        assert metrics.failed_requests == 1
        assert metrics.average_response_time == 0.8
        assert isinstance(metrics.last_request_time, datetime)
    
    def test_update_request_metrics_rolling_average(self):
        """Test rolling average calculation with multiple requests."""
        metrics = AgentMetrics(agent_type="test_agent")
        
        # First request
        metrics.update_request_metrics(success=True, response_time=1.0)
        assert metrics.average_response_time == 1.0
        
        # Second request
        metrics.update_request_metrics(success=True, response_time=2.0)
        assert metrics.average_response_time == 1.5
        
        # Third request
        metrics.update_request_metrics(success=False, response_time=3.0)
        assert metrics.average_response_time == 2.0
        
        assert metrics.total_requests == 3
        assert metrics.successful_requests == 2
        assert metrics.failed_requests == 1


class TestErrorCode:
    """Test cases for ErrorCode enum."""
    
    def test_error_code_values(self):
        """Test ErrorCode enum values."""
        assert ErrorCode.VALIDATION_ERROR.value == "VALIDATION_ERROR"
        assert ErrorCode.AUTHENTICATION_ERROR.value == "AUTHENTICATION_ERROR"
        assert ErrorCode.AUTHORIZATION_ERROR.value == "AUTHORIZATION_ERROR"
        assert ErrorCode.AGENT_NOT_FOUND.value == "AGENT_NOT_FOUND"
        assert ErrorCode.TOOL_ERROR.value == "TOOL_ERROR"
        assert ErrorCode.EXTERNAL_SERVICE_ERROR.value == "EXTERNAL_SERVICE_ERROR"
        assert ErrorCode.CONFIGURATION_ERROR.value == "CONFIGURATION_ERROR"
        assert ErrorCode.INTERNAL_ERROR.value == "INTERNAL_ERROR"
        assert ErrorCode.TIMEOUT_ERROR.value == "TIMEOUT_ERROR"
        assert ErrorCode.RATE_LIMIT_ERROR.value == "RATE_LIMIT_ERROR"