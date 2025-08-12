"""
Unit tests for configuration management system.
"""

import os
import tempfile
import yaml
import pytest
import asyncio
from pathlib import Path
from unittest.mock import patch, MagicMock

from agent_core.config import (
    ConfigManager, 
    CoreConfig, 
    AgentConfig,
    ConfigSchema,
    CoreConfigSchema,
    AgentConfigSchema,
    LogLevel
)


class TestConfigSchema:
    """Test configuration schema validation."""
    
    def test_core_config_schema_valid(self):
        """Test valid core configuration schema."""
        config_data = {
            'aws_region': 'us-west-2',
            'bedrock_model_id': 'test-model',
            'opensearch_endpoint': 'http://localhost:9200',
            'cache_directory': '/tmp/test',
            'log_level': 'DEBUG',
            'health_check_interval': 30,
            'auth_enabled': True
        }
        
        schema = CoreConfigSchema(**config_data)
        assert schema.aws_region == 'us-west-2'
        assert schema.log_level == LogLevel.DEBUG
        assert schema.health_check_interval == 30
    
    def test_core_config_schema_invalid_health_interval(self):
        """Test invalid health check interval."""
        config_data = {
            'health_check_interval': -1
        }
        
        with pytest.raises(ValueError, match="health_check_interval must be positive"):
            CoreConfigSchema(**config_data)
    
    def test_core_config_schema_invalid_cache_directory(self):
        """Test invalid cache directory."""
        config_data = {
            'cache_directory': ''
        }
        
        with pytest.raises(ValueError, match="cache_directory cannot be empty"):
            CoreConfigSchema(**config_data)
    
    def test_agent_config_schema_valid(self):
        """Test valid agent configuration schema."""
        config_data = {
            'enabled': True,
            'tools': ['tool1', 'tool2'],
            'config': {'key': 'value'}
        }
        
        schema = AgentConfigSchema(**config_data)
        assert schema.enabled is True
        assert schema.tools == ['tool1', 'tool2']
        assert schema.config == {'key': 'value'}
    
    def test_complete_config_schema(self):
        """Test complete configuration schema."""
        config_data = {
            'core': {
                'aws_region': 'us-east-1',
                'log_level': 'INFO'
            },
            'agents': {
                'test_agent': {
                    'enabled': True,
                    'tools': ['test_tool']
                }
            }
        }
        
        schema = ConfigSchema(**config_data)
        assert schema.core.aws_region == 'us-east-1'
        assert 'test_agent' in schema.agents
        assert schema.agents['test_agent'].enabled is True


