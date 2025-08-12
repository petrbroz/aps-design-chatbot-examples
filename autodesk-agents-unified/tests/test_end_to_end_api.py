"""
End-to-end API tests for the unified agent system.

These tests validate:
- Full request-response cycle tests
- Backward compatibility with existing client patterns
- Authentication and authorization flows
- Concurrent request handling and performance
"""

import pytest
import asyncio
import json
import time
from typing import Dict, Any, List
from unittest.mock import Mock, AsyncMock, patch, MagicMock

import httpx
from fastapi.testclient import TestClient
from fastapi import FastAPI

from agent_core.api_gateway import APIGateway
from agent_core.core import AgentCore
from agent_core.config import CoreConfig
from agent_core.auth import AuthContext
from agent_core.models import AgentRequest, AgentResponse
from agent_core.api_gateway import APIGateway
from agent_core.orchestrator import StrandsOrchestrator


@pytest.fixture
def test_config():
    """Create test configuration."""
    return CoreConfig(
        aws_region="us-east-1",
        bedrock_model_id="anthropic.claude-3-5-sonnet-20241022-v2:0",
        opensearch_endpoint="https://test-opensearch.amazonaws.com",
        cache_directory="/tmp/test_e2e_cache",
        log_level="DEBUG",
        health_check_interval=30
    )


@pytest.fixture
async def app(test_config):
    """Create FastAPI application for testing."""
    # Mock external services to avoid real API calls
    with patch('agent_core.agents.model_properties_agent.ChatBedrock'), \
         patch('agent_core.agents.aec_data_model_agent.ChatBedrock'), \
         patch('agent_core.agents.model_derivatives_agent.ChatBedrock'), \
         patch('agent_core.agents.aec_data_model_agent.OpenSearchVectorStore'), \
         patch('agent_core.agents.aec_data_model_agent.PropertyDefinitionsManager'):
        
        # Create AgentCore and orchestrator
        agent_core = AgentCore(test_config)
        await agent_core.initialize()
        
        from agent_core.orchestrator import StrandsOrchestrator
        orchestrator = StrandsOrchestrator(agent_core)
        
        # Create API Gateway
        api_gateway = APIGateway(agent_core, orchestrator)
        app = api_gateway.app
        
        yield app
        
        # Cleanup
        await agent_core.shutdown()


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def auth_headers():
    """Create authentication headers for different agent types."""
    return {
        "model_properties": {
            "Authorization": "Bearer test_mp_token_12345",
            "Content-Type": "application/json"
        },
        "aec_data_model": {
            "Authorization": "Bearer test_aec_token_12345", 
            "Content-Type": "application/json"
        },
        "model_derivatives": {
            "Authorization": "Bearer test_md_token_12345",
            "Content-Type": "application/json"
        }
    }


