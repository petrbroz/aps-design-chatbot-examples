"""
Strands orchestrator for agent management in the AgentCore framework.

This module provides the StrandsOrchestrator class that manages agent lifecycle,
routing, and coordination within the unified agent system.
"""

import asyncio
import time
from typing import Dict, List, Optional, Set
from datetime import datetime, timedelta
from dataclasses import dataclass

from .base_agent import BaseAgent
from .models import AgentRequest, AgentResponse, ErrorResponse, ErrorCode, AgentMetrics
from .auth import AuthContext


@dataclass
class AgentRegistration:
    """Information about a registered agent."""
    agent: BaseAgent
    registered_at: datetime
    last_health_check: Optional[datetime] = None
    health_status: bool = True
    consecutive_failures: int = 0


@dataclass
class RoutingRule:
    """Rule for routing requests to agents."""
    agent_type: str
    priority: int = 0
    conditions: Dict[str, any] = None
    
    def __post_init__(self):
        if self.conditions is None:
            self.conditions = {}


class AgentRouter:
    """
    Router for directing requests to appropriate agents.
    
    The router uses agent type and optional routing rules to determine
    which agent should handle a specific request.
    """
    
    def __init__(self):
        self._routing_rules: Dict[str, RoutingRule] = {}
        self._agent_types: Set[str] = set()
    
    def register_agent_type(self, agent_type: str, priority: int = 0, 
                           conditions: Optional[Dict[str, any]] = None) -> None:
        """
        Register an agent type with routing rules.
        
        Args:
            agent_type: The agent type identifier
            priority: Priority for routing (higher = more priority)
            conditions: Optional conditions for routing
        """
        self._agent_types.add(agent_type)
        self._routing_rules[agent_type] = RoutingRule(
            agent_type=agent_type,
            priority=priority,
            conditions=conditions or {}
        )
    
    def unregister_agent_type(self, agent_type: str) -> None:
        """
        Unregister an agent type.
        
        Args:
            agent_type: The agent type to unregister
        """
        self._agent_types.discard(agent_type)
        self._routing_rules.pop(agent_type, None)
    
    def route_request(self, request: AgentRequest) -> str:
        """
        Route a request to the appropriate agent type.
        
        Args:
            request: The agent request to route
            
        Returns:
            str: The agent type that should handle the request
            
        Raises:
            ValueError: If no suitable agent type is found
        """
        # Direct routing based on agent_type in request
        if request.agent_type in self._agent_types:
            return request.agent_type
        
        # If no direct match, check routing rules
        matching_rules = []
        for agent_type, rule in self._routing_rules.items():
            if self._matches_conditions(request, rule.conditions):
                matching_rules.append((agent_type, rule.priority))
        
        if not matching_rules:
            raise ValueError(f"No agent found for request type: {request.agent_type}")
        
        # Sort by priority (highest first) and return the best match
        matching_rules.sort(key=lambda x: x[1], reverse=True)
        return matching_rules[0][0]
    
    def _matches_conditions(self, request: AgentRequest, conditions: Dict[str, any]) -> bool:
        """
        Check if a request matches routing conditions.
        
        Args:
            request: The request to check
            conditions: The conditions to match against
            
        Returns:
            bool: True if request matches conditions
        """
        if not conditions:
            return True
        
        # Check context conditions
        if "context" in conditions:
            for key, value in conditions["context"].items():
                if request.context.get(key) != value:
                    return False
        
        # Check metadata conditions
        if "metadata" in conditions:
            for key, value in conditions["metadata"].items():
                if request.metadata.get(key) != value:
                    return False
        
        # Check prompt patterns
        if "prompt_contains" in conditions:
            patterns = conditions["prompt_contains"]
            if isinstance(patterns, str):
                patterns = [patterns]
            if not any(pattern.lower() in request.prompt.lower() for pattern in patterns):
                return False
        
        return True
    
    def get_registered_types(self) -> List[str]:
        """Get list of registered agent types."""
        return list(self._agent_types)
    
    def get_routing_rules(self) -> Dict[str, RoutingRule]:
        """Get current routing rules."""
        return self._routing_rules.copy()


