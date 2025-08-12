"""
Configuration management system with YAML support, validation, and hot-reloading.
"""

import os
import yaml
import asyncio
import threading
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Callable, List
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from pydantic import BaseModel, ValidationError, field_validator
from enum import Enum


class LogLevel(str, Enum):
    """Valid log levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class CoreConfigSchema(BaseModel):
    """Pydantic schema for core configuration validation."""
    aws_region: str = "us-east-1"
    bedrock_model_id: str = "anthropic.claude-3-5-sonnet-20241022-v2:0"
    opensearch_endpoint: str = ""
    cache_directory: str = "/tmp/agent_cache"
    log_level: LogLevel = LogLevel.INFO
    health_check_interval: int = 30
    auth_enabled: bool = True
    
    @field_validator('health_check_interval')
    @classmethod
    def validate_health_check_interval(cls, v):
        if v < 1:
            raise ValueError('health_check_interval must be positive')
        return v
    
    @field_validator('cache_directory')
    @classmethod
    def validate_cache_directory(cls, v):
        if not v:
            raise ValueError('cache_directory cannot be empty')
        return v


class AgentConfigSchema(BaseModel):
    """Pydantic schema for agent configuration validation."""
    enabled: bool = True
    tools: List[str] = []
    config: Dict[str, Any] = {}
    
    @field_validator('tools')
    @classmethod
    def validate_tools(cls, v):
        if not isinstance(v, list):
            raise ValueError('tools must be a list')
        return v


class ConfigSchema(BaseModel):
    """Complete configuration schema."""
    core: CoreConfigSchema = CoreConfigSchema()
    agents: Dict[str, AgentConfigSchema] = {}


@dataclass
class CoreConfig:
    """Core configuration for AgentCore framework."""
    aws_region: str = "us-east-1"
    bedrock_model_id: str = "anthropic.claude-3-5-sonnet-20241022-v2:0"
    opensearch_endpoint: str = ""
    cache_directory: str = "/tmp/agent_cache"
    log_level: str = "INFO"
    health_check_interval: int = 30
    auth_enabled: bool = True
    
    # Agent-specific configurations
    agents: Dict[str, Dict[str, Any]] = field(default_factory=dict)


@dataclass
class AgentConfig:
    """Configuration for individual agents."""
    agent_type: str
    enabled: bool = True
    tools: list = field(default_factory=list)
    specific_config: Dict[str, Any] = field(default_factory=dict)


class ConfigFileHandler(FileSystemEventHandler):
    """Handles configuration file changes for hot-reloading."""
    
    def __init__(self, config_manager: 'ConfigManager'):
        self.config_manager = config_manager
        
    def on_modified(self, event):
        if not event.is_directory and event.src_path == self.config_manager.config_path:
            asyncio.create_task(self.config_manager._reload_config())


class ConfigManager:
    """Manages configuration loading from YAML files and environment variables with hot-reloading."""
    
    def __init__(self, config_path: Optional[str] = None, enable_hot_reload: bool = True):
        self.config_path = config_path or self._find_config_file()
        self._config: Optional[CoreConfig] = None
        self._config_schema: Optional[ConfigSchema] = None
        self._reload_callbacks: List[Callable[[CoreConfig], None]] = []
        self._observer: Optional[Observer] = None
        self._lock = threading.RLock()
        
        if enable_hot_reload:
            self._setup_hot_reload()
    
    def _setup_hot_reload(self):
        """Setup file system watcher for configuration hot-reloading."""
        try:
            config_dir = os.path.dirname(os.path.abspath(self.config_path))
            if os.path.exists(config_dir):
                self._observer = Observer()
                event_handler = ConfigFileHandler(self)
                self._observer.schedule(event_handler, config_dir, recursive=False)
                self._observer.start()
        except Exception as e:
            print(f"Warning: Could not setup hot-reload for config: {e}")
    
    def _find_config_file(self) -> str:
        """Find configuration file in standard locations."""
        # Check environment variable first
        env_config = os.getenv('AGENT_CONFIG_PATH')
        if env_config and os.path.exists(env_config):
            return env_config
            
        possible_paths = [
            "config/config.yaml",
            "config/production.yaml", 
            "config/development.yaml",
            "config/local.yaml",
            "agent_core/config.yaml"
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
        
        # Return default path if none found
        return "config/config.yaml"
    
    def load_config(self, force_reload: bool = False) -> CoreConfig:
        """Load configuration from YAML file and environment variables with validation."""
        with self._lock:
            if self._config is not None and not force_reload:
                return self._config
                
            config_data = {}
            
            # Load from YAML file if it exists
            if os.path.exists(self.config_path):
                try:
                    with open(self.config_path, 'r') as f:
                        config_data = yaml.safe_load(f) or {}
                except yaml.YAMLError as e:
                    raise ValueError(f"Invalid YAML in config file {self.config_path}: {e}")
            
            # Override with environment variables
            config_data = self._apply_env_overrides(config_data)
            
            # Validate configuration schema
            try:
                self._config_schema = ConfigSchema(**config_data)
            except ValidationError as e:
                raise ValueError(f"Configuration validation failed: {e}")
            
            # Create CoreConfig instance from validated schema
            core_data = self._config_schema.core.model_dump()
            agents_data = {k: v.model_dump() for k, v in self._config_schema.agents.items()}
            
            self._config = CoreConfig(
                aws_region=core_data['aws_region'],
                bedrock_model_id=core_data['bedrock_model_id'],
                opensearch_endpoint=core_data['opensearch_endpoint'],
                cache_directory=core_data['cache_directory'],
                log_level=core_data['log_level'],
                health_check_interval=core_data['health_check_interval'],
                auth_enabled=core_data['auth_enabled'],
                agents=agents_data
            )
            
            # Ensure cache directory exists
            Path(self._config.cache_directory).mkdir(parents=True, exist_ok=True)
            
            return self._config
    
    async def _reload_config(self):
        """Reload configuration and notify callbacks."""
        try:
            old_config = self._config
            new_config = self.load_config(force_reload=True)
            
            # Notify callbacks of configuration change
            for callback in self._reload_callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(new_config)
                    else:
                        callback(new_config)
                except Exception as e:
                    print(f"Error in config reload callback: {e}")
                    
            print(f"Configuration reloaded from {self.config_path}")
            
        except Exception as e:
            print(f"Failed to reload configuration: {e}")
    
    def add_reload_callback(self, callback: Callable[[CoreConfig], None]):
        """Add a callback to be called when configuration is reloaded."""
        self._reload_callbacks.append(callback)
    
    def remove_reload_callback(self, callback: Callable[[CoreConfig], None]):
        """Remove a reload callback."""
        if callback in self._reload_callbacks:
            self._reload_callbacks.remove(callback)
    
    def _apply_env_overrides(self, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """Apply environment variable overrides to configuration."""
        env_mappings = {
            'AWS_REGION': ['core', 'aws_region'],
            'BEDROCK_MODEL_ID': ['core', 'bedrock_model_id'],
            'OPENSEARCH_ENDPOINT': ['core', 'opensearch_endpoint'],
            'CACHE_DIRECTORY': ['core', 'cache_directory'],
            'LOG_LEVEL': ['core', 'log_level'],
            'AUTH_ENABLED': ['core', 'auth_enabled'],
            'HEALTH_CHECK_INTERVAL': ['core', 'health_check_interval']
        }
        
        for env_var, config_path in env_mappings.items():
            env_value = os.getenv(env_var)
            if env_value is not None:
                # Navigate to the nested config location
                current = config_data
                for key in config_path[:-1]:
                    if key not in current:
                        current[key] = {}
                    current = current[key]
                
                # Convert values to appropriate types
                if env_var == 'AUTH_ENABLED':
                    env_value = env_value.lower() in ('true', '1', 'yes')
                elif env_var == 'HEALTH_CHECK_INTERVAL':
                    env_value = int(env_value)
                
                current[config_path[-1]] = env_value
        
        return config_data
    
    def get_agent_config(self, agent_type: str) -> AgentConfig:
        """Get configuration for a specific agent."""
        config = self.load_config()
        agent_data = config.agents.get(agent_type, {})
        
        return AgentConfig(
            agent_type=agent_type,
            enabled=agent_data.get('enabled', True),
            tools=agent_data.get('tools', []),
            specific_config=agent_data.get('config', {})
        )
    
    def validate_config(self) -> tuple[bool, Optional[str]]:
        """Validate the loaded configuration."""
        try:
            config = self.load_config()
            
            # Additional business logic validation
            if not config.aws_region:
                return False, "AWS region is required"
            
            if not config.bedrock_model_id:
                return False, "Bedrock model ID is required"
            
            # Validate agent configurations
            for agent_type, agent_data in config.agents.items():
                if not isinstance(agent_data.get('tools', []), list):
                    return False, f"Agent {agent_type} tools must be a list"
                    
                if not isinstance(agent_data.get('enabled', True), bool):
                    return False, f"Agent {agent_type} enabled must be a boolean"
            
            return True, None
            
        except Exception as e:
            return False, str(e)
    
    def get_config_summary(self) -> Dict[str, Any]:
        """Get a summary of the current configuration for debugging."""
        config = self.load_config()
        return {
            'config_path': self.config_path,
            'aws_region': config.aws_region,
            'log_level': config.log_level,
            'auth_enabled': config.auth_enabled,
            'cache_directory': config.cache_directory,
            'agents_enabled': {
                agent_type: agent_data.get('enabled', True) 
                for agent_type, agent_data in config.agents.items()
            },
            'hot_reload_enabled': self._observer is not None
        }
    
    def shutdown(self):
        """Cleanup resources and stop file watcher."""
        if self._observer:
            self._observer.stop()
            self._observer.join()
            self._observer = None
        self._reload_callbacks.clear()