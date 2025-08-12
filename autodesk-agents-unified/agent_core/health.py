"""
Health monitoring system for AgentCore framework.
"""

import asyncio
import psutil
import time
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from enum import Enum
from datetime import datetime, timezone
from collections import deque
import statistics


class HealthStatus(Enum):
    """Health status enumeration."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class ResponseTimeMetrics:
    """Response time metrics for performance monitoring."""
    avg_response_time_ms: float
    min_response_time_ms: float
    max_response_time_ms: float
    p95_response_time_ms: float
    p99_response_time_ms: float
    total_requests: int
    timestamp: datetime


@dataclass
class SystemMetrics:
    """System performance metrics."""
    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    memory_total_mb: float
    disk_percent: float
    uptime_seconds: float
    timestamp: datetime
    response_times: Optional[ResponseTimeMetrics] = None


@dataclass
class HealthCheck:
    """Individual health check result."""
    name: str
    status: HealthStatus
    message: str
    duration_ms: float
    timestamp: datetime
    metadata: Dict[str, Any] = None


class HealthMonitor:
    """Monitors system and service health."""
    
    def __init__(self, check_interval: int = 30, max_response_times: int = 1000):
        self.check_interval = check_interval
        self.start_time = time.time()
        self._health_checks: Dict[str, HealthCheck] = {}
        self._monitoring_task: Optional[asyncio.Task] = None
        self._is_running = False
        
        # Response time tracking
        self._response_times: deque = deque(maxlen=max_response_times)
        self._agent_response_times: Dict[str, deque] = {}
        self._tool_response_times: Dict[str, deque] = {}
    
    async def start_monitoring(self) -> None:
        """Start background health monitoring."""
        if self._is_running:
            return
        
        self._is_running = True
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())
    
    async def stop_monitoring(self) -> None:
        """Stop background health monitoring."""
        self._is_running = False
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
    
    async def _monitoring_loop(self) -> None:
        """Background monitoring loop."""
        while self._is_running:
            try:
                await self._perform_health_checks()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Health monitoring error: {e}")
                await asyncio.sleep(self.check_interval)
    
    async def _perform_health_checks(self) -> None:
        """Perform all registered health checks."""
        # System health check
        await self.check_system_health()
        
        # Add more health checks as needed
        # await self.check_database_health()
        # await self.check_external_services()
    
    async def check_system_health(self) -> HealthCheck:
        """Check system resource health."""
        start_time = time.time()
        
        try:
            metrics = self.get_system_metrics()
            
            # Determine health status based on resource usage
            status = HealthStatus.HEALTHY
            message = "System resources are healthy"
            
            if metrics.cpu_percent > 80 or metrics.memory_percent > 85:
                status = HealthStatus.DEGRADED
                message = f"High resource usage: CPU {metrics.cpu_percent}%, Memory {metrics.memory_percent}%"
            
            if metrics.cpu_percent > 95 or metrics.memory_percent > 95:
                status = HealthStatus.UNHEALTHY
                message = f"Critical resource usage: CPU {metrics.cpu_percent}%, Memory {metrics.memory_percent}%"
            
            duration_ms = (time.time() - start_time) * 1000
            
            health_check = HealthCheck(
                name="system",
                status=status,
                message=message,
                duration_ms=duration_ms,
                timestamp=datetime.now(timezone.utc),
                metadata={
                    "cpu_percent": metrics.cpu_percent,
                    "memory_percent": metrics.memory_percent,
                    "disk_percent": metrics.disk_percent
                }
            )
            
            self._health_checks["system"] = health_check
            return health_check
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            health_check = HealthCheck(
                name="system",
                status=HealthStatus.UNHEALTHY,
                message=f"System health check failed: {e}",
                duration_ms=duration_ms,
                timestamp=datetime.now(timezone.utc)
            )
            self._health_checks["system"] = health_check
            return health_check
    
    async def check_agent_health(self, agent_type: str) -> HealthCheck:
        """Check health of a specific agent."""
        start_time = time.time()
        
        try:
            # Basic agent health check - in production would ping agent
            # For now, just check if agent is registered
            status = HealthStatus.HEALTHY
            message = f"Agent {agent_type} is healthy"
            
            duration_ms = (time.time() - start_time) * 1000
            
            health_check = HealthCheck(
                name=f"agent_{agent_type}",
                status=status,
                message=message,
                duration_ms=duration_ms,
                timestamp=datetime.now(timezone.utc)
            )
            
            self._health_checks[f"agent_{agent_type}"] = health_check
            return health_check
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            health_check = HealthCheck(
                name=f"agent_{agent_type}",
                status=HealthStatus.UNHEALTHY,
                message=f"Agent {agent_type} health check failed: {e}",
                duration_ms=duration_ms,
                timestamp=datetime.now(timezone.utc)
            )
            self._health_checks[f"agent_{agent_type}"] = health_check
            return health_check
    
    async def check_dependencies(self) -> Dict[str, HealthCheck]:
        """Check health of external dependencies."""
        dependencies = {}
        
        # Check AWS Bedrock connectivity (mock for now)
        dependencies["bedrock"] = await self._check_bedrock_health()
        
        # Check OpenSearch connectivity (mock for now)
        dependencies["opensearch"] = await self._check_opensearch_health()
        
        return dependencies
    
    async def _check_bedrock_health(self) -> HealthCheck:
        """Check AWS Bedrock service health."""
        start_time = time.time()
        
        try:
            # Mock health check - in production would test actual connection
            status = HealthStatus.HEALTHY
            message = "Bedrock service is accessible"
            
            duration_ms = (time.time() - start_time) * 1000
            
            return HealthCheck(
                name="bedrock",
                status=status,
                message=message,
                duration_ms=duration_ms,
                timestamp=datetime.now(timezone.utc)
            )
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return HealthCheck(
                name="bedrock",
                status=HealthStatus.UNHEALTHY,
                message=f"Bedrock health check failed: {e}",
                duration_ms=duration_ms,
                timestamp=datetime.now(timezone.utc)
            )
    
    async def _check_opensearch_health(self) -> HealthCheck:
        """Check OpenSearch service health."""
        start_time = time.time()
        
        try:
            # Mock health check - in production would test actual connection
            status = HealthStatus.HEALTHY
            message = "OpenSearch service is accessible"
            
            duration_ms = (time.time() - start_time) * 1000
            
            return HealthCheck(
                name="opensearch",
                status=status,
                message=message,
                duration_ms=duration_ms,
                timestamp=datetime.now(timezone.utc)
            )
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return HealthCheck(
                name="opensearch",
                status=HealthStatus.UNHEALTHY,
                message=f"OpenSearch health check failed: {e}",
                duration_ms=duration_ms,
                timestamp=datetime.now(timezone.utc)
            )
    
    def get_system_metrics(self) -> SystemMetrics:
        """Get current system performance metrics."""
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        return SystemMetrics(
            cpu_percent=psutil.cpu_percent(interval=1),
            memory_percent=memory.percent,
            memory_used_mb=memory.used / (1024 * 1024),
            memory_total_mb=memory.total / (1024 * 1024),
            disk_percent=disk.percent,
            uptime_seconds=time.time() - self.start_time,
            timestamp=datetime.now(timezone.utc)
        )
    
    def get_overall_health(self) -> HealthStatus:
        """Get overall system health status."""
        if not self._health_checks:
            return HealthStatus.UNHEALTHY
        
        statuses = [check.status for check in self._health_checks.values()]
        
        if any(status == HealthStatus.UNHEALTHY for status in statuses):
            return HealthStatus.UNHEALTHY
        elif any(status == HealthStatus.DEGRADED for status in statuses):
            return HealthStatus.DEGRADED
        else:
            return HealthStatus.HEALTHY
    
    def record_response_time(self, duration_ms: float, component_type: str = "general", component_name: str = None) -> None:
        """Record response time for performance monitoring."""
        self._response_times.append(duration_ms)
        
        if component_type == "agent" and component_name:
            if component_name not in self._agent_response_times:
                self._agent_response_times[component_name] = deque(maxlen=1000)
            self._agent_response_times[component_name].append(duration_ms)
        
        elif component_type == "tool" and component_name:
            if component_name not in self._tool_response_times:
                self._tool_response_times[component_name] = deque(maxlen=1000)
            self._tool_response_times[component_name].append(duration_ms)
    
    def get_response_time_metrics(self, component_type: str = "general", component_name: str = None) -> Optional[ResponseTimeMetrics]:
        """Get response time metrics for a specific component or overall."""
        response_times = None
        
        if component_type == "agent" and component_name:
            response_times = list(self._agent_response_times.get(component_name, []))
        elif component_type == "tool" and component_name:
            response_times = list(self._tool_response_times.get(component_name, []))
        else:
            response_times = list(self._response_times)
        
        if not response_times:
            return None
        
        sorted_times = sorted(response_times)
        
        return ResponseTimeMetrics(
            avg_response_time_ms=statistics.mean(response_times),
            min_response_time_ms=min(response_times),
            max_response_time_ms=max(response_times),
            p95_response_time_ms=sorted_times[int(len(sorted_times) * 0.95)] if len(sorted_times) > 0 else 0,
            p99_response_time_ms=sorted_times[int(len(sorted_times) * 0.99)] if len(sorted_times) > 0 else 0,
            total_requests=len(response_times),
            timestamp=datetime.now(timezone.utc)
        )
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get performance metrics summary."""
        summary = {
            "overall": self.get_response_time_metrics(),
            "agents": {},
            "tools": {}
        }
        
        # Agent performance metrics
        for agent_name in self._agent_response_times:
            summary["agents"][agent_name] = self.get_response_time_metrics("agent", agent_name)
        
        # Tool performance metrics
        for tool_name in self._tool_response_times:
            summary["tools"][tool_name] = self.get_response_time_metrics("tool", tool_name)
        
        return summary
    
    def get_health_summary(self) -> Dict[str, Any]:
        """Get comprehensive health summary."""
        system_metrics = self.get_system_metrics()
        system_metrics.response_times = self.get_response_time_metrics()
        
        return {
            "overall_status": self.get_overall_health().value,
            "checks": {name: {
                "status": check.status.value,
                "message": check.message,
                "duration_ms": check.duration_ms,
                "timestamp": check.timestamp.isoformat(),
                "metadata": check.metadata
            } for name, check in self._health_checks.items()},
            "system_metrics": {
                "cpu_percent": system_metrics.cpu_percent,
                "memory_percent": system_metrics.memory_percent,
                "memory_used_mb": system_metrics.memory_used_mb,
                "memory_total_mb": system_metrics.memory_total_mb,
                "disk_percent": system_metrics.disk_percent,
                "uptime_seconds": system_metrics.uptime_seconds,
                "timestamp": system_metrics.timestamp.isoformat(),
                "response_times": system_metrics.response_times.__dict__ if system_metrics.response_times else None
            },
            "performance": self.get_performance_summary(),
            "uptime_seconds": time.time() - self.start_time
        }
    
    def get_health_check_endpoint_data(self) -> Dict[str, Any]:
        """Get data formatted for health check endpoints (load balancers)."""
        overall_status = self.get_overall_health()
        
        # Simple format for load balancers
        return {
            "status": overall_status.value,
            "healthy": overall_status == HealthStatus.HEALTHY,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "uptime": time.time() - self.start_time,
            "version": "1.0.0"  # Could be made configurable
        }
    
    def get_detailed_health_check(self) -> Dict[str, Any]:
        """Get detailed health check for monitoring systems."""
        return self.get_health_summary()