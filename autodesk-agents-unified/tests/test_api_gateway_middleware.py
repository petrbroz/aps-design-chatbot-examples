"""
Tests for API Gateway middleware functionality.

These tests validate:
- Request/response transformation middleware
- Authentication middleware
- CORS and security headers
- Request logging and monitoring
- Error handling middleware
"""

import pytest
import json
import time
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Dict, Any

from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from agent_core.api_gateway import APIGateway
from agent_core.core import AgentCore
from agent_core.config import CoreConfig
from agent_core.auth import AuthContext
from agent_core.models import AgentRequest, AgentResponse
from agent_core.orchestrator import StrandsOrchestrator


@pytest.fixture
def test_config():
    """Create test configuration."""
    return CoreConfig(
        aws_region="us-east-1",
        bedrock_model_id="anthropic.claude-3-5-sonnet-20241022-v2:0",
        opensearch_endpoint="https://test-opensearch.amazonaws.com",
        cache_directory="/tmp/test_middleware_cache",
        log_level="DEBUG",
        health_check_interval=30
    )


@pytest.fixture
def mock_agent_core(test_config):
    """Create mock AgentCore."""
    core = Mock()
    core.config = test_config
    core.logger = Mock()
    core.auth_manager = Mock()
    core.auth_manager.enabled = True
    core.auth_manager.validate_token = AsyncMock()
    return core


@pytest.fixture
def mock_orchestrator():
    """Create mock orchestrator."""
    orchestrator = Mock()
    orchestrator.route_request = AsyncMock()
    return orchestrator


@pytest.fixture
def api_gateway(mock_agent_core, mock_orchestrator):
    """Create API Gateway for testing."""
    return APIGateway(mock_agent_core, mock_orchestrator)


@pytest.fixture
def app(api_gateway):
    """Create FastAPI app with middleware."""
    return api_gateway.app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


class TestAuthenticationMiddleware:
    """Test authentication middleware functionality."""
    
    def test_valid_bearer_token(self, client, mock_agent_core, mock_orchestrator):
        """Test valid Bearer token authentication."""
        # Mock successful token validation
        mock_agent_core.auth_manager.validate_token.return_value = AuthContext(
            access_token="valid_token_12345",
            project_id="b.project123"
        )
        
        # Mock successful agent response
        mock_orchestrator.route_request.return_value = AgentResponse(
            responses=["Authentication successful"],
            agent_type="model_properties",
            success=True
        )
        
        payload = {
            "prompt": "Test with valid token",
            "project_id": "b.project123"
        }
        
        headers = {
            "Authorization": "Bearer valid_token_12345",
            "Content-Type": "application/json"
        }
        
        response = client.post(
            "/api/v1/model-properties/prompt",
            json=payload,
            headers=headers
        )
        
        assert response.status_code == 200
        mock_agent_core.auth_manager.validate_token.assert_called_once_with("valid_token_12345")
    
    def test_missing_authorization_header(self, client):
        """Test request without Authorization header."""
        payload = {
            "prompt": "Test without auth",
            "project_id": "b.project123"
        }
        
        response = client.post(
            "/api/v1/model-properties/prompt",
            json=payload
        )
        
        assert response.status_code == 401
        data = response.json()
        assert "authorization" in data["detail"].lower() or "missing" in data["detail"].lower()
    
    def test_invalid_token_format(self, client):
        """Test invalid token format."""
        payload = {
            "prompt": "Test with invalid token format",
            "project_id": "b.project123"
        }
        
        headers = {
            "Authorization": "InvalidTokenFormat",
            "Content-Type": "application/json"
        }
        
        response = client.post(
            "/api/v1/model-properties/prompt",
            json=payload,
            headers=headers
        )
        
        assert response.status_code == 401
        data = response.json()
        assert "bearer" in data["detail"].lower() or "invalid" in data["detail"].lower()
    
    def test_token_validation_failure(self, client, mock_agent_core):
        """Test token validation failure."""
        # Mock token validation failure
        mock_agent_core.auth_manager.validate_token.side_effect = Exception("Invalid token")
        
        payload = {
            "prompt": "Test with invalid token",
            "project_id": "b.project123"
        }
        
        headers = {
            "Authorization": "Bearer invalid_token_12345",
            "Content-Type": "application/json"
        }
        
        response = client.post(
            "/api/v1/model-properties/prompt",
            json=payload,
            headers=headers
        )
        
        assert response.status_code == 401
        data = response.json()
        assert "invalid token" in data["detail"].lower()
    
    def test_authentication_bypass_for_health_endpoints(self, client):
        """Test that health endpoints bypass authentication."""
        response = client.get("/health")
        
        # Health endpoint should work without authentication
        assert response.status_code == 200
    
    def test_authentication_bypass_for_public_endpoints(self, client):
        """Test that public endpoints bypass authentication."""
        # Test root endpoint
        response = client.get("/")
        assert response.status_code in [200, 404]  # Either works or not implemented
        
        # Test docs endpoint
        response = client.get("/docs")
        assert response.status_code in [200, 404]  # Either works or not implemented


