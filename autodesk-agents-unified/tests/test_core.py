"""
Unit tests for AgentCore framework.
"""

import pytest
import tempfile
import yaml
import os
from unittest.mock import patch, AsyncMock
from agent_core.core import AgentCore
from agent_core.health import HealthStatus


class TestAgentCore:
    """Test AgentCore framework functionality."""
    
    @pytest.mark.asyncio
    async def test_agent_core_initialization(self):
        """Test AgentCore initialization."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a test config file
            config_data = {
                'core': {
                    'cache_directory': temp_dir,
                    'log_level': 'INFO'
                }
            }
            
            config_path = os.path.join(temp_dir, 'config.yaml')
            with open(config_path, 'w') as f:
                yaml.dump(config_data, f)
            
            agent_core = AgentCore(config_path)
            
            assert agent_core.is_initialized() is False
            
            await agent_core.initialize()
            
            assert agent_core.is_initialized() is True
            assert agent_core.config is not None
            assert agent_core.auth_manager is not None
            assert agent_core.logger is not None
            assert agent_core.health_monitor is not None
            assert agent_core.cache_manager is not None
            
            await agent_core.shutdown()
    
    @pytest.mark.asyncio
    async def test_agent_core_double_initialization(self):
        """Test that double initialization is handled gracefully."""
        agent_core = AgentCore()
        
        await agent_core.initialize()
        assert agent_core.is_initialized() is True
        
        # Second initialization should not raise error
        await agent_core.initialize()
        assert agent_core.is_initialized() is True
        
        await agent_core.shutdown()
    
    @pytest.mark.asyncio
    async def test_agent_core_shutdown(self):
        """Test AgentCore shutdown."""
        agent_core = AgentCore()
        await agent_core.initialize()
        
        assert agent_core._shutdown is False
        
        await agent_core.shutdown()
        
        assert agent_core._shutdown is True
        
        # Double shutdown should not raise error
        await agent_core.shutdown()
    
    @pytest.mark.asyncio
    async def test_agent_core_context_manager(self):
        """Test AgentCore as async context manager."""
        async with AgentCore() as agent_core:
            assert agent_core.is_initialized() is True
            assert agent_core._shutdown is False
        
        # Should be shutdown after context exit
        assert agent_core._shutdown is True
    
    @pytest.mark.asyncio
    async def test_is_healthy(self):
        """Test health check functionality."""
        agent_core = AgentCore()
        
        # Not healthy before initialization
        assert agent_core.is_healthy() is False
        
        await agent_core.initialize()
        
        # Should be healthy after initialization
        assert agent_core.is_healthy() is True
        
        await agent_core.shutdown()
        
        # Not healthy after shutdown
        assert agent_core.is_healthy() is False
    
    @pytest.mark.asyncio
    async def test_get_health_status(self):
        """Test getting health status."""
        agent_core = AgentCore()
        
        # Before initialization
        health_status = await agent_core.get_health_status()
        assert "status" in health_status
        assert health_status["status"] == "unhealthy"
        
        await agent_core.initialize()
        
        # After initialization
        health_status = await agent_core.get_health_status()
        assert "overall_status" in health_status
        assert "checks" in health_status
        assert "system_metrics" in health_status
        
        await agent_core.shutdown()
    
    @pytest.mark.asyncio
    async def test_get_system_info(self):
        """Test getting system information."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_data = {
                'core': {
                    'cache_directory': temp_dir,
                    'aws_region': 'us-west-2'
                },
                'agents': {
                    'test_agent': {'enabled': True}
                }
            }
            
            config_path = os.path.join(temp_dir, 'config.yaml')
            with open(config_path, 'w') as f:
                yaml.dump(config_data, f)
            
            agent_core = AgentCore(config_path)
            await agent_core.initialize()
            
            system_info = await agent_core.get_system_info()
            
            assert system_info["initialized"] is True
            assert system_info["shutdown"] is False
            assert system_info["healthy"] is True
            assert "config" in system_info
            assert system_info["config"]["aws_region"] == "us-west-2"
            assert system_info["config"]["agents_configured"] == 1
            assert "cache_stats" in system_info
            assert "system_metrics" in system_info
            
            await agent_core.shutdown()
    
    def test_get_agent_config(self):
        """Test getting agent configuration."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_data = {
                'agents': {
                    'test_agent': {
                        'enabled': False,
                        'tools': ['tool1', 'tool2'],
                        'config': {'setting': 'value'}
                    }
                }
            }
            
            config_path = os.path.join(temp_dir, 'config.yaml')
            with open(config_path, 'w') as f:
                yaml.dump(config_data, f)
            
            agent_core = AgentCore(config_path)
            
            agent_config = agent_core.get_agent_config('test_agent')
            
            assert agent_config["agent_type"] == "test_agent"
            assert agent_config["enabled"] is False
            assert agent_config["tools"] == ['tool1', 'tool2']
            assert agent_config["config"]["setting"] == "value"
    
    def test_get_agent_config_not_initialized(self):
        """Test getting agent config when not initialized."""
        agent_core = AgentCore()
        agent_core.config_manager = None
        
        with pytest.raises(RuntimeError, match="AgentCore not initialized"):
            agent_core.get_agent_config('test_agent')
    
    @pytest.mark.asyncio
    async def test_initialization_failure(self):
        """Test handling of initialization failures."""
        # Create invalid config
        with tempfile.TemporaryDirectory() as temp_dir:
            config_data = {
                'core': {
                    'aws_region': '',  # Invalid empty region
                    'bedrock_model_id': ''  # Invalid empty model ID
                }
            }
            
            config_path = os.path.join(temp_dir, 'config.yaml')
            with open(config_path, 'w') as f:
                yaml.dump(config_data, f)
            
            agent_core = AgentCore(config_path)
            
            with pytest.raises(RuntimeError, match="AgentCore initialization failed"):
                await agent_core.initialize()
    
    @pytest.mark.asyncio
    async def test_shutdown_error_handling(self):
        """Test error handling during shutdown."""
        agent_core = AgentCore()
        await agent_core.initialize()
        
        # Mock an error in health monitor shutdown
        with patch.object(agent_core.health_monitor, 'stop_monitoring', side_effect=Exception("Test error")):
            with pytest.raises(Exception, match="Test error"):
                await agent_core.shutdown()
    
    @pytest.mark.asyncio
    async def test_health_monitor_integration(self):
        """Test integration with health monitor."""
        agent_core = AgentCore()
        await agent_core.initialize()
        
        # Health monitor should be running
        assert agent_core.health_monitor._is_running is True
        
        # Should be able to get health status
        health_status = await agent_core.get_health_status()
        assert health_status is not None
        
        await agent_core.shutdown()
        
        # Health monitor should be stopped
        assert agent_core.health_monitor._is_running is False