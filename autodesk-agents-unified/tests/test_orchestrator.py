"""
Unit tests for the Strands orchestrator functionality.
"""

import asyncio
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, Any

from agent_core.orchestrator import StrandsOrchestrator, AgentRouter, AgentRegistration, RoutingRule
from agent_core.base_agent import BaseAgent, BaseTool
from agent_core.models import AgentRequest, AgentResponse, ErrorResponse, ErrorCode, ToolResult
from agent_core.auth import AuthContext


class MockTool(BaseTool):
    """Mock tool for testing."""
    
    def __init__(self, name: str = "mock_tool"):
        super().__init__(name, f"Mock tool: {name}")
    
    async def execute(self, **kwargs) -> ToolResult:
        return ToolResult(
            tool_name=self.name,
            success=True,
            result=f"Mock result from {self.name}",
            metadata=kwargs
        )
    
    def _get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "param1": {"type": "string"},
                "param2": {"type": "integer"}
            }
        }


class MockAgent(BaseAgent):
    """Mock agent for testing."""
    
    def __init__(self, agent_core, agent_type: str = "mock_agent", tools=None):
        self._agent_type = agent_type
        super().__init__(agent_core, tools or [MockTool()])
        self._process_prompt_mock = None
    
    async def process_prompt(self, request: AgentRequest) -> AgentResponse:
        """Mock implementation of process_prompt."""
        if self._process_prompt_mock:
            return await self._process_prompt_mock(request)
        
        return AgentResponse(
            responses=[f"Mock response from {self._agent_type}"],
            agent_type=self._agent_type,
            request_id=request.request_id,
            success=True
        )
    
    def get_agent_type(self) -> str:
        return self._agent_type


@pytest.fixture
def mock_agent_core():
    """Create a mock AgentCore instance."""
    agent_core = Mock()
    agent_core.logger = Mock()
    agent_core.logger.info = Mock()
    agent_core.logger.debug = Mock()
    agent_core.logger.error = Mock()
    agent_core.logger.warning = Mock()
    agent_core.auth_manager = Mock()
    agent_core.auth_manager.enabled = False
    agent_core.is_healthy = Mock(return_value=True)
    return agent_core


@pytest.fixture
def orchestrator(mock_agent_core):
    """Create a StrandsOrchestrator instance for testing."""
    return StrandsOrchestrator(mock_agent_core, health_check_interval=1)


@pytest.fixture
def mock_agent(mock_agent_core):
    """Create a mock agent for testing."""
    return MockAgent(mock_agent_core, "test_agent")


@pytest.fixture
def sample_request():
    """Create a sample agent request."""
    return AgentRequest(
        agent_type="test_agent",
        prompt="Test prompt",
        context={"key": "value"},
        request_id="test-request-123"
    )