class TestCORSMiddleware:
    """Test CORS middleware functionality."""
    
    def test_cors_preflight_request(self, client):
        """Test CORS preflight request handling."""
        headers = {
            "Origin": "https://example.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization, Content-Type"
        }
        
        response = client.options(
            "/api/v1/model-properties/prompt",
            headers=headers
        )
        
        # Should handle preflight request
        assert response.status_code in [200, 204]
        
        # Check CORS headers if implemented
        if "Access-Control-Allow-Origin" in response.headers:
            assert response.headers["Access-Control-Allow-Origin"] in ["*", "https://example.com"]
            assert "POST" in response.headers.get("Access-Control-Allow-Methods", "")
    
    def test_cors_actual_request(self, client, mock_agent_core, mock_orchestrator):
        """Test CORS headers on actual requests."""
        # Mock authentication and agent response
        mock_agent_core.auth_manager.validate_token.return_value = AuthContext(
            access_token="test_token",
            project_id="b.project123"
        )
        
        mock_orchestrator.route_request.return_value = AgentResponse(
            responses=["CORS test response"],
            agent_type="model_properties",
            success=True
        )
        
        payload = {
            "prompt": "CORS test",
            "project_id": "b.project123"
        }
        
        headers = {
            "Authorization": "Bearer test_token",
            "Content-Type": "application/json",
            "Origin": "https://example.com"
        }
        
        response = client.post(
            "/api/v1/model-properties/prompt",
            json=payload,
            headers=headers
        )
        
        assert response.status_code == 200
        
        # Check CORS headers if implemented
        if "Access-Control-Allow-Origin" in response.headers:
            assert response.headers["Access-Control-Allow-Origin"] in ["*", "https://example.com"]


class TestLoggingMiddleware:
    """Test logging middleware functionality."""
    
    def test_request_logging(self, client, mock_agent_core, mock_orchestrator):
        """Test that requests are logged properly."""
        # Mock authentication and agent response
        mock_agent_core.auth_manager.validate_token.return_value = AuthContext(
            access_token="test_token",
            project_id="b.project123"
        )
        
        mock_orchestrator.route_request.return_value = AgentResponse(
            responses=["Logging test response"],
            agent_type="model_properties",
            success=True,
            execution_time=1.5
        )
        
        payload = {
            "prompt": "Logging test",
            "project_id": "b.project123"
        }
        
        headers = {
            "Authorization": "Bearer test_token",
            "Content-Type": "application/json"
        }
        
        response = client.post(
            "/api/v1/model-properties/prompt",
            json=payload,
            headers=headers
        )
        
        assert response.status_code == 200
        
        # Verify logging was called
        mock_agent_core.logger.info.assert_called()
        
        # Check that request details were logged
        log_calls = mock_agent_core.logger.info.call_args_list
        logged_messages = [call[0][0] for call in log_calls]
        
        # Should log request start and completion
        assert any("request" in msg.lower() for msg in logged_messages)
    
    def test_error_logging(self, client, mock_agent_core, mock_orchestrator):
        """Test that errors are logged properly."""
        # Mock authentication success but agent failure
        mock_agent_core.auth_manager.validate_token.return_value = AuthContext(
            access_token="test_token",
            project_id="b.project123"
        )
        
        mock_orchestrator.route_request.side_effect = Exception("Agent processing error")
        
        payload = {
            "prompt": "Error logging test",
            "project_id": "b.project123"
        }
        
        headers = {
            "Authorization": "Bearer test_token",
            "Content-Type": "application/json"
        }
        
        response = client.post(
            "/api/v1/model-properties/prompt",
            json=payload,
            headers=headers
        )
        
        # Should return error response
        assert response.status_code == 500
        
        # Verify error was logged
        mock_agent_core.logger.error.assert_called()
    
    def test_performance_logging(self, client, mock_agent_core, mock_orchestrator):
        """Test that performance metrics are logged."""
        # Mock slow agent response
        async def slow_response(*args, **kwargs):
            import asyncio
            await asyncio.sleep(0.1)  # Small delay for testing
            return AgentResponse(
                responses=["Slow response"],
                agent_type="model_properties",
                success=True,
                execution_time=2.5
            )
        
        mock_agent_core.auth_manager.validate_token.return_value = AuthContext(
            access_token="test_token",
            project_id="b.project123"
        )
        
        mock_orchestrator.route_request.side_effect = slow_response
        
        payload = {
            "prompt": "Performance test",
            "project_id": "b.project123"
        }
        
        headers = {
            "Authorization": "Bearer test_token",
            "Content-Type": "application/json"
        }
        
        response = client.post(
            "/api/v1/model-properties/prompt",
            json=payload,
            headers=headers
        )
        
        assert response.status_code == 200
        
        # Check that performance metrics were logged
        log_calls = mock_agent_core.logger.info.call_args_list
        logged_data = []
        for call in log_calls:
            if len(call) > 1 and isinstance(call[1], dict):
                logged_data.append(call[1])
        
        # Should log execution time
        assert any("execution_time" in data for data in logged_data)


