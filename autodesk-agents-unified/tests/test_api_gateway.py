"""
Unit tests for the API Gateway module.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime
from fastapi.testclient import TestClient
from fastapi import status

from agent_core.api_gateway import APIGateway, ModelPropertiesPayload, AECDataModelPayload, ModelDerivativesPayload
from agent_core.models import AgentRequest, AgentResponse, ErrorResponse, ErrorCode
from agent_core.auth import AuthContext
from agent_core.orchestrator import StrandsOrchestrator
from agent_core.core import AgentCore


class TestAPIGateway:
    """Test cases for the APIGateway class."""
    
    @pytest.fixture
    def mock_agent_core(self):
        """Create a mock AgentCore instance."""
        mock_core = Mock(spec=AgentCore)
        mock_core.logger = Mock()
        mock_core.auth_manager = Mock()
        mock_core.auth_manager.enabled = False  # Disable auth for tests
        mock_core.auth_manager.extract_auth_context = Mock()
        mock_core.auth_manager.validate_token = AsyncMock()
        
        # Mock health monitor
        mock_core.health_monitor = Mock()
        mock_core.health_monitor.record_response_time = Mock()
        mock_core.health_monitor.get_health_check_endpoint_data = Mock(return_value={
            "status": "healthy",
            "healthy": True,
            "timestamp": "2024-01-01T00:00:00Z",
            "uptime": 100.0,
            "version": "1.0.0"
        })
        mock_core.health_monitor.get_detailed_health_check = Mock(return_value={
            "overall_status": "healthy",
            "checks": {},
            "system_metrics": {},
            "performance": {},
            "uptime_seconds": 100.0
        })
        mock_core.health_monitor.get_system_metrics = Mock(return_value={"cpu_percent": 10.0, "memory_percent": 50.0, "memory_used_mb": 1024.0, "memory_total_mb": 2048.0, "disk_percent": 30.0, "uptime_seconds": 100.0, "timestamp": "2024-01-01T00:00:00Z"})
        mock_core.health_monitor.get_performance_summary = Mock(return_value={"overall": None, "agents": {}, "tools": {}})
        mock_core.health_monitor.get_health_summary = Mock(return_value={"overall_status": "healthy", "checks": {}, "system_metrics": {}, "performance": {}, "uptime_seconds": 100.0})
        
        return mock_core
    
    @pytest.fixture
    def mock_strands(self, mock_agent_core):
        """Create a mock StrandsOrchestrator instance."""
        mock_strands = Mock(spec=StrandsOrchestrator)
        mock_strands.agent_core = mock_agent_core
        mock_strands._initialized = True
        mock_strands.initialize = AsyncMock()
        mock_strands.shutdown = AsyncMock()
        mock_strands.route_request = AsyncMock()
        mock_strands.get_orchestrator_status = AsyncMock()
        mock_strands.get_registered_agents = Mock(return_value=["model_properties", "aec_data_model", "model_derivatives"])
        return mock_strands
    
    @pytest.fixture
    def api_gateway(self, mock_strands):
        """Create an APIGateway instance for testing."""
        return APIGateway(mock_strands)
    
    @pytest.fixture
    def test_client(self, api_gateway):
        """Create a test client for the API Gateway."""
        return TestClient(api_gateway.app)
    
    def test_init(self, mock_strands):
        """Test APIGateway initialization."""
        gateway = APIGateway(mock_strands, static_dir="/test/static")
        
        assert gateway.strands == mock_strands
        assert gateway.agent_core == mock_strands.agent_core
        assert gateway.auth_manager == mock_strands.agent_core.auth_manager
        assert gateway.static_dir == "/test/static"
        assert gateway._request_count == 0
        assert isinstance(gateway._start_time, datetime)
    
    def test_check_access_valid_token(self, api_gateway):
        """Test _check_access with valid authorization header."""
        from fastapi import Request
        
        # Create a mock request with valid authorization header
        mock_request = Mock(spec=Request)
        mock_request.headers = {"authorization": "Bearer test_token_123"}
        mock_request.state = Mock()
        # Explicitly set no auth_context to force fallback to header parsing
        mock_request.state.auth_context = None
        
        token = api_gateway._check_access(mock_request)
        assert token == "test_token_123"
    
    def test_check_access_missing_header(self, api_gateway):
        """Test _check_access with missing authorization header."""
        from fastapi import Request, HTTPException
        
        mock_request = Mock(spec=Request)
        mock_request.headers = {}
        mock_request.state = Mock()
        # Explicitly set no auth_context to force fallback to header parsing
        mock_request.state.auth_context = None
        
        with pytest.raises(HTTPException) as exc_info:
            api_gateway._check_access(mock_request)
        
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Authorization header required" in str(exc_info.value.detail)
    
    def test_check_access_invalid_format(self, api_gateway):
        """Test _check_access with invalid authorization header format."""
        from fastapi import Request, HTTPException
        
        mock_request = Mock(spec=Request)
        mock_request.headers = {"authorization": "Invalid token_123"}
        mock_request.state = Mock()
        # Explicitly set no auth_context to force fallback to header parsing
        mock_request.state.auth_context = None
        
        with pytest.raises(HTTPException) as exc_info:
            api_gateway._check_access(mock_request)
        
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Invalid authorization header format" in str(exc_info.value.detail)
    
    def test_generate_urn_from_version(self, api_gateway):
        """Test URN generation from version ID."""
        version_id = "test_version_123"
        urn = api_gateway._generate_urn_from_version(version_id)
        
        # Should be base64 encoded with replacements
        import base64
        expected = base64.b64encode(version_id.encode()).decode().replace("/", "_").replace("=", "")
        assert urn == expected
    
    @pytest.mark.asyncio
    async def test_handle_agent_request_success(self, api_gateway, mock_strands):
        """Test successful agent request handling."""
        from fastapi import Request
        
        # Setup mocks
        mock_request = Mock(spec=Request)
        mock_request.state = Mock()
        mock_request.state.request_id = "test_request_123"
        # Explicitly set no auth_context for this test
        mock_request.state.auth_context = None
        mock_request.client = Mock()
        mock_request.client.host = "127.0.0.1"
        mock_request.headers = {"user-agent": "test-client"}
        mock_request.url = Mock()
        mock_request.url.path = "/test/path"
        
        payload = ModelPropertiesPayload(
            prompt="Test prompt",
            project_id="test_project",
            version_id="test_version"
        )
        
        # Mock successful response
        mock_response = AgentResponse(
            responses=["Test response"],
            agent_type="model_properties",
            success=True
        )
        mock_strands.route_request.return_value = mock_response
        
        # Execute request
        result = await api_gateway._handle_agent_request(
            agent_type="model_properties",
            payload=payload,
            request=mock_request,
            access_token="test_token",
            context={"project_id": "test_project", "version_id": "test_version"}
        )
        
        # Verify result
        assert result.responses == ["Test response"]
        assert api_gateway._request_count == 1
        
        # Verify orchestrator was called correctly
        mock_strands.route_request.assert_called_once()
        call_args = mock_strands.route_request.call_args[0][0]
        assert isinstance(call_args, AgentRequest)
        assert call_args.agent_type == "model_properties"
        assert call_args.prompt == "Test prompt"
        assert call_args.authentication.access_token == "test_token"
    
    @pytest.mark.asyncio
    async def test_handle_agent_request_failure(self, api_gateway, mock_strands):
        """Test agent request handling with failure response."""
        from fastapi import Request, HTTPException
        
        mock_request = Mock(spec=Request)
        mock_request.state = Mock()
        mock_request.state.request_id = "test_request_123"
        mock_request.client = Mock()
        mock_request.client.host = "127.0.0.1"
        mock_request.headers = {"user-agent": "test-client"}
        mock_request.url = Mock()
        mock_request.url.path = "/test/path"
        
        payload = ModelPropertiesPayload(
            prompt="Test prompt",
            project_id="test_project",
            version_id="test_version"
        )
        
        # Mock failure response
        error_response = ErrorResponse(
            error_code="TEST_ERROR",
            message="Test error message"
        )
        mock_response = AgentResponse(
            responses=["Error occurred"],
            agent_type="model_properties",
            success=False,
            metadata={"error": error_response.to_dict()}
        )
        mock_strands.route_request.return_value = mock_response
        
        # Execute request and expect HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await api_gateway._handle_agent_request(
                agent_type="model_properties",
                payload=payload,
                request=mock_request,
                access_token="test_token",
                context={"project_id": "test_project", "version_id": "test_version"}
            )
        
        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Test error message" in str(exc_info.value.detail)
    
    @pytest.mark.asyncio
    async def test_handle_agent_request_exception(self, api_gateway, mock_strands):
        """Test agent request handling with unexpected exception."""
        from fastapi import Request, HTTPException
        
        mock_request = Mock(spec=Request)
        mock_request.state = Mock()
        mock_request.state.request_id = "test_request_123"
        mock_request.client = Mock()
        mock_request.client.host = "127.0.0.1"
        mock_request.headers = {"user-agent": "test-client"}
        mock_request.url = Mock()
        mock_request.url.path = "/test/path"
        
        payload = ModelPropertiesPayload(
            prompt="Test prompt",
            project_id="test_project",
            version_id="test_version"
        )
        
        # Mock exception
        mock_strands.route_request.side_effect = Exception("Unexpected error")
        
        # Execute request and expect HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await api_gateway._handle_agent_request(
                agent_type="model_properties",
                payload=payload,
                request=mock_request,
                access_token="test_token",
                context={"project_id": "test_project", "version_id": "test_version"}
            )
        
        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Internal server error" in str(exc_info.value.detail)
    
    @pytest.mark.asyncio
    async def test_startup(self, api_gateway, mock_strands):
        """Test API Gateway startup."""
        mock_strands._initialized = False
        
        await api_gateway.startup()
        
        mock_strands.initialize.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_startup_already_initialized(self, api_gateway, mock_strands):
        """Test API Gateway startup when orchestrator is already initialized."""
        mock_strands._initialized = True
        
        await api_gateway.startup()
        
        mock_strands.initialize.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_shutdown(self, api_gateway, mock_strands):
        """Test API Gateway shutdown."""
        mock_strands._initialized = True
        
        await api_gateway.shutdown()
        
        mock_strands.shutdown.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_shutdown_not_initialized(self, api_gateway, mock_strands):
        """Test API Gateway shutdown when orchestrator is not initialized."""
        mock_strands._initialized = False
        
        await api_gateway.shutdown()
        
        mock_strands.shutdown.assert_not_called()
    
    def test_get_app(self, api_gateway):
        """Test getting the FastAPI app instance."""
        app = api_gateway.get_app()
        assert app == api_gateway.app
    
    def test_get_metrics(self, api_gateway):
        """Test getting API Gateway metrics."""
        api_gateway._request_count = 42
        
        metrics = api_gateway.get_metrics()
        
        assert metrics["total_requests"] == 42
        assert "uptime_seconds" in metrics
        assert "start_time" in metrics
        assert "registered_agents" in metrics


class TestAPIGatewayEndpoints:
    """Test cases for API Gateway endpoints using TestClient."""
    
    @pytest.fixture
    def mock_agent_core(self):
        """Create a mock AgentCore instance."""
        mock_core = Mock(spec=AgentCore)
        mock_core.logger = Mock()
        mock_core.auth_manager = Mock()
        mock_core.auth_manager.enabled = False  # Disable auth for tests
        mock_core.auth_manager.extract_auth_context = Mock()
        mock_core.auth_manager.validate_token = AsyncMock()
        
        # Mock health monitor
        mock_core.health_monitor = Mock()
        mock_core.health_monitor.record_response_time = Mock()
        mock_core.health_monitor.get_health_check_endpoint_data = Mock(return_value={
            "status": "healthy",
            "healthy": True,
            "timestamp": "2024-01-01T00:00:00Z",
            "uptime": 100.0,
            "version": "1.0.0"
        })
        mock_core.health_monitor.get_detailed_health_check = Mock(return_value={
            "overall_status": "healthy",
            "checks": {},
            "system_metrics": {},
            "performance": {},
            "uptime_seconds": 100.0
        })
        mock_core.health_monitor.get_system_metrics = Mock(return_value={"cpu_percent": 10.0, "memory_percent": 50.0, "memory_used_mb": 1024.0, "memory_total_mb": 2048.0, "disk_percent": 30.0, "uptime_seconds": 100.0, "timestamp": "2024-01-01T00:00:00Z"})
        mock_core.health_monitor.get_performance_summary = Mock(return_value={"overall": None, "agents": {}, "tools": {}})
        mock_core.health_monitor.get_health_summary = Mock(return_value={"overall_status": "healthy", "checks": {}, "system_metrics": {}, "performance": {}, "uptime_seconds": 100.0})
        
        return mock_core
    
    @pytest.fixture
    def mock_strands(self, mock_agent_core):
        """Create a mock StrandsOrchestrator instance."""
        mock_strands = Mock(spec=StrandsOrchestrator)
        mock_strands.agent_core = mock_agent_core
        mock_strands._initialized = True
        mock_strands.initialize = AsyncMock()
        mock_strands.shutdown = AsyncMock()
        mock_strands.route_request = AsyncMock()
        mock_strands.get_orchestrator_status = AsyncMock(return_value={"status": "healthy"})
        mock_strands.get_registered_agents = Mock(return_value=["model_properties", "aec_data_model", "model_derivatives"])
        return mock_strands
    
    @pytest.fixture
    def test_client(self, mock_strands):
        """Create a test client for the API Gateway."""
        gateway = APIGateway(mock_strands)
        return TestClient(gateway.app)
    
    def test_health_endpoint(self, test_client, mock_strands):
        """Test the health check endpoint."""
        response = test_client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["healthy"] is True
        assert "timestamp" in data
        assert "uptime" in data
        assert "version" in data
    
    def test_detailed_health_endpoint(self, test_client, mock_strands):
        """Test the detailed health check endpoint."""
        response = test_client.get("/health/detailed")
        
        assert response.status_code == 200
        data = response.json()
        assert "overall_status" in data
        assert "checks" in data
        assert "system_metrics" in data
        assert "performance" in data
        assert "uptime_seconds" in data
    
    def test_metrics_endpoint(self, test_client, mock_strands):
        """Test the metrics endpoint."""
        response = test_client.get("/metrics")
        
        assert response.status_code == 200
        data = response.json()
        assert "system_metrics" in data
        assert "performance" in data
        assert "health_summary" in data
    
    def test_status_endpoint(self, test_client, mock_strands):
        """Test the status endpoint."""
        response = test_client.get("/status")
        
        assert response.status_code == 200
        data = response.json()
        assert "gateway" in data
        assert "orchestrator" in data
        assert "uptime_seconds" in data["gateway"]
        assert "total_requests" in data["gateway"]
    
    def test_model_properties_endpoint_success(self, test_client, mock_strands):
        """Test the Model Properties endpoint with successful response."""
        # Mock successful response
        mock_response = AgentResponse(
            responses=["Test response from model properties"],
            agent_type="model_properties",
            success=True
        )
        mock_strands.route_request.return_value = mock_response
        
        response = test_client.post(
            "/chatbot/prompt",
            json={
                "prompt": "Test prompt",
                "project_id": "test_project",
                "version_id": "test_version"
            },
            headers={"Authorization": "Bearer test_token"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["responses"] == ["Test response from model properties"]
    
    def test_model_properties_endpoint_unauthorized(self, test_client):
        """Test the Model Properties endpoint without authorization."""
        response = test_client.post(
            "/chatbot/prompt",
            json={
                "prompt": "Test prompt",
                "project_id": "test_project",
                "version_id": "test_version"
            }
        )
        
        assert response.status_code == 401
    
    def test_aec_data_model_endpoint_success(self, test_client, mock_strands):
        """Test the AEC Data Model endpoint with successful response."""
        # Mock successful response
        mock_response = AgentResponse(
            responses=["Test response from AEC data model"],
            agent_type="aec_data_model",
            success=True
        )
        mock_strands.route_request.return_value = mock_response
        
        response = test_client.post(
            "/aec/chatbot/prompt",
            json={
                "prompt": "Test prompt",
                "element_group_id": "test_element_group"
            },
            headers={"Authorization": "Bearer test_token"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["responses"] == ["Test response from AEC data model"]
    
    def test_model_derivatives_endpoint_success(self, test_client, mock_strands):
        """Test the Model Derivatives endpoint with successful response."""
        # Mock successful response
        mock_response = AgentResponse(
            responses=["Test response from model derivatives"],
            agent_type="model_derivatives",
            success=True
        )
        mock_strands.route_request.return_value = mock_response
        
        response = test_client.post(
            "/derivatives/chatbot/prompt",
            json={
                "prompt": "Test prompt",
                "urn": "test_urn"
            },
            headers={"Authorization": "Bearer test_token"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["responses"] == ["Test response from model derivatives"]
    
    def test_generic_agent_endpoint_success(self, test_client, mock_strands):
        """Test the generic agent endpoint with successful response."""
        # Mock successful response
        mock_response = AgentResponse(
            responses=["Test response from generic agent"],
            agent_type="test_agent",
            success=True
        )
        mock_strands.route_request.return_value = mock_response
        
        response = test_client.post(
            "/agents/test_agent/prompt",
            json={"prompt": "Test prompt"},
            headers={"Authorization": "Bearer test_token"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["responses"] == ["Test response from generic agent"]
    
    def test_endpoint_with_agent_failure(self, test_client, mock_strands):
        """Test endpoint behavior when agent returns failure response."""
        # Mock failure response
        error_response = ErrorResponse(
            error_code="AGENT_ERROR",
            message="Agent processing failed"
        )
        mock_response = AgentResponse(
            responses=["Error occurred"],
            agent_type="model_properties",
            success=False,
            metadata={"error": error_response.to_dict()}
        )
        mock_strands.route_request.return_value = mock_response
        
        response = test_client.post(
            "/chatbot/prompt",
            json={
                "prompt": "Test prompt",
                "project_id": "test_project",
                "version_id": "test_version"
            },
            headers={"Authorization": "Bearer test_token"}
        )
        
        assert response.status_code == 500
        assert "Agent processing failed" in response.json()["detail"]
    
    def test_endpoint_with_orchestrator_exception(self, test_client, mock_strands):
        """Test endpoint behavior when orchestrator raises exception."""
        # Mock orchestrator exception
        mock_strands.route_request.side_effect = Exception("Orchestrator error")
        
        response = test_client.post(
            "/chatbot/prompt",
            json={
                "prompt": "Test prompt",
                "project_id": "test_project",
                "version_id": "test_version"
            },
            headers={"Authorization": "Bearer test_token"}
        )
        
        assert response.status_code == 500
        assert "Internal server error" in response.json()["detail"]
    
    def test_request_id_in_response_headers(self, test_client, mock_strands):
        """Test that request ID is included in response headers."""
        # Mock successful response
        mock_response = AgentResponse(
            responses=["Test response"],
            agent_type="model_properties",
            success=True
        )
        mock_strands.route_request.return_value = mock_response
        
        response = test_client.post(
            "/chatbot/prompt",
            json={
                "prompt": "Test prompt",
                "project_id": "test_project",
                "version_id": "test_version"
            },
            headers={"Authorization": "Bearer test_token"}
        )
        
        assert response.status_code == 200
        assert "X-Request-ID" in response.headers
        assert len(response.headers["X-Request-ID"]) > 0


class TestPayloadModels:
    """Test cases for payload models."""
    
    def test_model_properties_payload_valid(self):
        """Test ModelPropertiesPayload with valid data."""
        payload = ModelPropertiesPayload(
            prompt="Test prompt",
            project_id="test_project",
            version_id="test_version"
        )
        
        assert payload.prompt == "Test prompt"
        assert payload.project_id == "test_project"
        assert payload.version_id == "test_version"
    
    def test_model_properties_payload_missing_fields(self):
        """Test ModelPropertiesPayload with missing required fields."""
        with pytest.raises(ValueError):
            ModelPropertiesPayload(prompt="Test prompt")  # Missing project_id and version_id
    
    def test_aec_data_model_payload_valid(self):
        """Test AECDataModelPayload with valid data."""
        payload = AECDataModelPayload(
            prompt="Test prompt",
            element_group_id="test_element_group"
        )
        
        assert payload.prompt == "Test prompt"
        assert payload.element_group_id == "test_element_group"
    
    def test_model_derivatives_payload_valid(self):
        """Test ModelDerivativesPayload with valid data."""
        payload = ModelDerivativesPayload(
            prompt="Test prompt",
            urn="test_urn"
        )
        
        assert payload.prompt == "Test prompt"
        assert payload.urn == "test_urn"


if __name__ == "__main__":
    pytest.main([__file__])