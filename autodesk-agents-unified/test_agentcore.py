#!/usr/bin/env python3
"""
Test script for AgentCore framework initialization and basic functionality.
"""

import asyncio
import os
from pathlib import Path

# Add the project root to Python path
import sys
sys.path.insert(0, str(Path(__file__).parent))

from agentcore import AgentCore, CoreConfig
from agentcore.config import ConfigManager


async def test_agentcore_initialization():
    """Test AgentCore initialization with real configuration."""
    
    print("🧪 Testing AgentCore Framework Initialization")
    print("=" * 60)
    
    try:
        # Load configuration
        config_manager = ConfigManager()
        config = config_manager.load_config()
        
        print(f"✅ Configuration loaded successfully")
        print(f"   AWS Region: {config.aws_region}")
        print(f"   Bedrock Model: {config.bedrock_model_id}")
        print(f"   Cache Directory: {config.cache_directory}")
        print(f"   Log Level: {config.log_level}")
        
        # Initialize AgentCore
        agent_core = AgentCore(config)
        print(f"✅ AgentCore instance created: {agent_core}")
        
        # Initialize services
        await agent_core.initialize()
        print(f"✅ AgentCore services initialized")
        
        # Test health check
        health = await agent_core.get_health_status()
        print(f"✅ Health check completed")
        print(f"   Overall Status: {health.get('status', 'unknown')}")
        print(f"   Services: {health.get('total_services', 0)}")
        print(f"   Healthy Services: {health.get('healthy_services', 0)}")
        
        # Test authentication manager
        try:
            # This will fail without real credentials, but we can test the structure
            auth_health = await agent_core.auth_manager.health_check()
            print(f"✅ Authentication manager health check")
            print(f"   Status: {auth_health.get('status', 'unknown')}")
        except Exception as e:
            print(f"⚠️  Authentication test (expected without credentials): {str(e)[:100]}...")
        
        # Test cache manager
        cache_stats = await agent_core.cache_manager.get_stats()
        print(f"✅ Cache manager operational")
        print(f"   Memory Cache Entries: {cache_stats['memory_cache']['entries']}")
        print(f"   File Cache Entries: {cache_stats['file_cache']['entries']}")
        
        # Shutdown
        await agent_core.shutdown()
        print(f"✅ AgentCore shutdown completed")
        
        print("\n🎉 AgentCore Framework Test PASSED!")
        return True
        
    except Exception as e:
        print(f"\n❌ AgentCore Framework Test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_configuration_loading():
    """Test configuration loading and validation."""
    
    print("\n🧪 Testing Configuration Management")
    print("=" * 60)
    
    try:
        config_manager = ConfigManager()
        
        # Load core config
        core_config = config_manager.load_config()
        print(f"✅ Core configuration loaded")
        
        # Load agent configs
        agent_configs = config_manager.load_agent_configs()
        print(f"✅ Agent configurations loaded: {list(agent_configs.keys())}")
        
        for agent_type, agent_config in agent_configs.items():
            print(f"   {agent_type}: enabled={agent_config.enabled}, tools={len(agent_config.tools)}")
        
        return True
        
    except Exception as e:
        print(f"❌ Configuration test failed: {e}")
        return False


async def main():
    """Run all tests."""
    
    print("🚀 AgentCore Framework Test Suite")
    print("=" * 80)
    
    # Set up test environment variables if not present
    if not os.getenv("AUTODESK_CLIENT_ID"):
        os.environ["AUTODESK_CLIENT_ID"] = "test_client_id"
    if not os.getenv("AUTODESK_CLIENT_SECRET"):
        os.environ["AUTODESK_CLIENT_SECRET"] = "test_client_secret"
    
    tests = [
        test_configuration_loading,
        test_agentcore_initialization
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if await test():
            passed += 1
    
    print(f"\n📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests PASSED! AgentCore framework is ready.")
        return 0
    else:
        print("❌ Some tests FAILED. Check the output above.")
        return 1


if __name__ == "__main__":
    exit(asyncio.run(main()))