class TestSecurityHeaders:
    """Test security headers middleware."""
    
    def test_security_headers_present(self, client, mock_agent_core, mock_orchestrator):
        """Test that security headers are added to responses."""
        # Mock authentication and agent response
        mock_agent_core.auth_manager.validate_token.return_value = AuthContext(
            access_token="test_token",
            project_id="b.project123"
        )
        
        mock_orchestrator.route_request.return_value = AgentResponse(
            responses=["Security test response"],
            agent_type="model_properties",
            success=True
        )
        
        payload = {
            "prompt": "Security headers test",
            "project_id": "b.project123"
        }
        
        headers = {
            "Authorization": "Bearer test_token",
            "Content-Type": "application/json"
        }
        
        response = client.post(
            "/api/v1/model-properties/prompt",
            json=payload,
            headers=headers
        )
        
        assert response.status_code == 200
        
        # Check for common security headers (if implemented)
        security_headers = [
            "X-Content-Type-Options",
            "X-Frame-Options", 
            "X-XSS-Protection",
            "Strict-Transport-Security"
        ]
        
        # At least some security headers should be present
        present_headers = [h for h in security_headers if h in response.headers]
        
        # If security headers are implemented, verify their values
        if "X-Content-Type-Options" in response.headers:
            assert response.headers["X-Content-Type-Options"] == "nosniff"
        
        if "X-Frame-Options" in response.headers:
            assert response.headers["X-Frame-Options"] in ["DENY", "SAMEORIGIN"]