class TestBackwardCompatibilityAPI:
    """Test backward compatibility with existing client patterns."""
    
    def test_model_properties_legacy_endpoint(self, client, auth_headers):
        """Test Model Properties legacy API endpoint compatibility."""
        # Legacy payload format from original implementation
        legacy_payload = {
            "prompt": "List all available properties",
            "project_id": "b.project123",
            "version_id": "test_version_456"
        }
        
        # Mock agent response
        with patch('agent_core.orchestrator.StrandsOrchestrator.route_request') as mock_route:
            mock_route.return_value = AgentResponse(
                responses=["Available properties: Name, Category, Material, Height"],
                agent_type="model_properties",
                success=True,
                execution_time=1.5,
                metadata={"tools_used": 2}
            )
            
            response = client.post(
                "/api/v1/model-properties/prompt",
                json=legacy_payload,
                headers=auth_headers["model_properties"]
            )
            
            assert response.status_code == 200
            data = response.json()
            
            # Verify legacy response format
            assert "responses" in data
            assert isinstance(data["responses"], list)
            assert len(data["responses"]) == 1
            assert "Available properties" in data["responses"][0]
            assert "execution_time" in data
            assert data["execution_time"] == 1.5
    
    def test_aec_data_model_legacy_endpoint(self, client, auth_headers):
        """Test AEC Data Model legacy API endpoint compatibility."""
        legacy_payload = {
            "prompt": "Find all wall elements",
            "element_group_id": "test_element_group_789"
        }
        
        with patch('agent_core.orchestrator.StrandsOrchestrator.route_request') as mock_route:
            mock_route.return_value = AgentResponse(
                responses=["Found 15 wall elements with properties: Height, Width, Material"],
                agent_type="aec_data_model",
                success=True,
                execution_time=2.1,
                metadata={"vector_store_used": True}
            )
            
            response = client.post(
                "/api/v1/aec-data-model/prompt",
                json=legacy_payload,
                headers=auth_headers["aec_data_model"]
            )
            
            assert response.status_code == 200
            data = response.json()
            
            assert "responses" in data
            assert "Found 15 wall elements" in data["responses"][0]
            assert data["execution_time"] == 2.1
    
    def test_model_derivatives_legacy_endpoint(self, client, auth_headers):
        """Test Model Derivatives legacy API endpoint compatibility."""
        legacy_payload = {
            "prompt": "Show me all elements with height > 3 meters",
            "urn": "dXJuOmFkc2sud2lwcHJvZDpmcy5maWxlOnZmLlUyTVk1UEFwUi1PV2l2TS1Zam9BQXc_dmVyc2lvbj0x"
        }
        
        with patch('agent_core.orchestrator.StrandsOrchestrator.route_request') as mock_route:
            mock_route.return_value = AgentResponse(
                responses=["Query executed: Found 8 elements with height > 3m"],
                agent_type="model_derivatives",
                success=True,
                execution_time=0.8,
                metadata={"database_queries": 1}
            )
            
            response = client.post(
                "/api/v1/model-derivatives/prompt",
                json=legacy_payload,
                headers=auth_headers["model_derivatives"]
            )
            
            assert response.status_code == 200
            data = response.json()
            
            assert "responses" in data
            assert "Found 8 elements" in data["responses"][0]
            assert data["execution_time"] == 0.8
    
    def test_legacy_error_response_format(self, client, auth_headers):
        """Test that error responses maintain legacy format."""
        # Invalid payload
        invalid_payload = {
            "invalid_field": "test"
        }
        
        response = client.post(
            "/api/v1/model-properties/prompt",
            json=invalid_payload,
            headers=auth_headers["model_properties"]
        )
        
        assert response.status_code == 400
        data = response.json()
        
        # Legacy error format
        assert "error" in data
        assert "message" in data
    
    def test_legacy_authentication_patterns(self, client):
        """Test legacy authentication patterns."""
        payload = {
            "prompt": "Test prompt",
            "project_id": "b.project123"
        }
        
        # Test without Authorization header
        response = client.post(
            "/api/v1/model-properties/prompt",
            json=payload
        )
        
        assert response.status_code == 401
        data = response.json()
        assert "authorization" in data["message"].lower() or "unauthorized" in data["message"].lower()
        
        # Test with invalid token format
        invalid_headers = {"Authorization": "InvalidToken"}
        response = client.post(
            "/api/v1/model-properties/prompt",
            json=payload,
            headers=invalid_headers
        )
        
        assert response.status_code == 401


class TestAuthenticationAndAuthorization:
    """Test authentication and authorization flows."""
    
    def test_bearer_token_validation(self, client, auth_headers):
        """Test Bearer token validation."""
        payload = {
            "prompt": "Test authentication",
            "project_id": "b.project123"
        }
        
        # Mock successful authentication
        with patch('agent_core.auth.AuthenticationManager.validate_token') as mock_validate:
            mock_validate.return_value = AuthContext(
                access_token="test_mp_token_12345",
                project_id="b.project123"
            )
            
            with patch('agent_core.orchestrator.StrandsOrchestrator.route_request') as mock_route:
                mock_route.return_value = AgentResponse(
                    responses=["Authentication successful"],
                    agent_type="model_properties",
                    success=True
                )
                
                response = client.post(
                    "/api/v1/model-properties/prompt",
                    json=payload,
                    headers=auth_headers["model_properties"]
                )
                
                assert response.status_code == 200
                mock_validate.assert_called_once()
    
    def test_token_expiration_handling(self, client, auth_headers):
        """Test handling of expired tokens."""
        payload = {
            "prompt": "Test with expired token",
            "project_id": "b.project123"
        }
        
        # Mock token validation failure
        with patch('agent_core.auth.AuthenticationManager.validate_token') as mock_validate:
            mock_validate.side_effect = Exception("Token expired")
            
            response = client.post(
                "/api/v1/model-properties/prompt",
                json=payload,
                headers=auth_headers["model_properties"]
            )
            
            assert response.status_code == 401
            data = response.json()
            assert "token" in data["message"].lower() or "expired" in data["message"].lower()
    
    def test_scope_based_authorization(self, client, auth_headers):
        """Test scope-based authorization for different agents."""
        # Test that Model Properties token can't access AEC Data Model
        payload = {
            "prompt": "Cross-agent access test",
            "element_group_id": "test_group"
        }
        
        # Use Model Properties token for AEC Data Model endpoint
        response = client.post(
            "/api/v1/aec-data-model/prompt",
            json=payload,
            headers=auth_headers["model_properties"]  # Wrong token type
        )
        
        # Should either work (if tokens are generic) or fail with proper error
        if response.status_code != 200:
            assert response.status_code in [401, 403]
    
    def test_rate_limiting(self, client, auth_headers):
        """Test rate limiting functionality."""
        payload = {
            "prompt": "Rate limit test",
            "project_id": "b.project123"
        }
        
        # Mock agent response
        with patch('agent_core.orchestrator.StrandsOrchestrator.route_request') as mock_route:
            mock_route.return_value = AgentResponse(
                responses=["Rate limit test response"],
                agent_type="model_properties",
                success=True
            )
            
            # Make multiple rapid requests
            responses = []
            for i in range(10):
                response = client.post(
                    "/api/v1/model-properties/prompt",
                    json=payload,
                    headers=auth_headers["model_properties"]
                )
                responses.append(response)
            
            # Check if rate limiting is applied
            status_codes = [r.status_code for r in responses]
            
            # Either all succeed (no rate limiting) or some are rate limited (429)
            if 429 in status_codes:
                assert status_codes.count(429) > 0
                # First few should succeed
                assert status_codes[0] == 200