class StrandsOrchestrator:
    """
    Main orchestrator for managing agents in the Strands architecture.
    
    The orchestrator handles agent registration, lifecycle management,
    request routing, and health monitoring.
    """
    
    def __init__(self, agent_core: 'AgentCore', health_check_interval: int = 30):
        """
        Initialize the Strands orchestrator.
        
        Args:
            agent_core: The AgentCore instance providing common services
            health_check_interval: Interval in seconds for health checks
        """
        self.agent_core = agent_core
        self.health_check_interval = health_check_interval
        
        # Agent management
        self._agents: Dict[str, AgentRegistration] = {}
        self._router = AgentRouter()
        
        # Lifecycle management
        self._initialized = False
        self._shutdown_event = asyncio.Event()
        self._health_check_task: Optional[asyncio.Task] = None
        
        # Metrics
        self._total_requests = 0
        self._successful_requests = 0
        self._failed_requests = 0
        self._start_time = datetime.utcnow()
    
    async def initialize(self) -> None:
        """Initialize the orchestrator and start background tasks."""
        if self._initialized:
            return
        
        self.agent_core.logger.info("Initializing Strands orchestrator")
        
        # Start health check task
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        
        self._initialized = True
        self.agent_core.logger.info("Strands orchestrator initialized successfully")
    
    async def shutdown(self) -> None:
        """Shutdown the orchestrator and all registered agents."""
        if not self._initialized:
            return
        
        self.agent_core.logger.info("Shutting down Strands orchestrator")
        
        # Signal shutdown
        self._shutdown_event.set()
        
        # Cancel health check task
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        
        # Shutdown all agents
        shutdown_tasks = []
        for agent_type, registration in self._agents.items():
            self.agent_core.logger.info(f"Shutting down agent: {agent_type}")
            shutdown_tasks.append(registration.agent.shutdown())
        
        if shutdown_tasks:
            await asyncio.gather(*shutdown_tasks, return_exceptions=True)
        
        self._agents.clear()
        self._initialized = False
        self.agent_core.logger.info("Strands orchestrator shutdown completed")
    
    async def register_agent(self, agent: BaseAgent) -> None:
        """
        Register an agent with the orchestrator.
        
        Args:
            agent: The agent instance to register
            
        Raises:
            ValueError: If agent type is already registered
        """
        agent_type = agent.get_agent_type()
        
        if agent_type in self._agents:
            raise ValueError(f"Agent type '{agent_type}' is already registered")
        
        self.agent_core.logger.info(f"Registering agent: {agent_type}")
        
        # Initialize the agent
        await agent.initialize()
        
        # Register with router
        self._router.register_agent_type(agent_type)
        
        # Store registration
        self._agents[agent_type] = AgentRegistration(
            agent=agent,
            registered_at=datetime.utcnow()
        )
        
        self.agent_core.logger.info(f"Agent registered successfully: {agent_type}")
    
    async def unregister_agent(self, agent_type: str) -> None:
        """
        Unregister an agent from the orchestrator.
        
        Args:
            agent_type: The agent type to unregister
            
        Raises:
            ValueError: If agent type is not registered
        """
        if agent_type not in self._agents:
            raise ValueError(f"Agent type '{agent_type}' is not registered")
        
        self.agent_core.logger.info(f"Unregistering agent: {agent_type}")
        
        registration = self._agents[agent_type]
        
        # Shutdown the agent
        await registration.agent.shutdown()
        
        # Unregister from router
        self._router.unregister_agent_type(agent_type)
        
        # Remove registration
        del self._agents[agent_type]
        
        self.agent_core.logger.info(f"Agent unregistered successfully: {agent_type}")
    
    async def route_request(self, request: AgentRequest) -> AgentResponse:
        """
        Route a request to the appropriate agent and return the response.
        
        Args:
            request: The agent request to process
            
        Returns:
            AgentResponse: The response from the agent
            
        Raises:
            ValueError: If no suitable agent is found
        """
        start_time = time.time()
        self._total_requests += 1
        
        try:
            # Route the request
            agent_type = self._router.route_request(request)
            
            # Get the agent
            if agent_type not in self._agents:
                raise ValueError(f"Agent '{agent_type}' is not registered")
            
            registration = self._agents[agent_type]
            
            # Check agent health
            if not registration.health_status:
                raise ValueError(f"Agent '{agent_type}' is unhealthy")
            
            self.agent_core.logger.debug(
                f"Routing request to agent: {agent_type}",
                agent_type=agent_type,
                request_id=request.request_id
            )
            
            # Process the request
            response = await registration.agent.handle_request(request)
            
            # Update metrics
            if response.success:
                self._successful_requests += 1
            else:
                self._failed_requests += 1
            
            execution_time = time.time() - start_time
            self.agent_core.logger.info(
                f"Request processed successfully",
                agent_type=agent_type,
                request_id=request.request_id,
                execution_time=execution_time,
                success=response.success
            )
            
            return response
            
        except Exception as e:
            self._failed_requests += 1
            execution_time = time.time() - start_time
            
            self.agent_core.logger.error(
                f"Request routing failed",
                request_id=request.request_id,
                execution_time=execution_time,
                error=str(e)
            )
            
            # Return error response
            error_response = ErrorResponse.from_exception(
                e,
                ErrorCode.AGENT_NOT_FOUND if "not registered" in str(e) else ErrorCode.INTERNAL_ERROR,
                request_id=request.request_id
            )
            
            return AgentResponse(
                responses=[f"Error: {error_response.message}"],
                metadata={"error": error_response.to_dict()},
                execution_time=execution_time,
                agent_type=request.agent_type,
                request_id=request.request_id,
                success=False
            )
    
    async def get_agent_status(self, agent_type: str) -> Dict[str, any]:
        """
        Get status information for a specific agent.
        
        Args:
            agent_type: The agent type to get status for
            
        Returns:
            Dict containing agent status information
            
        Raises:
            ValueError: If agent type is not registered
        """
        if agent_type not in self._agents:
            raise ValueError(f"Agent type '{agent_type}' is not registered")
        
        registration = self._agents[agent_type]
        agent_status = await registration.agent.get_status()
        
        return {
            **agent_status,
            "registration": {
                "registered_at": registration.registered_at.isoformat(),
                "last_health_check": registration.last_health_check.isoformat() if registration.last_health_check else None,
                "health_status": registration.health_status,
                "consecutive_failures": registration.consecutive_failures
            }
        }
    
    async def get_orchestrator_status(self) -> Dict[str, any]:
        """
        Get comprehensive orchestrator status.
        
        Returns:
            Dict containing orchestrator status information
        """
        uptime = (datetime.utcnow() - self._start_time).total_seconds()
        success_rate = (self._successful_requests / self._total_requests * 100.0) if self._total_requests > 0 else 0.0
        
        agent_statuses = {}
        for agent_type in self._agents:
            try:
                agent_statuses[agent_type] = await self.get_agent_status(agent_type)
            except Exception as e:
                agent_statuses[agent_type] = {"error": str(e)}
        
        return {
            "initialized": self._initialized,
            "uptime_seconds": uptime,
            "registered_agents": list(self._agents.keys()),
            "agent_count": len(self._agents),
            "metrics": {
                "total_requests": self._total_requests,
                "successful_requests": self._successful_requests,
                "failed_requests": self._failed_requests,
                "success_rate": success_rate
            },
            "routing": {
                "registered_types": self._router.get_registered_types(),
                "routing_rules": {k: {"priority": v.priority, "conditions": v.conditions} 
                                for k, v in self._router.get_routing_rules().items()}
            },
            "agents": agent_statuses
        }
    
    async def health_check(self, agent_type: Optional[str] = None) -> Dict[str, bool]:
        """
        Perform health check on agents.
        
        Args:
            agent_type: Optional specific agent type to check, or None for all
            
        Returns:
            Dict mapping agent types to health status
        """
        results = {}
        
        agents_to_check = [agent_type] if agent_type else list(self._agents.keys())
        
        for agent_type in agents_to_check:
            if agent_type not in self._agents:
                results[agent_type] = False
                continue
            
            registration = self._agents[agent_type]
            
            try:
                # Check if agent is healthy
                is_healthy = registration.agent.is_healthy()
                
                # Update registration
                registration.last_health_check = datetime.utcnow()
                
                if is_healthy:
                    registration.health_status = True
                    registration.consecutive_failures = 0
                else:
                    registration.consecutive_failures += 1
                    # Mark as unhealthy after 3 consecutive failures
                    if registration.consecutive_failures >= 3:
                        registration.health_status = False
                
                results[agent_type] = registration.health_status
                
            except Exception as e:
                self.agent_core.logger.error(
                    f"Health check failed for agent {agent_type}",
                    agent_type=agent_type,
                    error=str(e)
                )
                
                registration.consecutive_failures += 1
                registration.last_health_check = datetime.utcnow()
                
                if registration.consecutive_failures >= 3:
                    registration.health_status = False
                
                results[agent_type] = False
        
        return results
    
    def get_registered_agents(self) -> List[str]:
        """Get list of registered agent types."""
        return list(self._agents.keys())
    
    def is_agent_registered(self, agent_type: str) -> bool:
        """Check if an agent type is registered."""
        return agent_type in self._agents
    
    def get_agent(self, agent_type: str) -> Optional[BaseAgent]:
        """Get a registered agent by type."""
        registration = self._agents.get(agent_type)
        return registration.agent if registration else None
    
    async def _health_check_loop(self) -> None:
        """Background task for periodic health checks."""
        while not self._shutdown_event.is_set():
            try:
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=self.health_check_interval
                )
                break  # Shutdown was signaled
            except asyncio.TimeoutError:
                # Perform health checks
                if self._agents:
                    try:
                        await self.health_check()
                    except Exception as e:
                        self.agent_core.logger.error(
                            "Error during periodic health check",
                            error=str(e)
                        )