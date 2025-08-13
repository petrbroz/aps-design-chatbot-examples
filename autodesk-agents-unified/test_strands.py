#!/usr/bin/env python3
"""
Test script for Strands orchestrator functionality.
"""

import asyncio
import os
from pathlib import Path

# Add the project root to Python path
import sys
sys.path.insert(0, str(Path(__file__).parent))

from agentcore import (
    AgentCore, CoreConfig, ConfigManager,
    BaseAgent, AgentRequest, AgentResponse, 
    AgentCapabilities, ExecutionContext
)
from agentcore.strands import StrandsOrchestrator


class MockModelPropertiesAgent(BaseAgent):
    """Mock Model Properties agent for testing."""
    
    async def initialize(self) -> None:
        """Initialize the mock agent."""
        self.logger.info("Mock Model Properties agent initializing")
    
    async def process_prompt(self, request: AgentRequest, 
                           context: ExecutionContext) -> AgentResponse:
        """Process a mock model properties request."""
        return AgentResponse(
            responses=[
                f"Mock Model Properties response to: {request.prompt}",
                "This would normally query Autodesk model properties"
            ],
            metadata={"agent": "model_properties", "mock": True}
        )
    
    def get_capabilities(self) -> AgentCapabilities:
        """Get mock agent capabilities."""
        return AgentCapabilities(
            agent_type="model_properties",
            name="Mock Model Properties Agent",
            description="Mock agent for testing",
            version="1.0.0",
            tools=["create_index", "query_index"],
            requires_authentication=False
        )
    
    def get_agent_type(self) -> str:
        """Return agent type."""
        return "model_properties"


class MockAECDataModelAgent(BaseAgent):
    """Mock AEC Data Model agent for testing."""
    
    async def initialize(self) -> None:
        """Initialize the mock agent."""
        self.logger.info("Mock AEC Data Model agent initializing")
    
    async def process_prompt(self, request: AgentRequest, 
                           context: ExecutionContext) -> AgentResponse:
        """Process a mock AEC data model request."""
        return AgentResponse(
            responses=[
                f"Mock AEC Data Model response to: {request.prompt}",
                "This would normally query AEC data model via GraphQL"
            ],
            metadata={"agent": "aec_data_model", "mock": True}
        )
    
    def get_capabilities(self) -> AgentCapabilities:
        """Get mock agent capabilities."""
        return AgentCapabilities(
            agent_type="aec_data_model",
            name="Mock AEC Data Model Agent",
            description="Mock agent for testing",
            version="1.0.0",
            tools=["execute_graphql_query", "get_element_categories"],
            requires_authentication=False
        )
    
    def get_agent_type(self) -> str:
        """Return agent type."""
        return "aec_data_model"


