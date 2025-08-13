"""
AgentCore Framework - Core Implementation

Provides the foundational services for unified Autodesk agent deployment
including authentication, configuration, logging, and health monitoring.
"""

import asyncio
import logging
from typing import Dict, Any, Optional
from pathlib import Path

from .config import CoreConfig
from .auth import AuthenticationManager
from .logging import StructuredLogger
from .health import HealthMonitor
from .cache import CacheManager


class AgentCore:
    """
    Core framework for unified Autodesk agent deployment.
    
    Provides centralized services for authentication, configuration,
    logging, caching, and health monitoring across all agents.
    """
    
    def __init__(self, config: CoreConfig):
        """Initialize AgentCore with configuration."""
        self.config = config
        self._initialized = False
        
        # Core services
        self.logger = StructuredLogger(
            level=config.log_level,
            service_name="agentcore"
        )
        
        self.auth_manager = AuthenticationManager(
            client_id=config.autodesk_client_id,
            client_secret=config.autodesk_client_secret,
            logger=self.logger
        )
        
        self.cache_manager = CacheManager(
            cache_directory=Path(config.cache_directory),
            logger=self.logger
        )
        
        self.health_monitor = HealthMonitor(
            check_interval=config.health_check_interval,
            logger=self.logger
        )
        
        # Service registry
        self._services: Dict[str, Any] = {}
        
        self.logger.info("AgentCore initialized", extra={
            "config": {
                "aws_region": config.aws_region,
                "cache_directory": config.cache_directory,
                "log_level": config.log_level
            }
        })
    
    async def initialize(self) -> None:
        """Initialize all core services."""
        if self._initialized:
            self.logger.warning("AgentCore already initialized")
            return
        
        try:
            self.logger.info("Starting AgentCore initialization")
            
            # Initialize cache manager
            await self.cache_manager.initialize()
            
            # Initialize health monitor
            await self.health_monitor.initialize()
            
            # Register core services for health monitoring
            await self.health_monitor.register_service(
                "auth_manager", 
                self.auth_manager.health_check
            )
            await self.health_monitor.register_service(
                "cache_manager",
                self.cache_manager.health_check
            )
            
            self._initialized = True
            self.logger.info("AgentCore initialization complete")
            
        except Exception as e:
            self.logger.error("AgentCore initialization failed", extra={
                "error": str(e),
                "error_type": type(e).__name__
            })
            raise
    
    async def shutdown(self) -> None:
        """Graceful shutdown of all services."""
        if not self._initialized:
            return
        
        try:
            self.logger.info("Starting AgentCore shutdown")
            
            # Shutdown services in reverse order
            await self.health_monitor.shutdown()
            await self.cache_manager.shutdown()
            
            self._initialized = False
            self.logger.info("AgentCore shutdown complete")
            
        except Exception as e:
            self.logger.error("Error during AgentCore shutdown", extra={
                "error": str(e),
                "error_type": type(e).__name__
            })
            raise
    
    def register_service(self, name: str, service: Any) -> None:
        """Register a service with AgentCore."""
        self._services[name] = service
        self.logger.info(f"Service registered: {name}")
    
    def get_service(self, name: str) -> Optional[Any]:
        """Get a registered service by name."""
        return self._services.get(name)
    
    async def get_health_status(self) -> Dict[str, Any]:
        """Get comprehensive health status."""
        return await self.health_monitor.get_system_health()
    
    def __repr__(self) -> str:
        return f"AgentCore(initialized={self._initialized}, services={len(self._services)})"