class TestAgentRouter:
    """Test cases for AgentRouter."""
    
    def test_router_initialization(self):
        """Test router initialization."""
        router = AgentRouter()
        assert router.get_registered_types() == []
        assert router.get_routing_rules() == {}
    
    def test_register_agent_type(self):
        """Test agent type registration."""
        router = AgentRouter()
        router.register_agent_type("test_agent", priority=10, conditions={"context": {"env": "test"}})
        
        types = router.get_registered_types()
        assert "test_agent" in types
        
        rules = router.get_routing_rules()
        assert "test_agent" in rules
        assert rules["test_agent"].priority == 10
        assert rules["test_agent"].conditions == {"context": {"env": "test"}}
    
    def test_unregister_agent_type(self):
        """Test agent type unregistration."""
        router = AgentRouter()
        router.register_agent_type("test_agent")
        
        assert "test_agent" in router.get_registered_types()
        
        router.unregister_agent_type("test_agent")
        assert "test_agent" not in router.get_registered_types()
        assert "test_agent" not in router.get_routing_rules()
    
    def test_route_request_direct_match(self):
        """Test routing with direct agent type match."""
        router = AgentRouter()
        router.register_agent_type("test_agent")
        
        request = AgentRequest(agent_type="test_agent", prompt="test")
        result = router.route_request(request)
        
        assert result == "test_agent"
    
    def test_route_request_no_match(self):
        """Test routing with no matching agent type."""
        router = AgentRouter()
        
        request = AgentRequest(agent_type="unknown_agent", prompt="test")
        
        with pytest.raises(ValueError, match="No agent found for request type"):
            router.route_request(request)
    
    def test_route_request_with_conditions(self):
        """Test routing with conditions."""
        router = AgentRouter()
        router.register_agent_type("agent1", priority=1, conditions={"context": {"env": "prod"}})
        router.register_agent_type("agent2", priority=2, conditions={"context": {"env": "test"}})
        
        # Request matching agent2 conditions
        request = AgentRequest(
            agent_type="unknown",
            prompt="test",
            context={"env": "test"}
        )
        
        result = router.route_request(request)
        assert result == "agent2"  # Higher priority
    
    def test_matches_conditions_context(self):
        """Test condition matching for context."""
        router = AgentRouter()
        
        request = AgentRequest(
            agent_type="test",
            prompt="test",
            context={"env": "prod", "version": "1.0"}
        )
        
        # Matching conditions
        assert router._matches_conditions(request, {"context": {"env": "prod"}})
        assert router._matches_conditions(request, {"context": {"env": "prod", "version": "1.0"}})
        
        # Non-matching conditions
        assert not router._matches_conditions(request, {"context": {"env": "test"}})
        assert not router._matches_conditions(request, {"context": {"env": "prod", "version": "2.0"}})
    
    def test_matches_conditions_prompt_contains(self):
        """Test condition matching for prompt content."""
        router = AgentRouter()
        
        request = AgentRequest(agent_type="test", prompt="Create an index for model properties")
        
        # Matching conditions
        assert router._matches_conditions(request, {"prompt_contains": "index"})
        assert router._matches_conditions(request, {"prompt_contains": ["model", "properties"]})
        
        # Non-matching conditions
        assert not router._matches_conditions(request, {"prompt_contains": "database"})
        assert not router._matches_conditions(request, {"prompt_contains": ["sql", "query"]})