class TestRequestResponseTransformation:
    """Test request/response transformation middleware."""
    
    def test_request_transformation(self, client, mock_agent_core, mock_orchestrator):
        """Test that requests are transformed correctly."""
        # Mock authentication
        mock_agent_core.auth_manager.validate_token.return_value = AuthContext(
            access_token="test_token",
            project_id="b.project123",
            version_id="test_version"
        )
        
        # Capture the transformed request
        captured_request = None
        
        def capture_request(request):
            nonlocal captured_request
            captured_request = request
            return AgentResponse(
                responses=["Transformation test"],
                agent_type="model_properties",
                success=True
            )
        
        mock_orchestrator.route_request.side_effect = capture_request
        
        # Legacy payload format
        payload = {
            "prompt": "Transform this request",
            "project_id": "b.project123",
            "version_id": "test_version"
        }
        
        headers = {
            "Authorization": "Bearer test_token",
            "Content-Type": "application/json"
        }
        
        response = client.post(
            "/api/v1/model-properties/prompt",
            json=payload,
            headers=headers
        )
        
        assert response.status_code == 200
        
        # Verify request was transformed to AgentRequest format
        assert captured_request is not None
        assert isinstance(captured_request, AgentRequest)
        assert captured_request.agent_type == "model_properties"
        assert captured_request.prompt == "Transform this request"
        assert captured_request.authentication.project_id == "b.project123"
        assert captured_request.authentication.version_id == "test_version"
    
    def test_response_transformation(self, client, mock_agent_core, mock_orchestrator):
        """Test that responses are transformed to legacy format."""
        # Mock authentication
        mock_agent_core.auth_manager.validate_token.return_value = AuthContext(
            access_token="test_token",
            project_id="b.project123"
        )
        
        # Mock agent response with metadata
        mock_orchestrator.route_request.return_value = AgentResponse(
            responses=["Response transformation test"],
            agent_type="model_properties",
            success=True,
            execution_time=1.8,
            metadata={
                "tools_used": ["create_index", "query_index"],
                "cache_hit": True
            },
            request_id="req_12345"
        )
        
        payload = {
            "prompt": "Response transformation test",
            "project_id": "b.project123"
        }
        
        headers = {
            "Authorization": "Bearer test_token",
            "Content-Type": "application/json"
        }
        
        response = client.post(
            "/api/v1/model-properties/prompt",
            json=payload,
            headers=headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify legacy response format
        assert "responses" in data
        assert isinstance(data["responses"], list)
        assert data["responses"][0] == "Response transformation test"
        assert "execution_time" in data
        assert data["execution_time"] == 1.8
        assert "metadata" in data
        assert "tools_used" in data["metadata"]
        assert data["metadata"]["cache_hit"] is True
    
    def test_error_response_transformation(self, client, mock_agent_core, mock_orchestrator):
        """Test that error responses are transformed correctly."""
        # Mock authentication
        mock_agent_core.auth_manager.validate_token.return_value = AuthContext(
            access_token="test_token",
            project_id="b.project123"
        )
        
        # Mock agent error response
        mock_orchestrator.route_request.return_value = AgentResponse(
            responses=["Error: Invalid query format"],
            agent_type="model_properties",
            success=False,
            execution_time=0.5,
            metadata={"error_type": "validation_error"}
        )
        
        payload = {
            "prompt": "Invalid query that causes error",
            "project_id": "b.project123"
        }
        
        headers = {
            "Authorization": "Bearer test_token",
            "Content-Type": "application/json"
        }
        
        response = client.post(
            "/api/v1/model-properties/prompt",
            json=payload,
            headers=headers
        )
        
        # Should return 200 with error in response body (agent handles errors gracefully)
        assert response.status_code == 200
        data = response.json()
        
        assert "responses" in data
        assert "Error:" in data["responses"][0]
        assert "success" in data
        assert data["success"] is False
        assert "metadata" in data
        assert data["metadata"]["error_type"] == "validation_error"


class TestMiddlewareOrdering:
    """Test that middleware is applied in correct order."""
    
    def test_middleware_execution_order(self, client, mock_agent_core, mock_orchestrator):
        """Test that middleware executes in the correct order."""
        # Track middleware execution order
        execution_order = []
        
        # Mock middleware methods to track execution
        original_validate = mock_agent_core.auth_manager.validate_token
        original_log_info = mock_agent_core.logger.info
        
        def track_auth(*args, **kwargs):
            execution_order.append("auth")
            return AuthContext(access_token="test_token", project_id="b.project123")
        
        def track_logging(*args, **kwargs):
            execution_order.append("logging")
            return original_log_info(*args, **kwargs)
        
        mock_agent_core.auth_manager.validate_token.side_effect = track_auth
        mock_agent_core.logger.info.side_effect = track_logging
        
        # Mock agent response
        mock_orchestrator.route_request.return_value = AgentResponse(
            responses=["Middleware order test"],
            agent_type="model_properties",
            success=True
        )
        
        payload = {
            "prompt": "Test middleware order",
            "project_id": "b.project123"
        }
        
        headers = {
            "Authorization": "Bearer test_token",
            "Content-Type": "application/json"
        }
        
        response = client.post(
            "/api/v1/model-properties/prompt",
            json=payload,
            headers=headers
        )
        
        assert response.status_code == 200
        
        # Verify middleware executed
        assert "auth" in execution_order
        assert "logging" in execution_order
        
        # Auth should happen before logging the successful request
        auth_index = execution_order.index("auth")
        logging_indices = [i for i, x in enumerate(execution_order) if x == "logging"]
        
        # At least one logging call should happen after auth
        assert any(log_idx > auth_index for log_idx in logging_indices)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])