"""
Unit tests for configuration management.
"""

import pytest
import tempfile
import os
import yaml
from pathlib import Path
from agent_core.config import ConfigManager, CoreConfig, AgentConfig


class TestConfigManager:
    """Test configuration management functionality."""
    
    def test_default_config_creation(self):
        """Test creating default configuration."""
        config = CoreConfig()
        
        assert config.aws_region == "us-east-1"
        assert config.bedrock_model_id == "anthropic.claude-3-5-sonnet-20241022-v2:0"
        assert config.log_level == "INFO"
        assert config.auth_enabled is True
        assert config.health_check_interval == 30
    
    def test_config_loading_from_yaml(self):
        """Test loading configuration from YAML file."""
        config_data = {
            'core': {
                'aws_region': 'us-west-2',
                'log_level': 'DEBUG',
                'auth_enabled': False
            },
            'agents': {
                'test_agent': {
                    'enabled': True,
                    'tools': ['tool1', 'tool2']
                }
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_data, f)
            config_path = f.name
        
        try:
            config_manager = ConfigManager(config_path)
            config = config_manager.load_config()
            
            assert config.aws_region == 'us-west-2'
            assert config.log_level == 'DEBUG'
            assert config.auth_enabled is False
            assert 'test_agent' in config.agents
            
        finally:
            os.unlink(config_path)
    
    def test_environment_variable_overrides(self):
        """Test environment variable overrides."""
        # Set environment variables
        os.environ['AWS_REGION'] = 'eu-west-1'
        os.environ['LOG_LEVEL'] = 'ERROR'
        os.environ['AUTH_ENABLED'] = 'false'
        
        try:
            config_manager = ConfigManager()
            config = config_manager.load_config()
            
            assert config.aws_region == 'eu-west-1'
            assert config.log_level == 'ERROR'
            assert config.auth_enabled is False
            
        finally:
            # Clean up environment variables
            for var in ['AWS_REGION', 'LOG_LEVEL', 'AUTH_ENABLED']:
                if var in os.environ:
                    del os.environ[var]
    
    def test_agent_config_retrieval(self):
        """Test retrieving agent-specific configuration."""
        config_data = {
            'agents': {
                'test_agent': {
                    'enabled': False,
                    'tools': ['tool1', 'tool2'],
                    'config': {
                        'custom_setting': 'value'
                    }
                }
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_data, f)
            config_path = f.name
        
        try:
            config_manager = ConfigManager(config_path)
            agent_config = config_manager.get_agent_config('test_agent')
            
            assert agent_config.agent_type == 'test_agent'
            assert agent_config.enabled is False
            assert agent_config.tools == ['tool1', 'tool2']
            assert agent_config.specific_config['custom_setting'] == 'value'
            
        finally:
            os.unlink(config_path)
    
    def test_missing_agent_config(self):
        """Test retrieving configuration for non-existent agent."""
        config_manager = ConfigManager()
        agent_config = config_manager.get_agent_config('nonexistent_agent')
        
        assert agent_config.agent_type == 'nonexistent_agent'
        assert agent_config.enabled is True  # Default value
        assert agent_config.tools == []  # Default value
    
    def test_config_validation(self):
        """Test configuration validation."""
        # Test with valid config
        config_manager = ConfigManager()
        assert config_manager.validate_config() is True
        
        # Test with invalid config (empty AWS region)
        config_data = {
            'core': {
                'aws_region': '',
                'bedrock_model_id': ''
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_data, f)
            config_path = f.name
        
        try:
            config_manager = ConfigManager(config_path)
            assert config_manager.validate_config() is False
            
        finally:
            os.unlink(config_path)
    
    def test_cache_directory_creation(self):
        """Test that cache directory is created during validation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = os.path.join(temp_dir, 'test_cache')
            
            config_data = {
                'core': {
                    'cache_directory': cache_dir
                }
            }
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
                yaml.dump(config_data, f)
                config_path = f.name
            
            try:
                config_manager = ConfigManager(config_path)
                assert config_manager.validate_config() is True
                assert os.path.exists(cache_dir)
                
            finally:
                os.unlink(config_path)