class TestConfigManager:
    """Test configuration manager functionality."""
    
    @pytest.fixture
    def temp_config_file(self):
        """Create a temporary configuration file."""
        config_data = {
            'core': {
                'aws_region': 'us-test-1',
                'bedrock_model_id': 'test-model',
                'opensearch_endpoint': 'http://test:9200',
                'cache_directory': '/tmp/test_cache',
                'log_level': 'DEBUG',
                'health_check_interval': 15,
                'auth_enabled': False
            },
            'agents': {
                'test_agent': {
                    'enabled': True,
                    'tools': ['test_tool1', 'test_tool2'],
                    'config': {
                        'test_param': 'test_value'
                    }
                }
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_data, f)
            temp_path = f.name
        
        yield temp_path
        
        # Cleanup
        os.unlink(temp_path)
    
    def test_config_manager_initialization(self, temp_config_file):
        """Test configuration manager initialization."""
        manager = ConfigManager(config_path=temp_config_file, enable_hot_reload=False)
        assert manager.config_path == temp_config_file
        assert manager._config is None
    
    def test_load_config_from_file(self, temp_config_file):
        """Test loading configuration from YAML file."""
        manager = ConfigManager(config_path=temp_config_file, enable_hot_reload=False)
        config = manager.load_config()
        
        assert isinstance(config, CoreConfig)
        assert config.aws_region == 'us-test-1'
        assert config.bedrock_model_id == 'test-model'
        assert config.log_level == 'DEBUG'
        assert config.health_check_interval == 15
        assert config.auth_enabled is False
        assert 'test_agent' in config.agents
    
    def test_load_config_with_env_overrides(self, temp_config_file):
        """Test loading configuration with environment variable overrides."""
        with patch.dict(os.environ, {
            'AWS_REGION': 'us-override-1',
            'LOG_LEVEL': 'ERROR',
            'AUTH_ENABLED': 'true',
            'HEALTH_CHECK_INTERVAL': '45'
        }):
            manager = ConfigManager(config_path=temp_config_file, enable_hot_reload=False)
            config = manager.load_config()
            
            assert config.aws_region == 'us-override-1'
            assert config.log_level == 'ERROR'
            assert config.auth_enabled is True
            assert config.health_check_interval == 45
    
    def test_load_config_invalid_yaml(self):
        """Test loading configuration with invalid YAML."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("invalid: yaml: content: [")
            temp_path = f.name
        
        try:
            manager = ConfigManager(config_path=temp_path, enable_hot_reload=False)
            with pytest.raises(ValueError, match="Invalid YAML"):
                manager.load_config()
        finally:
            os.unlink(temp_path)
    
    def test_load_config_validation_error(self):
        """Test loading configuration with validation errors."""
        config_data = {
            'core': {
                'health_check_interval': -1  # Invalid value
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_data, f)
            temp_path = f.name
        
        try:
            manager = ConfigManager(config_path=temp_path, enable_hot_reload=False)
            with pytest.raises(ValueError, match="Configuration validation failed"):
                manager.load_config()
        finally:
            os.unlink(temp_path)
    
    def test_get_agent_config(self, temp_config_file):
        """Test getting agent-specific configuration."""
        manager = ConfigManager(config_path=temp_config_file, enable_hot_reload=False)
        agent_config = manager.get_agent_config('test_agent')
        
        assert isinstance(agent_config, AgentConfig)
        assert agent_config.agent_type == 'test_agent'
        assert agent_config.enabled is True
        assert agent_config.tools == ['test_tool1', 'test_tool2']
        assert agent_config.specific_config == {'test_param': 'test_value'}
    
    def test_get_agent_config_nonexistent(self, temp_config_file):
        """Test getting configuration for non-existent agent."""
        manager = ConfigManager(config_path=temp_config_file, enable_hot_reload=False)
        agent_config = manager.get_agent_config('nonexistent_agent')
        
        assert isinstance(agent_config, AgentConfig)
        assert agent_config.agent_type == 'nonexistent_agent'
        assert agent_config.enabled is True
        assert agent_config.tools == []
        assert agent_config.specific_config == {}
    
    def test_validate_config_success(self, temp_config_file):
        """Test successful configuration validation."""
        manager = ConfigManager(config_path=temp_config_file, enable_hot_reload=False)
        is_valid, error_msg = manager.validate_config()
        
        assert is_valid is True
        assert error_msg is None
    
    def test_validate_config_failure(self):
        """Test configuration validation failure."""
        config_data = {
            'core': {
                'aws_region': '',  # Empty region should fail validation
                'bedrock_model_id': 'test-model'
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_data, f)
            temp_path = f.name
        
        try:
            manager = ConfigManager(config_path=temp_path, enable_hot_reload=False)
            is_valid, error_msg = manager.validate_config()
            
            assert is_valid is False
            assert "AWS region is required" in error_msg
        finally:
            os.unlink(temp_path)
    
    def test_get_config_summary(self, temp_config_file):
        """Test getting configuration summary."""
        manager = ConfigManager(config_path=temp_config_file, enable_hot_reload=False)
        summary = manager.get_config_summary()
        
        assert 'config_path' in summary
        assert 'aws_region' in summary
        assert 'log_level' in summary
        assert 'agents_enabled' in summary
        assert 'hot_reload_enabled' in summary
        assert summary['aws_region'] == 'us-test-1'
        assert summary['agents_enabled']['test_agent'] is True
    
    def test_force_reload(self, temp_config_file):
        """Test force reloading configuration."""
        manager = ConfigManager(config_path=temp_config_file, enable_hot_reload=False)
        
        # Load initial config
        config1 = manager.load_config()
        assert config1.aws_region == 'us-test-1'
        
        # Modify the file
        config_data = {
            'core': {
                'aws_region': 'us-modified-1',
                'bedrock_model_id': 'test-model',
                'cache_directory': '/tmp/test_cache'
            }
        }
        
        with open(temp_config_file, 'w') as f:
            yaml.dump(config_data, f)
        
        # Force reload
        config2 = manager.load_config(force_reload=True)
        assert config2.aws_region == 'us-modified-1'
    
    def test_reload_callbacks(self, temp_config_file):
        """Test configuration reload callbacks."""
        manager = ConfigManager(config_path=temp_config_file, enable_hot_reload=False)
        
        callback_called = False
        callback_config = None
        
        def test_callback(config):
            nonlocal callback_called, callback_config
            callback_called = True
            callback_config = config
        
        manager.add_reload_callback(test_callback)
        
        # Trigger reload
        asyncio.run(manager._reload_config())
        
        assert callback_called is True
        assert callback_config is not None
        assert isinstance(callback_config, CoreConfig)
    
    def test_shutdown(self, temp_config_file):
        """Test configuration manager shutdown."""
        manager = ConfigManager(config_path=temp_config_file, enable_hot_reload=True)
        
        # Add a callback
        manager.add_reload_callback(lambda x: None)
        assert len(manager._reload_callbacks) == 1
        
        # Shutdown
        manager.shutdown()
        
        # Verify cleanup
        assert len(manager._reload_callbacks) == 0
        assert manager._observer is None


class TestConfigFileDiscovery:
    """Test configuration file discovery."""
    
    def test_find_config_file_env_variable(self):
        """Test finding config file via environment variable."""
        with tempfile.NamedTemporaryFile(suffix='.yaml', delete=False) as f:
            temp_path = f.name
        
        try:
            with patch.dict(os.environ, {'AGENT_CONFIG_PATH': temp_path}):
                manager = ConfigManager(enable_hot_reload=False)
                assert manager.config_path == temp_path
        finally:
            os.unlink(temp_path)
    
    def test_find_config_file_standard_locations(self):
        """Test finding config file in standard locations."""
        # Create a temporary directory structure
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir) / 'config'
            config_dir.mkdir()
            config_file = config_dir / 'config.yaml'
            config_file.write_text('core: {}')
            
            # Change to temp directory
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                manager = ConfigManager(enable_hot_reload=False)
                assert manager.config_path == 'config/config.yaml'
            finally:
                os.chdir(original_cwd)


if __name__ == '__main__':
    pytest.main([__file__])