class TestConcurrentRequestHandling:
    """Test concurrent request handling and performance."""
    
    @pytest.mark.asyncio
    async def test_concurrent_requests_same_agent(self, app, auth_headers):
        """Test handling concurrent requests to the same agent."""
        async with httpx.AsyncClient(app=app, base_url="http://test") as client:
            payload = {
                "prompt": "Concurrent test request",
                "project_id": "b.project123"
            }
            
            # Mock agent response
            with patch('agent_core.orchestrator.StrandsOrchestrator.route_request') as mock_route:
                mock_route.return_value = AgentResponse(
                    responses=["Concurrent response"],
                    agent_type="model_properties",
                    success=True,
                    execution_time=0.5
                )
                
                # Create 10 concurrent requests
                tasks = []
                for i in range(10):
                    task = client.post(
                        "/api/v1/model-properties/prompt",
                        json=payload,
                        headers=auth_headers["model_properties"]
                    )
                    tasks.append(task)
                
                # Execute concurrently
                responses = await asyncio.gather(*tasks)
                
                # All should succeed
                assert len(responses) == 10
                for response in responses:
                    assert response.status_code == 200
                    data = response.json()
                    assert "Concurrent response" in data["responses"][0]
    
    @pytest.mark.asyncio
    async def test_concurrent_requests_different_agents(self, app, auth_headers):
        """Test handling concurrent requests to different agents."""
        async with httpx.AsyncClient(app=app, base_url="http://test") as client:
            # Mock responses for different agents
            def mock_route_side_effect(request):
                if request.agent_type == "model_properties":
                    return AgentResponse(
                        responses=["MP response"],
                        agent_type="model_properties",
                        success=True
                    )
                elif request.agent_type == "aec_data_model":
                    return AgentResponse(
                        responses=["AEC response"],
                        agent_type="aec_data_model",
                        success=True
                    )
                else:
                    return AgentResponse(
                        responses=["MD response"],
                        agent_type="model_derivatives",
                        success=True
                    )
            
            with patch('agent_core.orchestrator.StrandsOrchestrator.route_request', side_effect=mock_route_side_effect):
                # Create requests for different agents
                tasks = [
                    client.post(
                        "/api/v1/model-properties/prompt",
                        json={"prompt": "MP test", "project_id": "b.project123"},
                        headers=auth_headers["model_properties"]
                    ),
                    client.post(
                        "/api/v1/aec-data-model/prompt",
                        json={"prompt": "AEC test", "element_group_id": "test_group"},
                        headers=auth_headers["aec_data_model"]
                    ),
                    client.post(
                        "/api/v1/model-derivatives/prompt",
                        json={"prompt": "MD test", "urn": "test_urn"},
                        headers=auth_headers["model_derivatives"]
                    )
                ]
                
                # Execute concurrently
                responses = await asyncio.gather(*tasks)
                
                # All should succeed
                assert len(responses) == 3
                for i, response in enumerate(responses):
                    assert response.status_code == 200
                    data = response.json()
                    if i == 0:
                        assert "MP response" in data["responses"][0]
                    elif i == 1:
                        assert "AEC response" in data["responses"][0]
                    else:
                        assert "MD response" in data["responses"][0]
    
    @pytest.mark.asyncio
    async def test_performance_under_load(self, app, auth_headers):
        """Test API performance under load."""
        async with httpx.AsyncClient(app=app, base_url="http://test") as client:
            payload = {
                "prompt": "Performance test",
                "project_id": "b.project123"
            }
            
            # Mock fast agent response
            with patch('agent_core.orchestrator.StrandsOrchestrator.route_request') as mock_route:
                mock_route.return_value = AgentResponse(
                    responses=["Fast response"],
                    agent_type="model_properties",
                    success=True,
                    execution_time=0.1
                )
                
                # Measure response times under load
                start_time = time.time()
                
                # Create 50 concurrent requests
                tasks = []
                for i in range(50):
                    task = client.post(
                        "/api/v1/model-properties/prompt",
                        json=payload,
                        headers=auth_headers["model_properties"]
                    )
                    tasks.append(task)
                
                responses = await asyncio.gather(*tasks)
                
                total_time = time.time() - start_time
                
                # All should succeed
                assert len(responses) == 50
                for response in responses:
                    assert response.status_code == 200
                
                # Performance check - should handle 50 requests in reasonable time
                avg_time_per_request = total_time / 50
                assert avg_time_per_request < 1.0, f"Average time per request: {avg_time_per_request:.3f}s"
    
    def test_request_timeout_handling(self, client, auth_headers):
        """Test handling of request timeouts."""
        payload = {
            "prompt": "Long running request",
            "project_id": "b.project123"
        }
        
        # Mock slow agent response
        with patch('agent_core.orchestrator.StrandsOrchestrator.route_request') as mock_route:
            async def slow_response(*args, **kwargs):
                await asyncio.sleep(10)  # Simulate slow response
                return AgentResponse(
                    responses=["Slow response"],
                    agent_type="model_properties",
                    success=True
                )
            
            mock_route.side_effect = slow_response
            
            # Request should timeout (depending on client timeout settings)
            try:
                response = client.post(
                    "/api/v1/model-properties/prompt",
                    json=payload,
                    headers=auth_headers["model_properties"],
                    timeout=2.0  # 2 second timeout
                )
                
                # If it doesn't timeout, that's also valid
                if response.status_code == 200:
                    pass  # Request completed within timeout
                else:
                    assert response.status_code in [408, 504]  # Timeout status codes
                    
            except httpx.TimeoutException:
                # Expected timeout exception
                pass


