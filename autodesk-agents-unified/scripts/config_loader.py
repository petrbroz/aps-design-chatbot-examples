#!/usr/bin/env python3
"""
Configuration loader for deployment scripts
Loads environment-specific configuration from deployment_config.yaml
"""

import os
import yaml
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class DeploymentConfig:
    """Deployment configuration data class"""
    environment: str
    image_tag: str
    scale_replicas: int
    enable_load_balancer: bool
    enable_auto_scaling: bool
    min_replicas: int
    max_replicas: int
    health_check_timeout: int
    rollback_enabled: bool
    backup_enabled: bool
    notification_webhook: Optional[str]
    
    # Performance settings
    target_cpu_percent: float
    target_memory_percent: float
    target_response_time_ms: float
    concurrent_test_requests: int
    cooldown_period: int = 300
    
    # Monitoring settings
    prometheus_enabled: bool = True
    grafana_enabled: bool = True
    alertmanager_enabled: bool = True
    log_level: str = "INFO"
    metrics_retention: str = "30d"
    
    # Security settings
    auth_enabled: bool = True
    cors_enabled: bool = True
    rate_limiting_enabled: bool = True
    security_headers_enabled: bool = True
    
    # Cache settings
    cache_ttl: int = 3600
    max_cache_size: str = "1GB"
    cleanup_interval: int = 1800


