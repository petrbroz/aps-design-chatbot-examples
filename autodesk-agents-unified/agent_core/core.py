"""
Core AgentCore framework implementation.
"""

import asyncio
from typing import Optional
from .config import ConfigManager, CoreConfig
from .auth import AuthenticationManager
from .logging import StructuredLogger
from .health import HealthMonitor
from .cache import CacheManager
from .tool_registry import ToolRegistry


class AgentCore:
    """
    Core framework that provides common services for all agents.
    
    This class initializes and manages:
    - Configuration management
    - Authentication and authorization
    - Structured logging
    - Health monitoring
    - Unified caching
    """
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_manager = ConfigManager(config_path)
        self.config: Optional[CoreConfig] = None
        
        # Core services - initialized in initialize()
        self.auth_manager: Optional[AuthenticationManager] = None
        self.logger: Optional[StructuredLogger] = None
        self.health_monitor: Optional[HealthMonitor] = None
        self.cache_manager: Optional[CacheManager] = None
        self.tool_registry: Optional[ToolRegistry] = None
        
        self._initialized = False
        self._shutdown = False
    
    async def initialize(self) -> None:
        """Initialize all core services."""
        if self._initialized:
            return
        
        try:
            # Load and validate configuration
            self.config = self.config_manager.load_config()
            is_valid, error_message = self.config_manager.validate_config()
            if not is_valid:
                raise RuntimeError(f"Configuration validation failed: {error_message}")
            
            # Initialize core services
            self.logger = StructuredLogger(
                log_level=self.config.log_level,
                service_name="agent-core"
            )
            
            self.auth_manager = AuthenticationManager(
                enabled=self.config.auth_enabled
            )
            
            self.health_monitor = HealthMonitor(
                check_interval=self.config.health_check_interval
            )
            
            self.cache_manager = CacheManager(
                cache_directory=self.config.cache_directory
            )
            
            self.tool_registry = ToolRegistry(
                logger=self.logger
            )
            
            # Initialize tool registry
            await self.tool_registry.initialize()
            
            # Start health monitoring
            await self.health_monitor.start_monitoring()
            
            self.logger.info("AgentCore initialized successfully", 
                           config_path=self.config_manager.config_path,
                           cache_directory=self.config.cache_directory)
            
            self._initialized = True
            
        except Exception as e:
            if self.logger:
                self.logger.error("Failed to initialize AgentCore", error=e)
            raise RuntimeError(f"AgentCore initialization failed: {e}")
    
    async def shutdown(self) -> None:
        """Graceful shutdown of all services."""
        if self._shutdown:
            return
        
        self._shutdown = True
        
        if self.logger:
            self.logger.info("Shutting down AgentCore")
        
        try:
            # Stop health monitoring
            if self.health_monitor:
                await self.health_monitor.stop_monitoring()
            
            # Shutdown tool registry
            if self.tool_registry:
                await self.tool_registry.shutdown()
            
            # Clean up expired cache entries
            if self.cache_manager:
                cleaned = await self.cache_manager.cleanup_expired()
                if self.logger:
                    self.logger.info("Cache cleanup completed", cleaned_entries=cleaned)
            
            # Clear authentication cache
            if self.auth_manager:
                self.auth_manager.clear_token_cache()
            
            if self.logger:
                self.logger.info("AgentCore shutdown completed")
                
        except Exception as e:
            if self.logger:
                self.logger.error("Error during AgentCore shutdown", error=e)
            raise
    
    def is_initialized(self) -> bool:
        """Check if AgentCore is initialized."""
        return self._initialized
    
    def is_healthy(self) -> bool:
        """Check if AgentCore is healthy."""
        if not self._initialized or self._shutdown:
            return False
        
        if self.health_monitor:
            from .health import HealthStatus
            # If no health checks have been performed yet, consider it healthy
            if not self.health_monitor._health_checks:
                return True
            return self.health_monitor.get_overall_health() != HealthStatus.UNHEALTHY
        
        return True
    
    async def get_health_status(self) -> dict:
        """Get comprehensive health status."""
        if not self.health_monitor:
            return {"status": "unhealthy", "message": "Health monitor not initialized"}
        
        return self.health_monitor.get_health_summary()
    
    async def get_system_info(self) -> dict:
        """Get system information and statistics."""
        info = {
            "initialized": self._initialized,
            "shutdown": self._shutdown,
            "healthy": self.is_healthy()
        }
        
        if self.config:
            info["config"] = {
                "aws_region": self.config.aws_region,
                "log_level": self.config.log_level,
                "auth_enabled": self.config.auth_enabled,
                "cache_directory": self.config.cache_directory,
                "agents_configured": len(self.config.agents)
            }
        
        if self.cache_manager:
            info["cache_stats"] = await self.cache_manager.get_cache_stats()
        
        if self.health_monitor:
            info["system_metrics"] = self.health_monitor.get_system_metrics().__dict__
        
        if self.tool_registry:
            info["tool_registry_stats"] = self.tool_registry.get_registry_stats()
        
        return info
    
    def get_agent_config(self, agent_type: str) -> dict:
        """Get configuration for a specific agent type."""
        if not self.config_manager:
            raise RuntimeError("AgentCore not initialized")
        
        agent_config = self.config_manager.get_agent_config(agent_type)
        return {
            "agent_type": agent_config.agent_type,
            "enabled": agent_config.enabled,
            "tools": agent_config.tools,
            "config": agent_config.specific_config
        }
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.shutdown()