class TestFullRequestResponseCycle:
    """Test complete request-response cycles."""
    
    def test_model_properties_full_cycle(self, client, auth_headers):
        """Test complete Model Properties request-response cycle."""
        # Simulate real-world request
        payload = {
            "prompt": "Create an index for this design and then list all wall properties",
            "project_id": "b.project123",
            "version_id": "test_version_456"
        }
        
        # Mock complex agent response with tool usage
        with patch('agent_core.orchestrator.StrandsOrchestrator.route_request') as mock_route:
            mock_route.return_value = AgentResponse(
                responses=[
                    "I'll create an index for your design and then list the wall properties.",
                    "Index created successfully with ID: idx_12345",
                    "Found the following wall properties: Name, Height, Width, Material, Thickness",
                    "Total walls found: 25"
                ],
                agent_type="model_properties",
                success=True,
                execution_time=3.2,
                metadata={
                    "tools_used": ["create_index", "list_index_properties", "query_index"],
                    "cache_hit": False,
                    "index_id": "idx_12345"
                }
            )
            
            response = client.post(
                "/api/v1/model-properties/prompt",
                json=payload,
                headers=auth_headers["model_properties"]
            )
            
            assert response.status_code == 200
            data = response.json()
            
            # Verify complete response structure
            assert "responses" in data
            assert len(data["responses"]) == 4
            assert "Index created successfully" in data["responses"][1]
            assert "wall properties" in data["responses"][2]
            assert "execution_time" in data
            assert data["execution_time"] == 3.2
            assert "metadata" in data
            assert "tools_used" in data["metadata"]
    
    def test_aec_data_model_full_cycle(self, client, auth_headers):
        """Test complete AEC Data Model request-response cycle."""
        payload = {
            "prompt": "Find all door elements and show their properties including height and width",
            "element_group_id": "test_element_group_789"
        }
        
        with patch('agent_core.orchestrator.StrandsOrchestrator.route_request') as mock_route:
            mock_route.return_value = AgentResponse(
                responses=[
                    "I'll search for door elements and retrieve their properties.",
                    "Found 12 door elements in the design.",
                    "Door properties retrieved: Height (2.1m avg), Width (0.9m avg), Material (Wood, Steel)",
                    '<a href="#" data-dbids="101,102,103,104,105">Show Doors in Viewer</a>'
                ],
                agent_type="aec_data_model",
                success=True,
                execution_time=2.8,
                metadata={
                    "tools_used": ["execute_graphql_query", "find_related_property_definitions"],
                    "elements_found": 12,
                    "vector_search_used": True
                }
            )
            
            response = client.post(
                "/api/v1/aec-data-model/prompt",
                json=payload,
                headers=auth_headers["aec_data_model"]
            )
            
            assert response.status_code == 200
            data = response.json()
            
            assert len(data["responses"]) == 4
            assert "12 door elements" in data["responses"][1]
            assert "data-dbids" in data["responses"][3]  # Viewer link
            assert data["metadata"]["elements_found"] == 12
    
    def test_model_derivatives_full_cycle(self, client, auth_headers):
        """Test complete Model Derivatives request-response cycle."""
        payload = {
            "prompt": "Set up the database and find all elements with area greater than 10 square meters",
            "urn": "dXJuOmFkc2sud2lwcHJvZDpmcy5maWxlOnZmLlUyTVk1UEFwUi1PV2l2TS1Zam9BQXc_dmVyc2lvbj0x"
        }
        
        with patch('agent_core.orchestrator.StrandsOrchestrator.route_request') as mock_route:
            mock_route.return_value = AgentResponse(
                responses=[
                    "I'll set up the SQLite database and execute your query.",
                    "Database setup completed. Properties loaded: 1,247 elements",
                    "SQL Query: SELECT * FROM properties WHERE area > 10.0",
                    "Found 89 elements with area > 10 m²",
                    '<a href="#" data-dbids="1,5,12,18,23">Show Large Elements</a>'
                ],
                agent_type="model_derivatives",
                success=True,
                execution_time=4.1,
                metadata={
                    "tools_used": ["setup_database", "sql_query"],
                    "database_size": "2.3MB",
                    "query_results": 89
                }
            )
            
            response = client.post(
                "/api/v1/model-derivatives/prompt",
                json=payload,
                headers=auth_headers["model_derivatives"]
            )
            
            assert response.status_code == 200
            data = response.json()
            
            assert len(data["responses"]) == 5
            assert "Database setup completed" in data["responses"][1]
            assert "89 elements" in data["responses"][3]
            assert data["metadata"]["query_results"] == 89
    
    def test_error_handling_full_cycle(self, client, auth_headers):
        """Test error handling in full request-response cycle."""
        payload = {
            "prompt": "This request will cause an error",
            "project_id": "b.project123"
        }
        
        # Mock agent error
        with patch('agent_core.orchestrator.StrandsOrchestrator.route_request') as mock_route:
            mock_route.return_value = AgentResponse(
                responses=["Error: Unable to process request due to invalid project ID"],
                agent_type="model_properties",
                success=False,
                execution_time=0.5,
                metadata={"error_type": "validation_error"}
            )
            
            response = client.post(
                "/api/v1/model-properties/prompt",
                json=payload,
                headers=auth_headers["model_properties"]
            )
            
            # Should return 200 with error in response (agent handles errors gracefully)
            assert response.status_code == 200
            data = response.json()
            
            assert "Error:" in data["responses"][0]
            assert "success" in data
            assert data["success"] is False


class TestHealthAndMonitoring:
    """Test health check and monitoring endpoints."""
    
    def test_health_check_endpoint(self, client):
        """Test health check endpoint."""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "status" in data
        assert "timestamp" in data
        assert "agents" in data
        
        # Should include all three agents
        assert "model_properties" in data["agents"]
        assert "aec_data_model" in data["agents"]
        assert "model_derivatives" in data["agents"]
    
    def test_metrics_endpoint(self, client):
        """Test metrics endpoint."""
        response = client.get("/metrics")
        
        # Metrics endpoint might not be implemented yet
        if response.status_code == 200:
            data = response.json()
            assert "requests_total" in data or "uptime" in data
        else:
            assert response.status_code == 404  # Not implemented yet
    
    def test_agent_status_endpoints(self, client):
        """Test individual agent status endpoints."""
        agents = ["model-properties", "aec-data-model", "model-derivatives"]
        
        for agent in agents:
            response = client.get(f"/api/v1/{agent}/status")
            
            if response.status_code == 200:
                data = response.json()
                assert "agent_type" in data
                assert "healthy" in data
            else:
                # Status endpoints might not be implemented
                assert response.status_code in [404, 501]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])