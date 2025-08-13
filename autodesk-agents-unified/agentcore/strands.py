"""
Strands Orchestrator for AgentCore

Manages agent lifecycle, routing requests to appropriate agents,
and handling inter-agent communication and coordination.
"""

import asyncio
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass
from enum import Enum
import uuid

from .models import AgentRequest, AgentResponse, ErrorCodes, AgentType
from .base_agent import BaseAgent
from .logging import StructuredLogger, TraceContext


class AgentStatus(Enum):
    """Agent status in the orchestrator."""
    INITIALIZING = "initializing"
    READY = "ready"
    BUSY = "busy"
    ERROR = "error"
    SHUTDOWN = "shutdown"


@dataclass
class AgentInfo:
    """Information about a registered agent."""
    agent: BaseAgent
    status: AgentStatus
    request_count: int = 0
    error_count: int = 0
    last_request_time: Optional[float] = None
    concurrent_requests: int = 0
    max_concurrent: int = 10


class AgentRouter:
    """
    Routes requests to appropriate agents based on agent type and load.
    """
    
    def __init__(self, logger: StructuredLogger):
        """Initialize agent router."""
        self.logger = logger
        self._routing_rules: Dict[str, str] = {}
        self._load_balancing_enabled = True
    
    def add_routing_rule(self, pattern: str, agent_type: str) -> None:
        """Add a routing rule for request patterns."""
        self._routing_rules[pattern] = agent_type
        self.logger.info(f"Routing rule added: {pattern} -> {agent_type}")
    
    def route_request(self, request: AgentRequest, 
                     available_agents: Dict[str, AgentInfo]) -> Optional[str]:
        """
        Route request to appropriate agent.
        
        Args:
            request: The incoming request
            available_agents: Dictionary of available agents
            
        Returns:
            Agent type to handle the request, or None if no suitable agent
        """
        # First, try direct agent type match
        if request.agent_type in available_agents:
            agent_info = available_agents[request.agent_type]
            if (agent_info.status == AgentStatus.READY and 
                agent_info.concurrent_requests < agent_info.max_concurrent):
                return request.agent_type
        
        # Check routing rules based on prompt content
        for pattern, agent_type in self._routing_rules.items():
            if pattern.lower() in request.prompt.lower():
                if (agent_type in available_agents and 
                    available_agents[agent_type].status == AgentStatus.READY):
                    return agent_type
        
        # If load balancing is enabled, find least loaded agent of requested type
        if self._load_balancing_enabled:
            candidates = [
                (agent_type, info) for agent_type, info in available_agents.items()
                if (info.status == AgentStatus.READY and 
                    info.concurrent_requests < info.max_concurrent)
            ]
            
            if candidates:
                # Sort by concurrent requests (ascending)
                candidates.sort(key=lambda x: x[1].concurrent_requests)
                return candidates[0][0]
        
        return None


