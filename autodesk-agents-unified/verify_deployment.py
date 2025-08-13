#!/usr/bin/env python3
"""
Deployment verification script for Autodesk Agents Unified System.
This script verifies that all components are properly deployed and ready.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add the project root to Python path
sys.path.insert(0, str(Path(__file__).parent))

def check_file_structure():
    """Verify all required files are present."""
    print("🔍 Checking file structure...")
    
    required_files = [
        "agentcore/__init__.py",
        "agentcore/agent_core.py",
        "agentcore/base_agent.py",
        "agentcore/orchestrator.py",
        "agentcore/api_gateway.py",
        "agents/__init__.py",
        "agents/model_properties.py",
        "agents/aec_data_model.py",
        "agents/model_derivatives.py",
        "config/config.yaml",
        "requirements.txt",
        "main.py",
        "deploy.py",
        "README.md"
    ]
    
    missing_files = []
    for file_path in required_files:
        if not Path(file_path).exists():
            missing_files.append(file_path)
    
    if missing_files:
        print(f"❌ Missing files: {missing_files}")
        return False
    else:
        print("✅ All required files present")
        return True

def check_dependencies():
    """Check if all required dependencies can be imported."""
    print("🔍 Checking dependencies...")
    
    required_modules = [
        "aiohttp",
        "aiofiles", 
        "aiosqlite",
        "fastapi",
        "uvicorn",
        "pydantic",
        "pyyaml",
        "boto3",
        "opensearch_py"
    ]
    
    missing_modules = []
    for module in required_modules:
        try:
            __import__(module)
        except ImportError:
            missing_modules.append(module)
    
    if missing_modules:
        print(f"❌ Missing modules: {missing_modules}")
        print("💡 Run: pip install -r requirements.txt")
        return False
    else:
        print("✅ All dependencies available")
        return True

def check_agentcore_imports():
    """Check if AgentCore components can be imported."""
    print("🔍 Checking AgentCore imports...")
    
    try:
        from agentcore import (
            AgentCore, ConfigManager, StrandsOrchestrator,
            AgentRequest, AgentResponse, ExecutionContext
        )
        from agents import ModelPropertiesAgent, AECDataModelAgent, ModelDerivativesAgent
        print("✅ All AgentCore components can be imported")
        return True
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False

async def check_agent_initialization():
    """Check if agents can be initialized."""
    print("🔍 Checking agent initialization...")
    
    try:
        # Set test credentials
        os.environ["AUTODESK_CLIENT_ID"] = "test_client_id"
        os.environ["AUTODESK_CLIENT_SECRET"] = "test_client_secret"
        
        from agentcore import AgentCore, ConfigManager
        from agents import ModelPropertiesAgent, AECDataModelAgent, ModelDerivativesAgent
        
        # Initialize AgentCore
        config_manager = ConfigManager()
        config = config_manager.load_config()
        agent_core = AgentCore(config)
        await agent_core.initialize()
        
        # Test each agent
        agents_tested = 0
        
        # Model Properties Agent
        try:
            model_props_config = {
                "agent_id": "model_properties",
                "agent_type": "model_properties",
                "specific_config": {
                    "elasticsearch_url": "http://localhost:9200"
                }
            }
            model_props_agent = ModelPropertiesAgent(agent_core, model_props_config)
            await model_props_agent.initialize()
            agents_tested += 1
            print("   ✅ Model Properties Agent initialized")
        except Exception as e:
            print(f"   ❌ Model Properties Agent failed: {e}")
        
        # AEC Data Model Agent
        try:
            aec_config = {
                "agent_id": "aec_data_model",
                "agent_type": "aec_data_model",
                "specific_config": {
                    "opensearch_endpoint": "https://test.us-east-1.es.amazonaws.com"
                }
            }
            aec_agent = AECDataModelAgent(agent_core, aec_config)
            await aec_agent.initialize()
            agents_tested += 1
            print("   ✅ AEC Data Model Agent initialized")
        except Exception as e:
            print(f"   ❌ AEC Data Model Agent failed: {e}")
        
        # Model Derivatives Agent
        try:
            derivatives_config = {
                "agent_id": "model_derivatives",
                "agent_type": "model_derivatives",
                "specific_config": {
                    "database_path": "./test_cache/test.db"
                }
            }
            derivatives_agent = ModelDerivativesAgent(agent_core, derivatives_config)
            await derivatives_agent.initialize()
            agents_tested += 1
            print("   ✅ Model Derivatives Agent initialized")
        except Exception as e:
            print(f"   ❌ Model Derivatives Agent failed: {e}")
        
        await agent_core.shutdown()
        
        if agents_tested == 3:
            print("✅ All agents can be initialized")
            return True
        else:
            print(f"❌ Only {agents_tested}/3 agents initialized successfully")
            return False
            
    except Exception as e:
        print(f"❌ Agent initialization failed: {e}")
        return False

def check_configuration():
    """Check configuration files."""
    print("🔍 Checking configuration...")
    
    try:
        from agentcore import ConfigManager
        config_manager = ConfigManager()
        config = config_manager.load_config()
        
        required_sections = ["core", "auth", "logging", "cache"]
        missing_sections = []
        
        for section in required_sections:
            if section not in config:
                missing_sections.append(section)
        
        if missing_sections:
            print(f"❌ Missing config sections: {missing_sections}")
            return False
        else:
            print("✅ Configuration is valid")
            return True
            
    except Exception as e:
        print(f"❌ Configuration error: {e}")
        return False

async def main():
    """Run all deployment verification checks."""
    
    print("🚀 Autodesk Agents Unified System - Deployment Verification")
    print("=" * 70)
    
    checks = [
        ("File Structure", check_file_structure),
        ("Dependencies", check_dependencies),
        ("AgentCore Imports", check_agentcore_imports),
        ("Configuration", check_configuration),
        ("Agent Initialization", check_agent_initialization)
    ]
    
    passed = 0
    total = len(checks)
    
    for check_name, check_func in checks:
        print(f"\n📋 {check_name}")
        print("-" * 40)
        
        try:
            if asyncio.iscoroutinefunction(check_func):
                result = await check_func()
            else:
                result = check_func()
            
            if result:
                passed += 1
        except Exception as e:
            print(f"❌ {check_name} failed with exception: {e}")
    
    print(f"\n📊 Verification Results: {passed}/{total} checks passed")
    
    if passed == total:
        print("\n🎉 DEPLOYMENT VERIFICATION SUCCESSFUL!")
        print("\n✅ System Status:")
        print("   • All files present and accessible")
        print("   • All dependencies installed")
        print("   • All components can be imported")
        print("   • Configuration is valid")
        print("   • All agents can be initialized")
        
        print("\n🚀 Ready for Production Deployment!")
        print("\n📋 Next Steps:")
        print("   1. Set production environment variables:")
        print("      - AUTODESK_CLIENT_ID")
        print("      - AUTODESK_CLIENT_SECRET")
        print("      - ELASTICSEARCH_URL")
        print("      - OPENSEARCH_ENDPOINT")
        print("      - AWS_REGION")
        print("   2. Run: python deploy.py production")
        print("   3. Start server: python main.py")
        print("   4. Test endpoints: curl http://localhost:8000/health")
        
        return 0
    else:
        print("\n❌ DEPLOYMENT VERIFICATION FAILED!")
        print(f"   {total - passed} checks failed. Please fix the issues above.")
        return 1

if __name__ == "__main__":
    exit(asyncio.run(main()))