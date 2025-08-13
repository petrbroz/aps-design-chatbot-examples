"""
Health Monitoring for AgentCore

Provides comprehensive health checks for all system components
including external dependencies and performance metrics.
"""

import asyncio
import time
import psutil
from typing import Dict, Any, Callable, Optional, List
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta


@dataclass
class HealthStatus:
    """Health status for a service or component."""
    status: str  # "healthy", "unhealthy", "degraded"
    message: str
    last_check: datetime
    response_time_ms: Optional[float] = None
    details: Optional[Dict[str, Any]] = None


@dataclass
class SystemMetrics:
    """System performance metrics."""
    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    memory_total_mb: float
    disk_percent: float
    disk_used_gb: float
    disk_total_gb: float
    uptime_seconds: float
    timestamp: datetime


class HealthMonitor:
    """
    Comprehensive health monitoring for AgentCore system.
    
    Monitors system resources, external dependencies, and service health
    with configurable check intervals and alerting thresholds.
    """
    
    def __init__(self, check_interval: int = 30, logger=None):
        """Initialize health monitor."""
        self.check_interval = check_interval
        self.logger = logger
        
        # Service registry
        self._services: Dict[str, Callable] = {}
        self._service_status: Dict[str, HealthStatus] = {}
        
        # System metrics
        self._start_time = time.time()
        self._metrics_history: List[SystemMetrics] = []
        self._max_history = 100  # Keep last 100 metrics
        
        # Health check task
        self._health_task: Optional[asyncio.Task] = None
        self._running = False
    
    async def initialize(self) -> None:
        """Initialize health monitoring."""
        self._running = True
        self._health_task = asyncio.create_task(self._health_check_loop())
        
        if self.logger:
            self.logger.info("Health monitor initialized", extra={
                "check_interval": self.check_interval
            })
    
    async def shutdown(self) -> None:
        """Shutdown health monitoring."""
        self._running = False
        
        if self._health_task:
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass
        
        if self.logger:
            self.logger.info("Health monitor shutdown")
    
    async def register_service(self, name: str, health_check: Callable) -> None:
        """Register a service for health monitoring."""
        self._services[name] = health_check
        
        # Perform initial health check
        await self._check_service_health(name)
        
        if self.logger:
            self.logger.info(f"Service registered for health monitoring: {name}")
    
    async def _health_check_loop(self) -> None:
        """Main health check loop."""
        while self._running:
            try:
                await self._perform_health_checks()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                if self.logger:
                    self.logger.error("Error in health check loop", extra={
                        "error": str(e),
                        "error_type": type(e).__name__
                    })
                await asyncio.sleep(self.check_interval)
    
    async def _perform_health_checks(self) -> None:
        """Perform health checks for all registered services."""
        # Check system metrics
        await self._collect_system_metrics()
        
        # Check all registered services
        for service_name in self._services:
            await self._check_service_health(service_name)
    
    async def _check_service_health(self, service_name: str) -> None:
        """Check health of a specific service."""
        health_check = self._services.get(service_name)
        if not health_check:
            return
        
        start_time = time.time()
        
        try:
            result = await health_check()
            response_time = (time.time() - start_time) * 1000
            
            if isinstance(result, dict):
                status = result.get("status", "healthy")
                message = result.get("message", "Service is healthy")
                details = {k: v for k, v in result.items() if k not in ["status", "message"]}
            else:
                status = "healthy" if result else "unhealthy"
                message = "Service check passed" if result else "Service check failed"
                details = None
            
            self._service_status[service_name] = HealthStatus(
                status=status,
                message=message,
                last_check=datetime.utcnow(),
                response_time_ms=response_time,
                details=details
            )
            
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            
            self._service_status[service_name] = HealthStatus(
                status="unhealthy",
                message=f"Health check failed: {str(e)}",
                last_check=datetime.utcnow(),
                response_time_ms=response_time,
                details={"error_type": type(e).__name__}
            )
            
            if self.logger:
                self.logger.error(f"Health check failed for {service_name}", extra={
                    "service": service_name,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "response_time_ms": response_time
                })
    
    async def _collect_system_metrics(self) -> None:
        """Collect system performance metrics."""
        try:
            # CPU and memory metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            metrics = SystemMetrics(
                cpu_percent=cpu_percent,
                memory_percent=memory.percent,
                memory_used_mb=memory.used / (1024 * 1024),
                memory_total_mb=memory.total / (1024 * 1024),
                disk_percent=disk.percent,
                disk_used_gb=disk.used / (1024 * 1024 * 1024),
                disk_total_gb=disk.total / (1024 * 1024 * 1024),
                uptime_seconds=time.time() - self._start_time,
                timestamp=datetime.utcnow()
            )
            
            # Add to history
            self._metrics_history.append(metrics)
            
            # Keep only recent metrics
            if len(self._metrics_history) > self._max_history:
                self._metrics_history = self._metrics_history[-self._max_history:]
            
        except Exception as e:
            if self.logger:
                self.logger.error("Failed to collect system metrics", extra={
                    "error": str(e),
                    "error_type": type(e).__name__
                })
    
    async def get_system_health(self) -> Dict[str, Any]:
        """Get comprehensive system health status."""
        # Overall system status
        overall_status = "healthy"
        unhealthy_services = []
        
        for service_name, status in self._service_status.items():
            if status.status == "unhealthy":
                overall_status = "unhealthy"
                unhealthy_services.append(service_name)
            elif status.status == "degraded" and overall_status == "healthy":
                overall_status = "degraded"
        
        # Get latest metrics
        latest_metrics = self._metrics_history[-1] if self._metrics_history else None
        
        return {
            "status": overall_status,
            "timestamp": datetime.utcnow().isoformat(),
            "uptime_seconds": time.time() - self._start_time,
            "services": {
                name: asdict(status) for name, status in self._service_status.items()
            },
            "system_metrics": asdict(latest_metrics) if latest_metrics else None,
            "unhealthy_services": unhealthy_services,
            "total_services": len(self._services),
            "healthy_services": len([s for s in self._service_status.values() if s.status == "healthy"])
        }
    
    async def get_service_health(self, service_name: str) -> Optional[HealthStatus]:
        """Get health status for a specific service."""
        return self._service_status.get(service_name)
    
    async def get_system_metrics(self) -> Optional[SystemMetrics]:
        """Get latest system metrics."""
        return self._metrics_history[-1] if self._metrics_history else None
    
    async def get_metrics_history(self, minutes: int = 30) -> List[SystemMetrics]:
        """Get system metrics history for specified time period."""
        cutoff_time = datetime.utcnow() - timedelta(minutes=minutes)
        
        return [
            metrics for metrics in self._metrics_history
            if metrics.timestamp >= cutoff_time
        ]
    
    def is_healthy(self) -> bool:
        """Check if system is overall healthy."""
        return all(
            status.status == "healthy" 
            for status in self._service_status.values()
        )