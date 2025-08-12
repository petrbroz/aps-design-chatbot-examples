"""
Unit tests for ErrorHandler class.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock
from datetime import datetime, timedelta

from agent_core.error_handler import (
    ErrorHandler, RetryPolicy, RetryStrategy, AlertSeverity, ErrorAlert
)
from agent_core.models import AgentRequest, AgentResponse, ErrorResponse, ErrorCode
from agent_core.auth import AuthContext
from agent_core.logging import StructuredLogger


class TestErrorHandler:
    """Test cases for ErrorHandler class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_logger = Mock(spec=StructuredLogger)
        self.error_handler = ErrorHandler(self.mock_logger)
    
    def test_error_handler_initialization(self):
        """Test ErrorHandler initialization."""
        assert self.error_handler.logger == self.mock_logger
        assert len(self.error_handler._error_handlers) == 0
        assert len(self.error_handler._retry_policies) == 0
    
    def test_register_error_handler(self):
        """Test registering custom error handler."""
        def custom_handler(error, context):
            return ErrorResponse(
                error_code="CUSTOM_ERROR",
                message=f"Custom: {str(error)}"
            )
        
        self.error_handler.register_error_handler(ValueError, custom_handler)
        
        assert ValueError in self.error_handler._error_handlers
        assert self.error_handler._error_handlers[ValueError] == custom_handler
        self.mock_logger.debug.assert_called_once()
    
    def test_set_retry_policy(self):
        """Test setting retry policy."""
        policy = RetryPolicy(
            max_retries=5,
            strategy=RetryStrategy.EXPONENTIAL_BACKOFF,
            base_delay=1.0,
            backoff_factor=2.0,
            retry_exceptions=[ConnectionError, TimeoutError]
        )
        
        self.error_handler.set_retry_policy("test_operation", policy)
        
        stored_policy = self.error_handler._retry_policies["test_operation"]
        assert stored_policy.max_retries == 5
        assert stored_policy.strategy == RetryStrategy.EXPONENTIAL_BACKOFF
        assert stored_policy.backoff_factor == 2.0
        assert stored_policy.retry_exceptions == [ConnectionError, TimeoutError]
        self.mock_logger.debug.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_handle_agent_error_basic(self):
        """Test basic agent error handling."""
        auth_context = AuthContext(access_token="test_token")
        request = AgentRequest(
            agent_type="test_agent",
            prompt="Test prompt",
            authentication=auth_context,
            request_id="req_123"
        )
        
        test_error = ValueError("Test error message")
        response = await self.error_handler.handle_agent_error(test_error, request)
        
        assert isinstance(response, AgentResponse)
        assert response.success is False
        assert response.agent_type == "test_agent"
        assert response.request_id == "req_123"
        assert "Error: Test error message" in response.responses
        assert "error" in response.metadata
        assert "trace_id" in response.metadata
        
        # Verify logging was called
        self.mock_logger.error.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_handle_agent_error_with_custom_handler(self):
        """Test agent error handling with custom error handler."""
        def custom_handler(error, context):
            return ErrorResponse(
                error_code="CUSTOM_ERROR",
                message=f"Custom: {str(error)}",
                trace_id=context["trace_id"]
            )
        
        self.error_handler.register_error_handler(ValueError, custom_handler)
        
        auth_context = AuthContext(access_token="test_token")
        request = AgentRequest(
            agent_type="test_agent",
            prompt="Test prompt",
            authentication=auth_context,
            request_id="req_123"
        )
        
        test_error = ValueError("Test error message")
        response = await self.error_handler.handle_agent_error(test_error, request)
        
        assert response.success is False
        assert "Error: Custom: Test error message" in response.responses
        error_data = response.metadata["error"]
        assert error_data["error_code"] == "CUSTOM_ERROR"
    
    @pytest.mark.asyncio
    async def test_handle_agent_error_custom_handler_fails(self):
        """Test agent error handling when custom handler fails."""
        def failing_handler(error, context):
            raise RuntimeError("Handler failed")
        
        self.error_handler.register_error_handler(ValueError, failing_handler)
        
        auth_context = AuthContext(access_token="test_token")
        request = AgentRequest(
            agent_type="test_agent",
            prompt="Test prompt",
            authentication=auth_context
        )
        
        test_error = ValueError("Test error message")
        response = await self.error_handler.handle_agent_error(test_error, request)
        
        # Should fall back to default error handling
        assert response.success is False
        assert "Error: Test error message" in response.responses
        
        # Should log both the original error and handler error
        assert self.mock_logger.error.call_count == 2
    
    @pytest.mark.asyncio
    async def test_handle_tool_error(self):
        """Test tool error handling."""
        test_error = RuntimeError("Tool execution failed")
        context = {"param1": "value1", "param2": "value2"}
        
        error_response = await self.error_handler.handle_tool_error(
            test_error, "test_tool", context
        )
        
        assert isinstance(error_response, ErrorResponse)
        assert error_response.error_code == ErrorCode.INTERNAL_ERROR.value
        assert "Tool 'test_tool' execution failed" in error_response.message
        assert error_response.details["tool_name"] == "test_tool"
        assert error_response.details["context"] == context
        assert error_response.details["exception_type"] == "RuntimeError"
        assert error_response.trace_id is not None
        
        self.mock_logger.error.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_handle_validation_error(self):
        """Test validation error handling."""
        test_error = ValueError("Invalid field value")
        
        error_response = await self.error_handler.handle_validation_error(
            test_error, "test_field", "invalid_value"
        )
        
        assert isinstance(error_response, ErrorResponse)
        assert error_response.error_code == ErrorCode.VALIDATION_ERROR.value
        assert error_response.message == "Invalid field value"
        assert error_response.details["field_name"] == "test_field"
        assert error_response.details["invalid_value"] == "invalid_value"
        assert error_response.trace_id is not None
        
        self.mock_logger.warning.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_handle_authentication_error(self):
        """Test authentication error handling."""
        test_error = ValueError("Invalid token")
        auth_context = {"token": "invalid_token", "user_id": "user123"}
        
        error_response = await self.error_handler.handle_authentication_error(
            test_error, auth_context
        )
        
        assert isinstance(error_response, ErrorResponse)
        assert error_response.error_code == ErrorCode.AUTHENTICATION_ERROR.value
        assert error_response.message == "Invalid token"
        assert error_response.details["auth_context"] == auth_context
        assert error_response.trace_id is not None
        
        self.mock_logger.warning.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_handle_authorization_error(self):
        """Test authorization error handling."""
        test_error = ValueError("Unauthorized access")
        
        error_response = await self.error_handler.handle_authentication_error(test_error)
        
        assert isinstance(error_response, ErrorResponse)
        assert error_response.error_code == ErrorCode.AUTHORIZATION_ERROR.value
        assert error_response.message == "Unauthorized access"
    
    def test_determine_error_code_authentication(self):
        """Test error code determination for authentication errors."""
        auth_error = ValueError("Invalid token")
        error_code = self.error_handler._determine_error_code(auth_error)
        assert error_code == ErrorCode.AUTHENTICATION_ERROR
        
        unauth_error = ValueError("Unauthorized access")
        error_code = self.error_handler._determine_error_code(unauth_error)
        assert error_code == ErrorCode.AUTHENTICATION_ERROR
    
    def test_determine_error_code_validation(self):
        """Test error code determination for validation errors."""
        validation_error = ValueError("Invalid value")
        error_code = self.error_handler._determine_error_code(validation_error)
        assert error_code == ErrorCode.VALIDATION_ERROR
    
    def test_determine_error_code_external_service(self):
        """Test error code determination for external service errors."""
        connection_error = ValueError("Connection failed")
        error_code = self.error_handler._determine_error_code(connection_error)
        assert error_code == ErrorCode.EXTERNAL_SERVICE_ERROR
        
        timeout_error = ValueError("Request timeout")
        error_code = self.error_handler._determine_error_code(timeout_error)
        assert error_code == ErrorCode.EXTERNAL_SERVICE_ERROR
    
    def test_determine_error_code_configuration(self):
        """Test error code determination for configuration errors."""
        config_error = ValueError("Invalid configuration")
        error_code = self.error_handler._determine_error_code(config_error)
        assert error_code == ErrorCode.CONFIGURATION_ERROR
    
    def test_determine_error_code_timeout(self):
        """Test error code determination for timeout errors."""
        timeout_error = TimeoutError("Operation timed out")
        error_code = self.error_handler._determine_error_code(timeout_error)
        assert error_code == ErrorCode.TIMEOUT_ERROR
    
    def test_determine_error_code_rate_limit(self):
        """Test error code determination for rate limit errors."""
        rate_limit_error = ValueError("Rate limit exceeded")
        error_code = self.error_handler._determine_error_code(rate_limit_error)
        assert error_code == ErrorCode.RATE_LIMIT_ERROR
    
    def test_determine_error_code_default(self):
        """Test error code determination for unknown errors."""
        unknown_error = RuntimeError("Unknown error")
        error_code = self.error_handler._determine_error_code(unknown_error)
        assert error_code == ErrorCode.INTERNAL_ERROR
    
    def test_is_recoverable_error_by_type(self):
        """Test recoverable error detection by exception type."""
        connection_error = ConnectionError("Connection failed")
        assert self.error_handler._is_recoverable_error(connection_error)
        
        timeout_error = TimeoutError("Request timed out")
        assert self.error_handler._is_recoverable_error(timeout_error)
        
        value_error = ValueError("Invalid value")
        assert not self.error_handler._is_recoverable_error(value_error)
    
    def test_is_recoverable_error_by_message(self):
        """Test recoverable error detection by error message."""
        recoverable_error = RuntimeError("Connection timeout occurred")
        assert self.error_handler._is_recoverable_error(recoverable_error)
        
        recoverable_error2 = RuntimeError("Service unavailable")
        assert self.error_handler._is_recoverable_error(recoverable_error2)
        
        non_recoverable_error = RuntimeError("Invalid input data")
        assert not self.error_handler._is_recoverable_error(non_recoverable_error)
    
    @pytest.mark.asyncio
    async def test_create_system_error(self):
        """Test creating system error response."""
        details = {"component": "database", "operation": "connect"}
        
        error_response = await self.error_handler.create_system_error(
            "System initialization failed", details
        )
        
        assert isinstance(error_response, ErrorResponse)
        assert error_response.error_code == ErrorCode.INTERNAL_ERROR.value
        assert error_response.message == "System initialization failed"
        assert error_response.details == details
        assert error_response.trace_id is not None
        
        self.mock_logger.error.assert_called_once()
    
    def test_get_error_statistics(self):
        """Test getting error statistics."""
        stats = self.error_handler.get_error_statistics()
        
        assert isinstance(stats, dict)
        assert "total_errors" in stats
        assert "errors_by_type" in stats
        assert "retry_attempts" in stats
        assert "successful_recoveries" in stats
        assert "failed_recoveries" in stats
        assert "error_rate_per_minute" in stats
        assert "circuit_breakers" in stats
    
    @pytest.mark.asyncio
    async def test_execute_with_retry_success_first_attempt(self):
        """Test successful operation on first attempt."""
        async def successful_operation():
            return "success"
        
        result = await self.error_handler.execute_with_retry("test_op", successful_operation)
        assert result == "success"
    
    @pytest.mark.asyncio
    async def test_execute_with_retry_success_after_retries(self):
        """Test successful operation after retries."""
        call_count = 0
        
        async def failing_then_success():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Connection failed")
            return "success"
        
        policy = RetryPolicy(max_retries=3, base_delay=0.01, retry_exceptions=[ConnectionError])
        self.error_handler.set_retry_policy("test_op", policy)
        
        result = await self.error_handler.execute_with_retry("test_op", failing_then_success)
        assert result == "success"
        assert call_count == 3
        assert self.error_handler._metrics.successful_recoveries == 1
    
    @pytest.mark.asyncio
    async def test_execute_with_retry_all_attempts_fail(self):
        """Test operation failing all retry attempts."""
        async def always_fails():
            raise ConnectionError("Always fails")
        
        policy = RetryPolicy(max_retries=2, base_delay=0.01, retry_exceptions=[ConnectionError])
        self.error_handler.set_retry_policy("test_op", policy)
        
        with pytest.raises(ConnectionError):
            await self.error_handler.execute_with_retry("test_op", always_fails)
        
        assert self.error_handler._metrics.failed_recoveries == 1
        assert self.error_handler._metrics.retry_attempts == 2
    
    @pytest.mark.asyncio
    async def test_execute_with_retry_non_retryable_exception(self):
        """Test operation with non-retryable exception."""
        async def fails_with_value_error():
            raise ValueError("Not retryable")
        
        policy = RetryPolicy(max_retries=3, base_delay=0.01, retry_exceptions=[ConnectionError])
        self.error_handler.set_retry_policy("test_op", policy)
        
        with pytest.raises(ValueError):
            await self.error_handler.execute_with_retry("test_op", fails_with_value_error)
        
        # Should not retry for non-retryable exceptions
        assert self.error_handler._metrics.retry_attempts == 0
    
    def test_calculate_retry_delay_exponential(self):
        """Test exponential backoff delay calculation."""
        policy = RetryPolicy(
            strategy=RetryStrategy.EXPONENTIAL_BACKOFF,
            base_delay=1.0,
            backoff_factor=2.0,
            jitter=False
        )
        
        delay0 = self.error_handler._calculate_retry_delay(policy, 0)
        delay1 = self.error_handler._calculate_retry_delay(policy, 1)
        delay2 = self.error_handler._calculate_retry_delay(policy, 2)
        
        assert delay0 == 1.0
        assert delay1 == 2.0
        assert delay2 == 4.0
    
    def test_calculate_retry_delay_linear(self):
        """Test linear backoff delay calculation."""
        policy = RetryPolicy(
            strategy=RetryStrategy.LINEAR_BACKOFF,
            base_delay=1.0,
            jitter=False
        )
        
        delay0 = self.error_handler._calculate_retry_delay(policy, 0)
        delay1 = self.error_handler._calculate_retry_delay(policy, 1)
        delay2 = self.error_handler._calculate_retry_delay(policy, 2)
        
        assert delay0 == 1.0
        assert delay1 == 2.0
        assert delay2 == 3.0
    
    def test_calculate_retry_delay_fixed(self):
        """Test fixed delay calculation."""
        policy = RetryPolicy(
            strategy=RetryStrategy.FIXED_DELAY,
            base_delay=2.0,
            jitter=False
        )
        
        delay0 = self.error_handler._calculate_retry_delay(policy, 0)
        delay1 = self.error_handler._calculate_retry_delay(policy, 1)
        delay2 = self.error_handler._calculate_retry_delay(policy, 2)
        
        assert delay0 == 2.0
        assert delay1 == 2.0
        assert delay2 == 2.0
    
    def test_calculate_retry_delay_max_delay(self):
        """Test max delay limit."""
        policy = RetryPolicy(
            strategy=RetryStrategy.EXPONENTIAL_BACKOFF,
            base_delay=10.0,
            backoff_factor=10.0,
            max_delay=30.0,
            jitter=False
        )
        
        delay3 = self.error_handler._calculate_retry_delay(policy, 3)
        assert delay3 == 30.0  # Should be capped at max_delay
    
    def test_set_alert_threshold(self):
        """Test setting alert thresholds."""
        self.error_handler.set_alert_threshold(
            "ValueError", 
            threshold=5, 
            time_window_minutes=10,
            severity=AlertSeverity.HIGH
        )
        
        threshold = self.error_handler._alert_thresholds["ValueError"]
        assert threshold["threshold"] == 5
        assert threshold["time_window_minutes"] == 10
        assert threshold["severity"] == AlertSeverity.HIGH
    
    def test_register_alert_callback(self):
        """Test registering alert callbacks."""
        callback = Mock()
        self.error_handler.register_alert_callback(callback)
        
        assert callback in self.error_handler._alert_callbacks
        self.mock_logger.debug.assert_called_with("Registered alert callback")
    
    def test_set_circuit_breaker(self):
        """Test setting circuit breaker configuration."""
        self.error_handler.set_circuit_breaker(
            "test_op",
            failure_threshold=3,
            recovery_timeout=30,
            half_open_max_calls=2
        )
        
        breaker = self.error_handler._circuit_breakers["test_op"]
        assert breaker["failure_threshold"] == 3
        assert breaker["recovery_timeout"] == 30
        assert breaker["half_open_max_calls"] == 2
        assert breaker["state"] == "closed"
        assert breaker["failure_count"] == 0
    
    def test_circuit_breaker_closed_state(self):
        """Test circuit breaker in closed state."""
        self.error_handler.set_circuit_breaker("test_op", failure_threshold=2)
        
        # Should allow operation in closed state
        assert self.error_handler._check_circuit_breaker("test_op") is True
    
    def test_circuit_breaker_opens_after_failures(self):
        """Test circuit breaker opening after threshold failures."""
        self.error_handler.set_circuit_breaker("test_op", failure_threshold=2)
        
        # Simulate failures
        self.error_handler._update_circuit_breaker_failure("test_op")
        assert self.error_handler._circuit_breakers["test_op"]["state"] == "closed"
        
        self.error_handler._update_circuit_breaker_failure("test_op")
        assert self.error_handler._circuit_breakers["test_op"]["state"] == "open"
        
        # Should not allow operation when open
        assert self.error_handler._check_circuit_breaker("test_op") is False
    
    def test_circuit_breaker_half_open_transition(self):
        """Test circuit breaker transition to half-open state."""
        self.error_handler.set_circuit_breaker("test_op", failure_threshold=1, recovery_timeout=0)
        
        # Open the circuit
        self.error_handler._update_circuit_breaker_failure("test_op")
        assert self.error_handler._circuit_breakers["test_op"]["state"] == "open"
        
        # Should transition to half-open after timeout
        assert self.error_handler._check_circuit_breaker("test_op") is True
        assert self.error_handler._circuit_breakers["test_op"]["state"] == "half_open"
    
    def test_circuit_breaker_closes_on_success(self):
        """Test circuit breaker closing on successful operation."""
        self.error_handler.set_circuit_breaker("test_op", failure_threshold=1, recovery_timeout=0)
        
        # Open the circuit and transition to half-open
        self.error_handler._update_circuit_breaker_failure("test_op")
        self.error_handler._check_circuit_breaker("test_op")  # Moves to half-open
        
        # Success should close the circuit
        self.error_handler._update_circuit_breaker_success("test_op")
        assert self.error_handler._circuit_breakers["test_op"]["state"] == "closed"
        assert self.error_handler._circuit_breakers["test_op"]["failure_count"] == 0
    
    @pytest.mark.asyncio
    async def test_execute_with_retry_circuit_breaker_open(self):
        """Test retry execution with open circuit breaker."""
        self.error_handler.set_circuit_breaker("test_op", failure_threshold=1)
        
        # Open the circuit
        self.error_handler._update_circuit_breaker_failure("test_op")
        
        async def dummy_operation():
            return "success"
        
        with pytest.raises(RuntimeError, match="Circuit breaker is open"):
            await self.error_handler.execute_with_retry("test_op", dummy_operation)
    
    def test_update_error_metrics(self):
        """Test error metrics updating."""
        error = ValueError("Test error")
        
        self.error_handler._update_error_metrics(error, "test_agent")
        
        assert self.error_handler._metrics.total_errors == 1
        assert self.error_handler._metrics.errors_by_type["ValueError"] == 1
        assert self.error_handler._metrics.errors_by_agent["test_agent"] == 1
        assert len(self.error_handler._error_history) == 1
    
    def test_error_rate_calculation(self):
        """Test error rate calculation."""
        # Add some errors
        for i in range(5):
            error = ValueError(f"Error {i}")
            self.error_handler._update_error_metrics(error)
        
        # Error rate should be 5 errors per minute
        assert self.error_handler._metrics.error_rate_per_minute == 5
    
    def test_error_alert_triggering(self):
        """Test error alert triggering."""
        callback = Mock()
        self.error_handler.register_alert_callback(callback)
        self.error_handler.set_alert_threshold("ValueError", threshold=2, time_window_minutes=5)
        
        # Add errors to trigger alert
        for i in range(3):
            error = ValueError(f"Error {i}")
            self.error_handler._update_error_metrics(error)
        
        # Alert should have been triggered (multiple times as each error above threshold triggers alert)
        assert callback.call_count >= 1
        alert = callback.call_args[0][0]
        assert isinstance(alert, ErrorAlert)
        assert alert.error_type == "ValueError"
        assert alert.count >= 2
    
    def test_get_recent_errors(self):
        """Test getting recent error history."""
        # Add some errors
        for i in range(10):
            error = ValueError(f"Error {i}")
            self.error_handler._update_error_metrics(error)
        
        recent_errors = self.error_handler.get_recent_errors(limit=5)
        assert len(recent_errors) == 5
        assert all("error_type" in error for error in recent_errors)
        assert all("timestamp" in error for error in recent_errors)
    
    def test_clear_error_history(self):
        """Test clearing error history and metrics."""
        # Add some errors
        for i in range(5):
            error = ValueError(f"Error {i}")
            self.error_handler._update_error_metrics(error)
        
        assert len(self.error_handler._error_history) == 5
        assert self.error_handler._metrics.total_errors == 5
        
        self.error_handler.clear_error_history()
        
        assert len(self.error_handler._error_history) == 0
        assert self.error_handler._metrics.total_errors == 0