class ConfigLoader:
    """Loads and processes deployment configuration"""
    
    def __init__(self, config_file: str = "deployment_config.yaml"):
        self.config_file = Path(config_file)
        self.config_data = None
        self.load_config()
    
    def load_config(self) -> None:
        """Load configuration from YAML file"""
        try:
            if not self.config_file.exists():
                logger.warning(f"Configuration file {self.config_file} not found, using defaults")
                self.config_data = {}
                return
            
            with open(self.config_file, 'r') as f:
                self.config_data = yaml.safe_load(f)
            
            logger.info(f"Configuration loaded from {self.config_file}")
            
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            self.config_data = {}
    
    def get_environment_config(self, environment: str) -> DeploymentConfig:
        """Get configuration for specific environment"""
        if not self.config_data:
            return self._get_default_config(environment)
        
        # Get environment-specific config
        env_config = self.config_data.get(environment, {})
        
        # Get common config
        common_config = self.config_data.get('common', {})
        
        # Merge configurations (environment overrides common)
        merged_config = self._deep_merge(common_config, env_config)
        
        # Apply environment variable substitutions
        merged_config = self._substitute_env_vars(merged_config)
        
        # Convert to DeploymentConfig object
        return self._create_deployment_config(environment, merged_config)
    
    def _deep_merge(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """Deep merge two dictionaries"""
        result = base.copy()
        
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        
        return result
    
    def _substitute_env_vars(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Substitute environment variables in configuration"""
        def substitute_value(value):
            if isinstance(value, str):
                # Handle ${VAR} and ${VAR:-default} patterns
                import re
                pattern = r'\$\{([^}]+)\}'
                
                def replace_var(match):
                    var_expr = match.group(1)
                    if ':-' in var_expr:
                        var_name, default_value = var_expr.split(':-', 1)
                        return os.getenv(var_name, default_value)
                    else:
                        return os.getenv(var_expr, match.group(0))
                
                return re.sub(pattern, replace_var, value)
            elif isinstance(value, dict):
                return {k: substitute_value(v) for k, v in value.items()}
            elif isinstance(value, list):
                return [substitute_value(item) for item in value]
            else:
                return value
        
        return substitute_value(config)
    
    def _create_deployment_config(self, environment: str, config: Dict[str, Any]) -> DeploymentConfig:
        """Create DeploymentConfig from configuration dictionary"""
        deployment = config.get('deployment', {})
        monitoring = config.get('monitoring', {})
        performance = config.get('performance', {})
        security = config.get('security', {})
        cache = config.get('cache', {})
        
        return DeploymentConfig(
            environment=environment,
            image_tag=deployment.get('image_tag', 'latest'),
            scale_replicas=deployment.get('scale_replicas', 1),
            enable_load_balancer=deployment.get('enable_load_balancer', False),
            enable_auto_scaling=deployment.get('enable_auto_scaling', False),
            min_replicas=deployment.get('min_replicas', 1),
            max_replicas=deployment.get('max_replicas', 5),
            health_check_timeout=deployment.get('health_check_timeout', 300),
            rollback_enabled=deployment.get('rollback_enabled', True),
            backup_enabled=deployment.get('backup_enabled', True),
            notification_webhook=deployment.get('notification_webhook'),
            
            target_cpu_percent=performance.get('target_cpu_percent', 70.0),
            target_memory_percent=performance.get('target_memory_percent', 80.0),
            target_response_time_ms=performance.get('target_response_time_ms', 2000.0),
            concurrent_test_requests=performance.get('concurrent_test_requests', 10),
            cooldown_period=performance.get('cooldown_period', 300),
            
            prometheus_enabled=monitoring.get('prometheus_enabled', True),
            grafana_enabled=monitoring.get('grafana_enabled', True),
            alertmanager_enabled=monitoring.get('alertmanager_enabled', True),
            log_level=monitoring.get('log_level', 'INFO'),
            metrics_retention=monitoring.get('metrics_retention', '30d'),
            
            auth_enabled=security.get('auth_enabled', True),
            cors_enabled=security.get('cors_enabled', True),
            rate_limiting_enabled=security.get('rate_limiting_enabled', True),
            security_headers_enabled=security.get('security_headers_enabled', True),
            
            cache_ttl=cache.get('cache_ttl', 3600),
            max_cache_size=cache.get('max_cache_size', '1GB'),
            cleanup_interval=cache.get('cleanup_interval', 1800)
        )
    
    def _get_default_config(self, environment: str) -> DeploymentConfig:
        """Get default configuration when no config file is available"""
        logger.info(f"Using default configuration for {environment}")
        
        if environment == 'production':
            return DeploymentConfig(
                environment=environment,
                image_tag='latest',
                scale_replicas=3,
                enable_load_balancer=True,
                enable_auto_scaling=True,
                min_replicas=2,
                max_replicas=10,
                health_check_timeout=300,
                rollback_enabled=True,
                backup_enabled=True,
                notification_webhook=None,
                target_cpu_percent=70.0,
                target_memory_percent=80.0,
                target_response_time_ms=2000.0,
                concurrent_test_requests=20,
                cooldown_period=300
            )
        else:
            return DeploymentConfig(
                environment=environment,
                image_tag='latest',
                scale_replicas=1,
                enable_load_balancer=False,
                enable_auto_scaling=False,
                min_replicas=1,
                max_replicas=3,
                health_check_timeout=120,
                rollback_enabled=True,
                backup_enabled=True,
                notification_webhook=None,
                target_cpu_percent=80.0,
                target_memory_percent=85.0,
                target_response_time_ms=5000.0,
                concurrent_test_requests=5,
                cooldown_period=300
            )
    
    def get_validation_config(self, environment: str) -> Dict[str, Any]:
        """Get validation configuration for environment"""
        if not self.config_data:
            return {}
        
        env_config = self.config_data.get(environment, {})
        common_config = self.config_data.get('common', {})
        
        merged_config = self._deep_merge(common_config, env_config)
        
        return merged_config.get('validation', {})
    
    def get_agent_config(self, environment: str) -> Dict[str, Any]:
        """Get agent configuration for environment"""
        if not self.config_data:
            return {}
        
        env_config = self.config_data.get(environment, {})
        common_config = self.config_data.get('common', {})
        
        merged_config = self._deep_merge(common_config, env_config)
        
        return merged_config.get('agents', {})
    
    def export_environment_variables(self, config: DeploymentConfig) -> Dict[str, str]:
        """Export configuration as environment variables"""
        env_vars = {
            'ENVIRONMENT': config.environment,
            'IMAGE_TAG': config.image_tag,
            'SCALE_REPLICAS': str(config.scale_replicas),
            'ENABLE_LOAD_BALANCER': str(config.enable_load_balancer).lower(),
            'ENABLE_AUTO_SCALING': str(config.enable_auto_scaling).lower(),
            'MIN_REPLICAS': str(config.min_replicas),
            'MAX_REPLICAS': str(config.max_replicas),
            'HEALTH_CHECK_TIMEOUT': str(config.health_check_timeout),
            'ROLLBACK_ENABLED': str(config.rollback_enabled).lower(),
            'BACKUP_ENABLED': str(config.backup_enabled).lower(),
            'TARGET_CPU_PERCENT': str(config.target_cpu_percent),
            'TARGET_MEMORY_PERCENT': str(config.target_memory_percent),
            'TARGET_RESPONSE_TIME_MS': str(config.target_response_time_ms),
            'LOG_LEVEL': config.log_level,
            'CACHE_TTL': str(config.cache_ttl),
            'MAX_CACHE_SIZE': config.max_cache_size,
            'CLEANUP_INTERVAL': str(config.cleanup_interval)
        }
        
        if config.notification_webhook:
            env_vars['NOTIFICATION_WEBHOOK'] = config.notification_webhook
        
        return env_vars
    
    def print_config_summary(self, config: DeploymentConfig) -> None:
        """Print configuration summary"""
        print(f"\n📋 Deployment Configuration for {config.environment.upper()}")
        print("=" * 60)
        print(f"Image Tag: {config.image_tag}")
        print(f"Scale: {config.scale_replicas} replicas")
        print(f"Load Balancer: {'Enabled' if config.enable_load_balancer else 'Disabled'}")
        print(f"Auto Scaling: {'Enabled' if config.enable_auto_scaling else 'Disabled'}")
        if config.enable_auto_scaling:
            print(f"  Min/Max Replicas: {config.min_replicas}/{config.max_replicas}")
        print(f"Health Check Timeout: {config.health_check_timeout}s")
        print(f"Rollback: {'Enabled' if config.rollback_enabled else 'Disabled'}")
        print(f"Backup: {'Enabled' if config.backup_enabled else 'Disabled'}")
        print(f"Log Level: {config.log_level}")
        print(f"Cache TTL: {config.cache_ttl}s")
        print("=" * 60)


def main():
    """Main function for testing configuration loader"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Load deployment configuration")
    parser.add_argument("--environment", required=True, help="Environment name")
    parser.add_argument("--config-file", default="deployment_config.yaml", help="Configuration file path")
    parser.add_argument("--export-env", action="store_true", help="Export as environment variables")
    
    args = parser.parse_args()
    
    loader = ConfigLoader(args.config_file)
    config = loader.get_environment_config(args.environment)
    
    loader.print_config_summary(config)
    
    if args.export_env:
        print("\n🔧 Environment Variables:")
        print("-" * 40)
        env_vars = loader.export_environment_variables(config)
        for key, value in env_vars.items():
            print(f"export {key}='{value}'")
    
    return 0


if __name__ == "__main__":
    exit(main())