class TestStrandsOrchestrator:
    """Test cases for StrandsOrchestrator."""
    
    @pytest.mark.asyncio
    async def test_orchestrator_initialization(self, orchestrator):
        """Test orchestrator initialization."""
        assert not orchestrator._initialized
        
        await orchestrator.initialize()
        assert orchestrator._initialized
        
        await orchestrator.shutdown()
        assert not orchestrator._initialized
    
    @pytest.mark.asyncio
    async def test_register_agent(self, orchestrator, mock_agent):
        """Test agent registration."""
        await orchestrator.initialize()
        
        assert not orchestrator.is_agent_registered("test_agent")
        
        await orchestrator.register_agent(mock_agent)
        
        assert orchestrator.is_agent_registered("test_agent")
        assert "test_agent" in orchestrator.get_registered_agents()
        assert orchestrator.get_agent("test_agent") == mock_agent
        
        await orchestrator.shutdown()
    
    @pytest.mark.asyncio
    async def test_register_duplicate_agent(self, orchestrator, mock_agent_core):
        """Test registering duplicate agent type."""
        await orchestrator.initialize()
        
        agent1 = MockAgent(mock_agent_core, "duplicate_agent")
        agent2 = MockAgent(mock_agent_core, "duplicate_agent")
        
        await orchestrator.register_agent(agent1)
        
        with pytest.raises(ValueError, match="already registered"):
            await orchestrator.register_agent(agent2)
        
        await orchestrator.shutdown()
    
    @pytest.mark.asyncio
    async def test_unregister_agent(self, orchestrator, mock_agent):
        """Test agent unregistration."""
        await orchestrator.initialize()
        await orchestrator.register_agent(mock_agent)
        
        assert orchestrator.is_agent_registered("test_agent")
        
        await orchestrator.unregister_agent("test_agent")
        
        assert not orchestrator.is_agent_registered("test_agent")
        assert "test_agent" not in orchestrator.get_registered_agents()
        
        await orchestrator.shutdown()
    
    @pytest.mark.asyncio
    async def test_unregister_nonexistent_agent(self, orchestrator):
        """Test unregistering non-existent agent."""
        await orchestrator.initialize()
        
        with pytest.raises(ValueError, match="not registered"):
            await orchestrator.unregister_agent("nonexistent_agent")
        
        await orchestrator.shutdown()
    
    @pytest.mark.asyncio
    async def test_route_request_success(self, orchestrator, mock_agent, sample_request):
        """Test successful request routing."""
        await orchestrator.initialize()
        await orchestrator.register_agent(mock_agent)
        
        response = await orchestrator.route_request(sample_request)
        
        assert response.success
        assert response.agent_type == "test_agent"
        assert response.request_id == "test-request-123"
        assert len(response.responses) > 0
        
        await orchestrator.shutdown()
    
    @pytest.mark.asyncio
    async def test_route_request_agent_not_registered(self, orchestrator, sample_request):
        """Test routing to unregistered agent."""
        await orchestrator.initialize()
        
        response = await orchestrator.route_request(sample_request)
        
        assert not response.success
        assert "No agent found for request type" in response.responses[0]
        assert "error" in response.metadata
        
        await orchestrator.shutdown()
    
    @pytest.mark.asyncio
    async def test_route_request_unhealthy_agent(self, orchestrator, mock_agent, sample_request):
        """Test routing to unhealthy agent."""
        await orchestrator.initialize()
        await orchestrator.register_agent(mock_agent)
        
        # Mark agent as unhealthy
        orchestrator._agents["test_agent"].health_status = False
        
        response = await orchestrator.route_request(sample_request)
        
        assert not response.success
        assert "unhealthy" in response.responses[0]
        
        await orchestrator.shutdown()
    
    @pytest.mark.asyncio
    async def test_get_agent_status(self, orchestrator, mock_agent):
        """Test getting agent status."""
        await orchestrator.initialize()
        await orchestrator.register_agent(mock_agent)
        
        status = await orchestrator.get_agent_status("test_agent")
        
        assert status["agent_type"] == "test_agent"
        assert status["initialized"] == True
        assert "registration" in status
        assert "registered_at" in status["registration"]
        assert status["registration"]["health_status"] == True
        
        await orchestrator.shutdown()
    
    @pytest.mark.asyncio
    async def test_get_agent_status_not_registered(self, orchestrator):
        """Test getting status for unregistered agent."""
        await orchestrator.initialize()
        
        with pytest.raises(ValueError, match="not registered"):
            await orchestrator.get_agent_status("nonexistent_agent")
        
        await orchestrator.shutdown()
    
    @pytest.mark.asyncio
    async def test_get_orchestrator_status(self, orchestrator, mock_agent):
        """Test getting orchestrator status."""
        await orchestrator.initialize()
        await orchestrator.register_agent(mock_agent)
        
        status = await orchestrator.get_orchestrator_status()
        
        assert status["initialized"] == True
        assert status["agent_count"] == 1
        assert "test_agent" in status["registered_agents"]
        assert "metrics" in status
        assert "routing" in status
        assert "agents" in status
        
        await orchestrator.shutdown()
    
    @pytest.mark.asyncio
    async def test_health_check_all_agents(self, orchestrator, mock_agent_core):
        """Test health check for all agents."""
        await orchestrator.initialize()
        
        agent1 = MockAgent(mock_agent_core, "agent1")
        agent2 = MockAgent(mock_agent_core, "agent2")
        
        await orchestrator.register_agent(agent1)
        await orchestrator.register_agent(agent2)
        
        results = await orchestrator.health_check()
        
        assert len(results) == 2
        assert results["agent1"] == True
        assert results["agent2"] == True
        
        await orchestrator.shutdown()
    
    @pytest.mark.asyncio
    async def test_health_check_specific_agent(self, orchestrator, mock_agent):
        """Test health check for specific agent."""
        await orchestrator.initialize()
        await orchestrator.register_agent(mock_agent)
        
        results = await orchestrator.health_check("test_agent")
        
        assert len(results) == 1
        assert results["test_agent"] == True
        
        await orchestrator.shutdown()
    
    @pytest.mark.asyncio
    async def test_health_check_unhealthy_agent(self, orchestrator, mock_agent):
        """Test health check with unhealthy agent."""
        await orchestrator.initialize()
        await orchestrator.register_agent(mock_agent)
        
        # Mock agent as unhealthy
        mock_agent.is_healthy = Mock(return_value=False)
        
        # First few checks should still return True (consecutive failures needed)
        results = await orchestrator.health_check("test_agent")
        assert results["test_agent"] == True
        
        results = await orchestrator.health_check("test_agent")
        assert results["test_agent"] == True
        
        # Third consecutive failure should mark as unhealthy
        results = await orchestrator.health_check("test_agent")
        assert results["test_agent"] == False
        
        await orchestrator.shutdown()
    
    @pytest.mark.asyncio
    async def test_health_check_nonexistent_agent(self, orchestrator):
        """Test health check for non-existent agent."""
        await orchestrator.initialize()
        
        results = await orchestrator.health_check("nonexistent_agent")
        
        assert results["nonexistent_agent"] == False
        
        await orchestrator.shutdown()
    
    @pytest.mark.asyncio
    async def test_metrics_tracking(self, orchestrator, mock_agent, sample_request):
        """Test metrics tracking during request processing."""
        await orchestrator.initialize()
        await orchestrator.register_agent(mock_agent)
        
        # Process successful request
        response = await orchestrator.route_request(sample_request)
        assert response.success
        
        status = await orchestrator.get_orchestrator_status()
        metrics = status["metrics"]
        
        assert metrics["total_requests"] == 1
        assert metrics["successful_requests"] == 1
        assert metrics["failed_requests"] == 0
        assert metrics["success_rate"] == 100.0
        
        await orchestrator.shutdown()
    
    @pytest.mark.asyncio
    async def test_metrics_tracking_failures(self, orchestrator, sample_request):
        """Test metrics tracking with failed requests."""
        await orchestrator.initialize()
        
        # Process request without registered agent (should fail)
        response = await orchestrator.route_request(sample_request)
        assert not response.success
        
        status = await orchestrator.get_orchestrator_status()
        metrics = status["metrics"]
        
        assert metrics["total_requests"] == 1
        assert metrics["successful_requests"] == 0
        assert metrics["failed_requests"] == 1
        assert metrics["success_rate"] == 0.0
        
        await orchestrator.shutdown()
    
    @pytest.mark.asyncio
    async def test_shutdown_with_agents(self, orchestrator, mock_agent_core):
        """Test orchestrator shutdown with registered agents."""
        await orchestrator.initialize()
        
        agent1 = MockAgent(mock_agent_core, "agent1")
        agent2 = MockAgent(mock_agent_core, "agent2")
        
        await orchestrator.register_agent(agent1)
        await orchestrator.register_agent(agent2)
        
        assert len(orchestrator.get_registered_agents()) == 2
        
        await orchestrator.shutdown()
        
        assert len(orchestrator.get_registered_agents()) == 0
        assert not orchestrator._initialized
    
    @pytest.mark.asyncio
    async def test_health_check_loop_integration(self, mock_agent_core):
        """Test health check loop integration."""
        # Use very short interval for testing
        orchestrator = StrandsOrchestrator(mock_agent_core, health_check_interval=0.1)
        
        await orchestrator.initialize()
        
        agent = MockAgent(mock_agent_core, "test_agent")
        await orchestrator.register_agent(agent)
        
        # Wait for at least one health check cycle
        await asyncio.sleep(0.2)
        
        # Verify health check was performed
        registration = orchestrator._agents["test_agent"]
        assert registration.last_health_check is not None
        
        await orchestrator.shutdown()


class TestAgentRegistration:
    """Test cases for AgentRegistration dataclass."""
    
    def test_agent_registration_creation(self, mock_agent):
        """Test AgentRegistration creation."""
        registration = AgentRegistration(
            agent=mock_agent,
            registered_at=datetime.utcnow()
        )
        
        assert registration.agent == mock_agent
        assert registration.last_health_check is None
        assert registration.health_status == True
        assert registration.consecutive_failures == 0


class TestRoutingRule:
    """Test cases for RoutingRule dataclass."""
    
    def test_routing_rule_creation(self):
        """Test RoutingRule creation."""
        rule = RoutingRule(
            agent_type="test_agent",
            priority=10,
            conditions={"context": {"env": "prod"}}
        )
        
        assert rule.agent_type == "test_agent"
        assert rule.priority == 10
        assert rule.conditions == {"context": {"env": "prod"}}
    
    def test_routing_rule_default_conditions(self):
        """Test RoutingRule with default conditions."""
        rule = RoutingRule(agent_type="test_agent")
        
        assert rule.agent_type == "test_agent"
        assert rule.priority == 0
        assert rule.conditions == {}


if __name__ == "__main__":
    pytest.main([__file__])