"""
Configuration Management for AgentCore

Handles loading and validation of configuration from YAML files
and environment variables with support for different environments.
"""

import os
import yaml
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from pathlib import Path


@dataclass
class CoreConfig:
    """Core AgentCore configuration."""
    
    # AWS Configuration
    aws_region: str = "us-east-1"
    bedrock_model_id: str = "anthropic.claude-3-5-sonnet-20241022-v2:0"
    bedrock_max_tokens: int = 4000
    bedrock_temperature: float = 0.1
    
    # Autodesk API Configuration
    autodesk_client_id: str = ""
    autodesk_client_secret: str = ""
    autodesk_base_url: str = "https://developer.api.autodesk.com"
    autodesk_auth_url: str = "https://developer.api.autodesk.com/authentication/v2/token"
    
    # AWS OpenSearch Configuration
    aws_opensearch_endpoint: str = ""  # e.g., https://search-agentcore-xyz.us-east-1.es.amazonaws.com
    aws_opensearch_domain: str = ""    # e.g., agentcore-vectors
    opensearch_index_prefix: str = "agentcore"
    opensearch_use_aws_auth: bool = True
    
    # Core Settings
    cache_directory: str = "./cache"
    log_level: str = "INFO"
    health_check_interval: int = 30
    
    # API Gateway Settings
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_cors_origins: List[str] = field(default_factory=lambda: ["*"])
    api_trusted_hosts: List[str] = field(default_factory=lambda: ["*"])
    
    def __post_init__(self):
        """Validate configuration after initialization."""
        # Load from environment variables if not set
        if not self.autodesk_client_id:
            self.autodesk_client_id = os.getenv("AUTODESK_CLIENT_ID", "")
        if not self.autodesk_client_secret:
            self.autodesk_client_secret = os.getenv("AUTODESK_CLIENT_SECRET", "")
        if not self.aws_opensearch_endpoint:
            self.aws_opensearch_endpoint = os.getenv("AWS_OPENSEARCH_ENDPOINT", "")
        if not self.aws_opensearch_domain:
            self.aws_opensearch_domain = os.getenv("AWS_OPENSEARCH_DOMAIN", "")
        
        # Override with environment variables
        self.aws_region = os.getenv("AWS_DEFAULT_REGION", self.aws_region)
        self.log_level = os.getenv("LOG_LEVEL", self.log_level)
        
        # Validate required fields
        if not self.autodesk_client_id:
            raise ValueError("AUTODESK_CLIENT_ID is required")
        if not self.autodesk_client_secret:
            raise ValueError("AUTODESK_CLIENT_SECRET is required")


@dataclass
class AgentConfig:
    """Configuration for individual agents."""
    
    agent_type: str
    enabled: bool = True
    tools: List[str] = field(default_factory=list)
    cache_ttl: int = 3600  # 1 hour default
    max_results: int = 100
    specific_config: Dict[str, Any] = field(default_factory=dict)


class ConfigManager:
    """Manages configuration loading and validation."""
    
    def __init__(self, config_path: Optional[Path] = None):
        """Initialize configuration manager."""
        self.config_path = config_path or Path("config/agentcore.yaml")
        self._config_cache: Optional[Dict[str, Any]] = None
    
    def load_config(self) -> CoreConfig:
        """Load core configuration from file and environment."""
        config_data = self._load_config_file()
        
        # Extract core config
        core_data = config_data.get("core", {})
        
        # Create CoreConfig with loaded data
        return CoreConfig(**core_data)
    
    def load_agent_configs(self) -> Dict[str, AgentConfig]:
        """Load agent configurations."""
        config_data = self._load_config_file()
        agents_data = config_data.get("agents", {})
        
        agent_configs = {}
        for agent_type, agent_data in agents_data.items():
            agent_configs[agent_type] = AgentConfig(
                agent_type=agent_type,
                **agent_data
            )
        
        return agent_configs
    
    def _load_config_file(self) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        if self._config_cache is not None:
            return self._config_cache
        
        if not self.config_path.exists():
            # Create default config if none exists
            self._create_default_config()
        
        try:
            with open(self.config_path, 'r') as f:
                config_data = yaml.safe_load(f) or {}
            
            self._config_cache = config_data
            return config_data
            
        except Exception as e:
            raise ValueError(f"Failed to load config from {self.config_path}: {e}")
    
    def _create_default_config(self) -> None:
        """Create a default configuration file."""
        default_config = {
            "core": {
                "aws_region": "us-east-1",
                "bedrock_model_id": "anthropic.claude-3-5-sonnet-20241022-v2:0",
                "cache_directory": "./cache",
                "log_level": "INFO",
                "health_check_interval": 30,
                "api_host": "0.0.0.0",
                "api_port": 8000
            },
            "agents": {
                "model_properties": {
                    "enabled": True,
                    "tools": [
                        "create_index",
                        "list_index_properties", 
                        "query_index",
                        "execute_jq_query"
                    ],
                    "cache_ttl": 3600,
                    "max_results": 100
                },
                "aec_data_model": {
                    "enabled": True,
                    "tools": [
                        "execute_graphql_query",
                        "get_element_categories",
                        "execute_jq_query",
                        "find_related_property_definitions"
                    ],
                    "cache_ttl": 3600,
                    "max_results": 100,
                    "specific_config": {
                        "aws_opensearch_endpoint": "${AWS_OPENSEARCH_ENDPOINT}",
                        "aws_opensearch_domain": "${AWS_OPENSEARCH_DOMAIN}",
                        "vector_search_k": 8,
                        "embedding_batch_size": 100
                    }
                },
                "model_derivatives": {
                    "enabled": True,
                    "tools": ["sql_database_toolkit"],
                    "cache_ttl": 3600,
                    "specific_config": {
                        "database_path": "./cache/derivatives.db"
                    }
                }
            }
        }
        
        # Ensure config directory exists
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write default config
        with open(self.config_path, 'w') as f:
            yaml.dump(default_config, f, default_flow_style=False, indent=2)
    
    def reload_config(self) -> None:
        """Reload configuration from file."""
        self._config_cache = None