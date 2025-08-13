#!/usr/bin/env python3
"""
Test script for BaseAgent interface and models.
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
    AgentCapabilities, ExecutionContext, ErrorCodes
)


class TestAgent(BaseAgent):
    """Test implementation of BaseAgent."""
    
    async def initialize(self) -> None:
        """Initialize the test agent."""
        self.logger.info("Test agent initializing")
        
        # Register a simple test tool
        def echo_tool(message: str) -> str:
            return f"Echo: {message}"
        
        self.register_tool("echo", echo_tool)
    
    async def process_prompt(self, request: AgentRequest, 
                           context: ExecutionContext) -> AgentResponse:
        """Process a test prompt."""
        prompt = request.prompt.lower()
        
        if "echo" in prompt:
            # Use the echo tool
            tool_result = await self.execute_tool("echo", message=request.prompt)
            if tool_result.success:
                return AgentResponse(
                    responses=[tool_result.output],
                    metadata={"tool_used": "echo"}
                )
            else:
                return AgentResponse.error(
                    error_message=f"Tool failed: {tool_result.error_message}",
                    error_code=ErrorCodes.TOOL_EXECUTION_FAILED
                )
        
        elif "error" in prompt:
            # Test error handling
            raise ValueError("This is a test error")
        
        else:
            # Simple response
            return AgentResponse(
                responses=[
                    f"Test agent received: {request.prompt}",
                    f"Context keys: {list(request.context.keys())}",
                    f"Request ID: {context.request_id}"
                ],
                metadata={
                    "prompt_length": len(request.prompt),
                    "context_size": len(request.context)
                }
            )
    
    def get_capabilities(self) -> AgentCapabilities:
        """Get test agent capabilities."""
        return AgentCapabilities(
            agent_type="test_agent",
            name="Test Agent",
            description="A test implementation of BaseAgent",
            version="1.0.0",
            tools=["echo"],
            max_prompt_length=1000,
            requires_authentication=False,
            requires_project_context=False
        )
    
    def get_agent_type(self) -> str:
        """Return agent type."""
        return "test_agent"


async def test_base_agent_functionality():
    """Test BaseAgent functionality."""
    
    print("🧪 Testing BaseAgent Interface")
    print("=" * 60)
    
    try:
        # Set up test environment
        if not os.getenv("AUTODESK_CLIENT_ID"):
            os.environ["AUTODESK_CLIENT_ID"] = "test_client_id"
        if not os.getenv("AUTODESK_CLIENT_SECRET"):
            os.environ["AUTODESK_CLIENT_SECRET"] = "test_client_secret"
        
        # Load configuration
        config_manager = ConfigManager()
        config = config_manager.load_config()
        
        # Initialize AgentCore
        agent_core = AgentCore(config)
        await agent_core.initialize()
        
        # Create test agent
        test_agent = TestAgent(agent_core, {"timeout_seconds": 30})
        print(f"✅ Test agent created: {test_agent}")
        
        # Test capabilities
        capabilities = test_agent.get_capabilities()
        print(f"✅ Agent capabilities: {capabilities.name} v{capabilities.version}")
        print(f"   Tools: {capabilities.tools}")
        print(f"   Max prompt length: {capabilities.max_prompt_length}")
        
        # Test simple request
        request = AgentRequest(
            agent_type="test_agent",
            prompt="Hello test agent",
            context={"test_key": "test_value"}
        )
        
        response = await test_agent.execute_request(request)
        print(f"✅ Simple request processed")
        print(f"   Success: {response.success}")
        print(f"   Responses: {len(response.responses)}")
        print(f"   Execution time: {response.execution_time:.3f}s")
        
        # Test tool execution
        echo_request = AgentRequest(
            agent_type="test_agent",
            prompt="echo this message",
            context={}
        )
        
        echo_response = await test_agent.execute_request(echo_request)
        print(f"✅ Tool execution test")
        print(f"   Success: {echo_response.success}")
        print(f"   Response: {echo_response.responses[0] if echo_response.responses else 'None'}")
        
        # Test error handling
        error_request = AgentRequest(
            agent_type="test_agent",
            prompt="trigger an error",
            context={}
        )
        
        error_response = await test_agent.execute_request(error_request)
        print(f"✅ Error handling test")
        print(f"   Success: {error_response.success}")
        print(f"   Error code: {error_response.error_code}")
        print(f"   Error message: {error_response.error_message}")
        
        # Test health check
        health = await test_agent.health_check()
        print(f"✅ Health check")
        print(f"   Status: {health['status']}")
        print(f"   Request count: {health['request_count']}")
        print(f"   Error count: {health['error_count']}")
        
        # Test performance metrics
        metrics = test_agent.get_performance_metrics()
        print(f"✅ Performance metrics")
        print(f"   Total requests: {metrics['request_count']}")
        print(f"   Average response time: {metrics['avg_response_time_ms']:.2f}ms")
        
        # Shutdown
        await test_agent.shutdown()
        await agent_core.shutdown()
        
        print("\n🎉 BaseAgent Interface Test PASSED!")
        return True
        
    except Exception as e:
        print(f"\n❌ BaseAgent Interface Test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_models():
    """Test data models."""
    
    print("\n🧪 Testing Data Models")
    print("=" * 60)
    
    try:
        # Test AgentRequest
        request = AgentRequest(
            agent_type="test",
            prompt="Test prompt",
            context={"key": "value"},
            metadata={"source": "test"}
        )
        
        request_dict = request.to_dict()
        print(f"✅ AgentRequest serialization")
        print(f"   Keys: {list(request_dict.keys())}")
        
        # Test AgentResponse
        response = AgentResponse(
            responses=["Response 1", "Response 2"],
            success=True,
            agent_type="test",
            metadata={"processed": True}
        )
        
        response_dict = response.to_dict()
        print(f"✅ AgentResponse serialization")
        print(f"   Keys: {list(response_dict.keys())}")
        
        # Test error response
        error_response = AgentResponse.error(
            error_message="Test error",
            error_code=ErrorCodes.INVALID_PARAMETER,
            agent_type="test"
        )
        
        error_dict = error_response.to_dict()
        print(f"✅ Error response")
        print(f"   Success: {error_dict['success']}")
        print(f"   Error code: {error_dict['error_code']}")
        
        # Test ExecutionContext
        context = ExecutionContext(
            request_id="test-123",
            project_id="project-456"
        )
        
        print(f"✅ ExecutionContext")
        print(f"   Request ID: {context.request_id}")
        print(f"   Elapsed time: {context.elapsed_time():.3f}s")
        
        return True
        
    except Exception as e:
        print(f"❌ Data Models Test FAILED: {e}")
        return False


async def main():
    """Run all tests."""
    
    print("🚀 BaseAgent and Models Test Suite")
    print("=" * 80)
    
    tests = [
        test_models,
        test_base_agent_functionality
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if await test():
            passed += 1
    
    print(f"\n📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests PASSED! BaseAgent interface is ready.")
        return 0
    else:
        print("❌ Some tests FAILED. Check the output above.")
        return 1


if __name__ == "__main__":
    exit(asyncio.run(main()))