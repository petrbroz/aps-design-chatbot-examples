#!/usr/bin/env python3
"""
Test script for Model Derivatives Agent with real SQLite database integration.
"""

import asyncio
import os
from pathlib import Path

# Add the project root to Python path
import sys
sys.path.insert(0, str(Path(__file__).parent))

from agentcore import (
    AgentCore, CoreConfig, ConfigManager,
    AgentRequest, ExecutionContext, StrandsOrchestrator
)
from agents.model_derivatives import ModelDerivativesAgent


async def test_model_derivatives_agent():
    """Test Model Derivatives Agent functionality."""
    
    print("🧪 Testing Model Derivatives Agent")
    print("=" * 60)
    
    try:
        # Set up test environment
        if not os.getenv("AUTODESK_CLIENT_ID"):
            print("⚠️  No real Autodesk credentials found. Using test credentials.")
            os.environ["AUTODESK_CLIENT_ID"] = "test_client_id"
            os.environ["AUTODESK_CLIENT_SECRET"] = "test_client_secret"
        
        # Initialize AgentCore
        config_manager = ConfigManager()
        config = config_manager.load_config()
        agent_core = AgentCore(config)
        await agent_core.initialize()
        
        # Create orchestrator
        orchestrator = StrandsOrchestrator(agent_core)
        await orchestrator.initialize()
        
        # Create and register Model Derivatives agent
        model_derivatives_config = {
            "agent_id": "model_derivatives",
            "agent_type": "model_derivatives",
            "name": "Model Derivatives Agent",
            "description": "SQLite database integration for model derivatives",
            "specific_config": {
                "database_path": "./test_cache/derivatives.db"
            }
        }
        
        model_derivatives_agent = ModelDerivativesAgent(agent_core, model_derivatives_config)
        await model_derivatives_agent.initialize()
        
        # Register agent with orchestrator
        orchestrator.register_agent("model_derivatives", model_derivatives_agent)
        
        print("✅ Model Derivatives Agent initialized successfully")
        print()
        
        # Test 1: Show database schema
        print("🧪 Test 1: Show database schema")
        print("-" * 40)
        
        request = AgentRequest(
            prompt="Show schema",
            context={}
        )
        
        context = ExecutionContext(
            request_id="test-schema-001",
            user_id="test-user",
            session_id="test-session"
        )
        
        response = await model_derivatives_agent.process_prompt(request, context)
        
        if response.success:
            print("✅ Schema query successful")
            for line in response.responses:
                print(f"   {line}")
        else:
            print(f"❌ Schema query failed: {response.error_message}")
        
        print()
        
        # Test 2: SQL query examples
        print("🧪 Test 2: SQL query examples")
        print("-" * 40)
        
        request = AgentRequest(
            prompt="Show me SQL examples",
            context={}
        )
        
        response = await model_derivatives_agent.process_prompt(request, context)
        
        if response.success:
            print("✅ SQL examples retrieved successfully")
            for line in response.responses[:10]:  # Show first 10 lines
                print(f"   {line}")
            if len(response.responses) > 10:
                print(f"   ... and {len(response.responses) - 10} more lines")
        else:
            print(f"❌ SQL examples failed: {response.error_message}")
        
        print()
        
        # Test 3: Test SQL query execution (basic table query)
        print("🧪 Test 3: Test SQL query execution")
        print("-" * 40)
        
        request = AgentRequest(
            prompt="SELECT name FROM sqlite_master WHERE type='table';",
            context={}
        )
        
        response = await model_derivatives_agent.process_prompt(request, context)
        
        if response.success:
            print("✅ SQL query executed successfully")
            for line in response.responses:
                print(f"   {line}")
        else:
            print(f"❌ SQL query failed: {response.error_message}")
        
        print()
        
        # Test 4: Test agent capabilities
        print("🧪 Test 4: Agent capabilities")
        print("-" * 40)
        
        capabilities = model_derivatives_agent.get_capabilities()
        print(f"✅ Agent Type: {capabilities.agent_type}")
        print(f"✅ Name: {capabilities.name}")
        print(f"✅ Description: {capabilities.description}")
        print(f"✅ Version: {capabilities.version}")
        print(f"✅ Tools: {capabilities.tools}")
        print(f"✅ Supported Formats: {capabilities.supported_formats}")
        print(f"✅ Requires Auth: {capabilities.requires_authentication}")
        print(f"✅ Requires Internet: {capabilities.requires_internet}")
        
        print()
        
        # Test 5: Test help functionality
        print("🧪 Test 5: Help functionality")
        print("-" * 40)
        
        request = AgentRequest(
            prompt="help me with model derivatives",
            context={}
        )
        
        response = await model_derivatives_agent.process_prompt(request, context)
        
        if response.success:
            print("✅ Help response generated successfully")
            for line in response.responses[:8]:  # Show first 8 lines
                print(f"   {line}")
            if len(response.responses) > 8:
                print(f"   ... and {len(response.responses) - 8} more lines")
        else:
            print(f"❌ Help failed: {response.error_message}")
        
        print()
        print("🎉 All Model Derivatives Agent tests completed!")
        
    except Exception as e:
        print(f"❌ Test failed with error: {str(e)}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Cleanup
        try:
            await agent_core.shutdown()
            print("✅ AgentCore shutdown completed")
        except:
            pass


if __name__ == "__main__":
    asyncio.run(test_model_derivatives_agent())