class StrandsOrchestrator:
    """
    Strands orchestrator for managing multiple agents.
    
    Handles agent registration, lifecycle management, request routing,
    and coordination between agents.
    """
    
    def __init__(self, agent_core):
        """Initialize Strands orchestrator."""
        self.agent_core = agent_core
        self.logger = agent_core.logger
        
        # Agent management
        self._agents: Dict[str, AgentInfo] = {}
        self._router = AgentRouter(self.logger)
        
        # Request tracking
        self._active_requests: Dict[str, Dict[str, Any]] = {}
        self._request_history: List[Dict[str, Any]] = []
        self._max_history = 1000
        
        # Orchestrator state
        self._initialized = False
        self._shutdown_event = asyncio.Event()
        
        # Performance tracking
        self._total_requests = 0
        self._total_errors = 0
        self._total_execution_time = 0.0
    
    async def initialize(self) -> None:
        """Initialize the orchestrator."""
        if self._initialized:
            return
        
        self.logger.info("Initializing Strands orchestrator")
        
        # Set up default routing rules
        self._setup_default_routing()
        
        self._initialized = True
        self.logger.info("Strands orchestrator initialized")
    
    def _setup_default_routing(self) -> None:
        """Set up default routing rules."""
        # Model Properties patterns
        self._router.add_routing_rule("properties", AgentType.MODEL_PROPERTIES.value)
        self._router.add_routing_rule("index", AgentType.MODEL_PROPERTIES.value)
        self._router.add_routing_rule("query", AgentType.MODEL_PROPERTIES.value)
        
        # AEC Data Model patterns
        self._router.add_routing_rule("element", AgentType.AEC_DATA_MODEL.value)
        self._router.add_routing_rule("category", AgentType.AEC_DATA_MODEL.value)
        self._router.add_routing_rule("graphql", AgentType.AEC_DATA_MODEL.value)
        
        # Model Derivatives patterns
        self._router.add_routing_rule("sql", AgentType.MODEL_DERIVATIVES.value)
        self._router.add_routing_rule("database", AgentType.MODEL_DERIVATIVES.value)
        self._router.add_routing_rule("derivative", AgentType.MODEL_DERIVATIVES.value)
    
    async def register_agent(self, agent_type: str, agent: BaseAgent) -> None:
        """
        Register an agent with the orchestrator.
        
        Args:
            agent_type: Type identifier for the agent
            agent: The agent instance to register
        """
        if not self._initialized:
            await self.initialize()
        
        self.logger.info(f"Registering agent: {agent_type}")
        
        # Create agent info
        agent_info = AgentInfo(
            agent=agent,
            status=AgentStatus.INITIALIZING
        )
        
        try:
            # Initialize the agent if not already initialized
            if not agent._initialized:
                await agent.initialize()
            
            agent_info.status = AgentStatus.READY
            self._agents[agent_type] = agent_info
            
            self.logger.info(f"Agent registered successfully: {agent_type}")
            
        except Exception as e:
            agent_info.status = AgentStatus.ERROR
            self._agents[agent_type] = agent_info
            
            self.logger.error(f"Failed to register agent {agent_type}", extra={
                "error": str(e),
                "error_type": type(e).__name__
            })
            raise
    
    async def unregister_agent(self, agent_type: str) -> bool:
        """
        Unregister an agent from the orchestrator.
        
        Args:
            agent_type: Type of agent to unregister
            
        Returns:
            True if agent was unregistered, False if not found
        """
        if agent_type not in self._agents:
            return False
        
        agent_info = self._agents[agent_type]
        
        # Wait for active requests to complete
        while agent_info.concurrent_requests > 0:
            self.logger.info(f"Waiting for {agent_info.concurrent_requests} active requests to complete for {agent_type}")
            await asyncio.sleep(1)
        
        # Shutdown the agent
        try:
            await agent_info.agent.shutdown()
        except Exception as e:
            self.logger.error(f"Error shutting down agent {agent_type}", extra={
                "error": str(e)
            })
        
        # Remove from registry
        del self._agents[agent_type]
        self.logger.info(f"Agent unregistered: {agent_type}")
        
        return True
    
    async def route_request(self, request: AgentRequest) -> AgentResponse:
        """
        Route and execute a request through the appropriate agent.
        
        Args:
            request: The request to process
            
        Returns:
            Response from the selected agent
        """
        if not self._initialized:
            return AgentResponse.error(
                error_message="Orchestrator not initialized",
                error_code=ErrorCodes.AGENT_UNAVAILABLE
            )
        
        request_id = request.request_id or str(uuid.uuid4())
        request.request_id = request_id
        
        # Track request start
        start_time = asyncio.get_event_loop().time()
        self._active_requests[request_id] = {
            "request": request,
            "start_time": start_time,
            "agent_type": None
        }
        
        with TraceContext(request_id):
            try:
                # Route the request
                target_agent_type = self._router.route_request(request, self._agents)
                
                if not target_agent_type:
                    return self._handle_no_agent_available(request)
                
                # Get agent info
                agent_info = self._agents[target_agent_type]
                
                # Update tracking
                self._active_requests[request_id]["agent_type"] = target_agent_type
                agent_info.concurrent_requests += 1
                agent_info.request_count += 1
                agent_info.last_request_time = start_time
                
                # Update agent status
                if agent_info.concurrent_requests >= agent_info.max_concurrent:
                    agent_info.status = AgentStatus.BUSY
                
                self.logger.info(f"Routing request to agent: {target_agent_type}", extra={
                    "request_id": request_id,
                    "agent_type": target_agent_type,
                    "concurrent_requests": agent_info.concurrent_requests
                })
                
                # Execute the request
                response = await agent_info.agent.execute_request(request)
                
                # Track completion
                execution_time = asyncio.get_event_loop().time() - start_time
                self._total_requests += 1
                self._total_execution_time += execution_time
                
                if not response.success:
                    self._total_errors += 1
                    agent_info.error_count += 1
                
                # Add orchestrator metadata
                response.metadata.update({
                    "orchestrator": {
                        "routed_to": target_agent_type,
                        "execution_time": execution_time,
                        "request_id": request_id
                    }
                })
                
                return response
                
            except Exception as e:
                self._total_errors += 1
                if target_agent_type and target_agent_type in self._agents:
                    self._agents[target_agent_type].error_count += 1
                
                self.logger.error(f"Error processing request", extra={
                    "request_id": request_id,
                    "error": str(e),
                    "error_type": type(e).__name__
                })
                
                return AgentResponse.error(
                    error_message=f"Orchestrator error: {str(e)}",
                    error_code=ErrorCodes.UNKNOWN_ERROR,
                    error_details={"request_id": request_id}
                )
                
            finally:
                # Cleanup tracking
                if request_id in self._active_requests:
                    agent_type = self._active_requests[request_id].get("agent_type")
                    if agent_type and agent_type in self._agents:
                        agent_info = self._agents[agent_type]
                        agent_info.concurrent_requests = max(0, agent_info.concurrent_requests - 1)
                        
                        # Update status if no longer busy
                        if agent_info.concurrent_requests < agent_info.max_concurrent:
                            agent_info.status = AgentStatus.READY
                    
                    # Move to history
                    request_record = self._active_requests.pop(request_id)
                    request_record["end_time"] = asyncio.get_event_loop().time()
                    request_record["duration"] = request_record["end_time"] - request_record["start_time"]
                    
                    self._request_history.append(request_record)
                    
                    # Limit history size
                    if len(self._request_history) > self._max_history:
                        self._request_history = self._request_history[-self._max_history:]
    
    def _handle_no_agent_available(self, request: AgentRequest) -> AgentResponse:
        """Handle case when no agent is available for the request."""
        available_agents = [
            agent_type for agent_type, info in self._agents.items()
            if info.status == AgentStatus.READY
        ]
        
        if not available_agents:
            error_message = "No agents are currently available"
            error_code = ErrorCodes.AGENT_UNAVAILABLE
        else:
            error_message = f"No agent available for request type '{request.agent_type}'"
            error_code = ErrorCodes.AGENT_NOT_FOUND
        
        return AgentResponse.error(
            error_message=error_message,
            error_code=error_code,
            error_details={
                "requested_agent_type": request.agent_type,
                "available_agents": available_agents
            }
        )
    
    async def get_agent_status(self, agent_type: str) -> Optional[Dict[str, Any]]:
        """Get status information for a specific agent."""
        if agent_type not in self._agents:
            return None
        
        agent_info = self._agents[agent_type]
        
        # Get agent health check
        try:
            health = await agent_info.agent.health_check()
        except Exception as e:
            health = {"status": "error", "error": str(e)}
        
        return {
            "agent_type": agent_type,
            "status": agent_info.status.value,
            "request_count": agent_info.request_count,
            "error_count": agent_info.error_count,
            "concurrent_requests": agent_info.concurrent_requests,
            "max_concurrent": agent_info.max_concurrent,
            "last_request_time": agent_info.last_request_time,
            "health": health
        }
    
    async def get_orchestrator_status(self) -> Dict[str, Any]:
        """Get comprehensive orchestrator status."""
        agent_statuses = {}
        for agent_type in self._agents:
            agent_statuses[agent_type] = await self.get_agent_status(agent_type)
        
        # Calculate average response time
        avg_response_time = (
            self._total_execution_time / self._total_requests 
            if self._total_requests > 0 else 0
        )
        
        # Calculate error rate
        error_rate = (
            self._total_errors / self._total_requests 
            if self._total_requests > 0 else 0
        )
        
        return {
            "initialized": self._initialized,
            "total_agents": len(self._agents),
            "active_requests": len(self._active_requests),
            "total_requests": self._total_requests,
            "total_errors": self._total_errors,
            "error_rate": error_rate,
            "avg_response_time": avg_response_time,
            "agents": agent_statuses
        }
    
    async def shutdown(self) -> None:
        """Shutdown the orchestrator and all registered agents."""
        if not self._initialized:
            return
        
        self.logger.info("Shutting down Strands orchestrator")
        
        # Signal shutdown
        self._shutdown_event.set()
        
        # Wait for active requests to complete (with timeout)
        timeout = 30  # 30 seconds
        start_time = asyncio.get_event_loop().time()
        
        while self._active_requests and (asyncio.get_event_loop().time() - start_time) < timeout:
            self.logger.info(f"Waiting for {len(self._active_requests)} active requests to complete")
            await asyncio.sleep(1)
        
        # Force shutdown remaining requests
        if self._active_requests:
            self.logger.warning(f"Force shutting down with {len(self._active_requests)} active requests")
        
        # Shutdown all agents
        for agent_type in list(self._agents.keys()):
            try:
                await self.unregister_agent(agent_type)
            except Exception as e:
                self.logger.error(f"Error unregistering agent {agent_type}", extra={
                    "error": str(e)
                })
        
        self._initialized = False
        self.logger.info("Strands orchestrator shutdown complete")
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get performance metrics for the orchestrator."""
        agent_metrics = {}
        for agent_type, agent_info in self._agents.items():
            agent_metrics[agent_type] = {
                "request_count": agent_info.request_count,
                "error_count": agent_info.error_count,
                "error_rate": (
                    agent_info.error_count / agent_info.request_count 
                    if agent_info.request_count > 0 else 0
                ),
                "concurrent_requests": agent_info.concurrent_requests,
                "status": agent_info.status.value
            }
        
        return {
            "orchestrator": {
                "total_requests": self._total_requests,
                "total_errors": self._total_errors,
                "error_rate": (
                    self._total_errors / self._total_requests 
                    if self._total_requests > 0 else 0
                ),
                "avg_response_time": (
                    self._total_execution_time / self._total_requests 
                    if self._total_requests > 0 else 0
                ),
                "active_requests": len(self._active_requests)
            },
            "agents": agent_metrics
        }
    
    def __repr__(self) -> str:
        return (f"StrandsOrchestrator("
                f"agents={len(self._agents)}, "
                f"active_requests={len(self._active_requests)}, "
                f"initialized={self._initialized})")