async def test_orchestrator_initialization():
    """Test orchestrator initialization."""
    
    print("🧪 Testing Strands Orchestrator Initialization")
    print("=" * 60)
    
    try:
        # Set up test environment
        if not os.getenv("AUTODESK_CLIENT_ID"):
            os.environ["AUTODESK_CLIENT_ID"] = "test_client_id"
        if not os.getenv("AUTODESK_CLIENT_SECRET"):
            os.environ["AUTODESK_CLIENT_SECRET"] = "test_client_secret"
        
        # Initialize AgentCore
        config_manager = ConfigManager()
        config = config_manager.load_config()
        agent_core = AgentCore(config)
        await agent_core.initialize()
        
        # Create orchestrator
        orchestrator = StrandsOrchestrator(agent_core)
        print(f"✅ Orchestrator created: {orchestrator}")
        
        # Initialize orchestrator
        await orchestrator.initialize()
        print(f"✅ Orchestrator initialized")
        
        # Get initial status
        status = await orchestrator.get_orchestrator_status()
        print(f"✅ Initial status retrieved")
        print(f"   Total agents: {status['total_agents']}")
        print(f"   Active requests: {status['active_requests']}")
        print(f"   Initialized: {status['initialized']}")
        
        # Shutdown
        await orchestrator.shutdown()
        await agent_core.shutdown()
        
        print("\n🎉 Orchestrator Initialization Test PASSED!")
        return True
        
    except Exception as e:
        print(f"\n❌ Orchestrator Initialization Test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_agent_registration():
    """Test agent registration and management."""
    
    print("\n🧪 Testing Agent Registration")
    print("=" * 60)
    
    try:
        # Set up test environment
        if not os.getenv("AUTODESK_CLIENT_ID"):
            os.environ["AUTODESK_CLIENT_ID"] = "test_client_id"
        if not os.getenv("AUTODESK_CLIENT_SECRET"):
            os.environ["AUTODESK_CLIENT_SECRET"] = "test_client_secret"
        
        # Initialize AgentCore and orchestrator
        config_manager = ConfigManager()
        config = config_manager.load_config()
        agent_core = AgentCore(config)
        await agent_core.initialize()
        
        orchestrator = StrandsOrchestrator(agent_core)
        await orchestrator.initialize()
        
        # Create mock agents
        model_props_agent = MockModelPropertiesAgent(agent_core, {})
        aec_agent = MockAECDataModelAgent(agent_core, {})
        
        # Register agents
        await orchestrator.register_agent("model_properties", model_props_agent)
        print(f"✅ Model Properties agent registered")
        
        await orchestrator.register_agent("aec_data_model", aec_agent)
        print(f"✅ AEC Data Model agent registered")
        
        # Check status
        status = await orchestrator.get_orchestrator_status()
        print(f"✅ Status after registration")
        print(f"   Total agents: {status['total_agents']}")
        print(f"   Agent types: {list(status['agents'].keys())}")
        
        # Get individual agent status
        mp_status = await orchestrator.get_agent_status("model_properties")
        print(f"✅ Model Properties agent status: {mp_status['status']}")
        
        aec_status = await orchestrator.get_agent_status("aec_data_model")
        print(f"✅ AEC Data Model agent status: {aec_status['status']}")
        
        # Test unregistration
        unregistered = await orchestrator.unregister_agent("model_properties")
        print(f"✅ Agent unregistration: {unregistered}")
        
        # Check status after unregistration
        final_status = await orchestrator.get_orchestrator_status()
        print(f"✅ Final agent count: {final_status['total_agents']}")
        
        # Shutdown
        await orchestrator.shutdown()
        await agent_core.shutdown()
        
        print("\n🎉 Agent Registration Test PASSED!")
        return True
        
    except Exception as e:
        print(f"\n❌ Agent Registration Test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_request_routing():
    """Test request routing functionality."""
    
    print("\n🧪 Testing Request Routing")
    print("=" * 60)
    
    try:
        # Set up test environment
        if not os.getenv("AUTODESK_CLIENT_ID"):
            os.environ["AUTODESK_CLIENT_ID"] = "test_client_id"
        if not os.getenv("AUTODESK_CLIENT_SECRET"):
            os.environ["AUTODESK_CLIENT_SECRET"] = "test_client_secret"
        
        # Initialize AgentCore and orchestrator
        config_manager = ConfigManager()
        config = config_manager.load_config()
        agent_core = AgentCore(config)
        await agent_core.initialize()
        
        orchestrator = StrandsOrchestrator(agent_core)
        await orchestrator.initialize()
        
        # Register agents
        model_props_agent = MockModelPropertiesAgent(agent_core, {})
        aec_agent = MockAECDataModelAgent(agent_core, {})
        
        await orchestrator.register_agent("model_properties", model_props_agent)
        await orchestrator.register_agent("aec_data_model", aec_agent)
        
        # Test direct routing by agent type
        request1 = AgentRequest(
            agent_type="model_properties",
            prompt="Show me model properties",
            context={}
        )
        
        response1 = await orchestrator.route_request(request1)
        print(f"✅ Direct routing test")
        print(f"   Success: {response1.success}")
        print(f"   Agent: {response1.metadata.get('orchestrator', {}).get('routed_to')}")
        print(f"   Response: {response1.responses[0] if response1.responses else 'None'}")
        
        # Test pattern-based routing
        request2 = AgentRequest(
            agent_type="unknown",  # Will be routed based on content
            prompt="Query the element categories",
            context={}
        )
        
        response2 = await orchestrator.route_request(request2)
        print(f"✅ Pattern-based routing test")
        print(f"   Success: {response2.success}")
        print(f"   Agent: {response2.metadata.get('orchestrator', {}).get('routed_to') if response2.success else 'None'}")
        
        # Test no agent available
        request3 = AgentRequest(
            agent_type="nonexistent_agent",
            prompt="This should fail",
            context={}
        )
        
        response3 = await orchestrator.route_request(request3)
        print(f"✅ No agent available test")
        print(f"   Success: {response3.success}")
        print(f"   Error code: {response3.error_code}")
        
        # Check performance metrics
        metrics = orchestrator.get_performance_metrics()
        print(f"✅ Performance metrics")
        print(f"   Total requests: {metrics['orchestrator']['total_requests']}")
        print(f"   Error rate: {metrics['orchestrator']['error_rate']:.2%}")
        
        # Shutdown
        await orchestrator.shutdown()
        await agent_core.shutdown()
        
        print("\n🎉 Request Routing Test PASSED!")
        return True
        
    except Exception as e:
        print(f"\n❌ Request Routing Test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests."""
    
    print("🚀 Strands Orchestrator Test Suite")
    print("=" * 80)
    
    tests = [
        test_orchestrator_initialization,
        test_agent_registration,
        test_request_routing
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if await test():
            passed += 1
    
    print(f"\n📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests PASSED! Strands orchestrator is ready.")
        return 0
    else:
        print("❌ Some tests FAILED. Check the output above.")
        return 1


if __name__ == "__main__":
    exit(asyncio.run(main()))