#!/usr/bin/env python3
"""
Main application entry point for Autodesk Agents Unified System

This is the production server that runs all three agents:
- Model Properties Agent (Elasticsearch integration)
- AEC Data Model Agent (OpenSearch integration)  
- Model Derivatives Agent (SQLite integration)
"""

import asyncio
import os
import sys
import uvicorn
from pathlib import Path

# Add the project root to Python path
sys.path.insert(0, str(Path(__file__).parent))

from agentcore import AgentCore, ConfigManager
from agentcore.orchestrator import StrandsOrchestrator
from agentcore.api_gateway import APIGateway
from agents import ModelPropertiesAgent, AECDataModelAgent, ModelDerivativesAgent


async def create_app():
    """Create and configure the FastAPI application."""
    
    print("🚀 Starting Autodesk Agents Unified System")
    print("=" * 50)
    
    # Set up test credentials if not provided
    if not os.getenv("AUTODESK_CLIENT_ID"):
        print("⚠️  Using test credentials for demo purposes")
        os.environ["AUTODESK_CLIENT_ID"] = "test_client_id"
        os.environ["AUTODESK_CLIENT_SECRET"] = "test_client_secret"
    
    # Initialize core system
    print("🏗️  Initializing core system...")
    config_manager = ConfigManager()
    config = config_manager.load_config()
    
    agent_core = AgentCore(config)
    await agent_core.initialize()
    
    orchestrator = StrandsOrchestrator(agent_core)
    await orchestrator.initialize()
    
    print("✅ Core system initialized")
    
    # Configure agents
    agents_config = {
        "model_properties": {
            "agent_id": "model_properties",
            "agent_type": "model_properties",
            "name": "Model Properties Agent",
            "description": "Elasticsearch integration for model properties",
            "specific_config": {
                "elasticsearch_url": os.getenv("ELASTICSEARCH_URL", "http://localhost:9200"),
                "default_index": "model_properties"
            }
        },
        "aec_data_model": {
            "agent_id": "aec_data_model",
            "agent_type": "aec_data_model",
            "name": "AEC Data Model Agent",
            "description": "OpenSearch integration for AEC data model",
            "specific_config": {
                "opensearch_endpoint": os.getenv("OPENSEARCH_ENDPOINT", "https://localhost:9200"),
                "aws_region": os.getenv("AWS_REGION", "us-east-1"),
                "index_name": "aec_property_definitions"
            }
        },
        "model_derivatives": {
            "agent_id": "model_derivatives",
            "agent_type": "model_derivatives",
            "name": "Model Derivatives Agent",
            "description": "SQLite database integration for model derivatives",
            "specific_config": {
                "database_path": "./cache/derivatives.db"
            }
        }
    }
    
    # Initialize and register agents
    print("🤖 Initializing agents...")
    
    # Model Properties Agent
    model_properties_agent = ModelPropertiesAgent(agent_core, agents_config["model_properties"])
    await model_properties_agent.initialize()
    orchestrator.register_agent("model_properties", model_properties_agent)
    print("   ✅ Model Properties Agent ready")
    
    # AEC Data Model Agent
    aec_data_model_agent = AECDataModelAgent(agent_core, agents_config["aec_data_model"])
    await aec_data_model_agent.initialize()
    orchestrator.register_agent("aec_data_model", aec_data_model_agent)
    print("   ✅ AEC Data Model Agent ready")
    
    # Model Derivatives Agent
    model_derivatives_agent = ModelDerivativesAgent(agent_core, agents_config["model_derivatives"])
    await model_derivatives_agent.initialize()
    orchestrator.register_agent("model_derivatives", model_derivatives_agent)
    print("   ✅ Model Derivatives Agent ready")
    
    print("✅ All agents initialized")
    
    # Create API Gateway
    print("🌐 Setting up API Gateway...")
    api_gateway = APIGateway(orchestrator, config)
    await api_gateway.initialize()
    
    app = api_gateway.get_app()
    print("✅ API Gateway ready")
    
    # Display startup summary
    print()
    print("🎉 System Ready!")
    print("-" * 30)
    print("📊 Active Agents:")
    agents = orchestrator.get_registered_agents()
    for agent_id, agent in agents.items():
        capabilities = agent.get_capabilities()
        print(f"   • {capabilities.name}")
    
    print()
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    print(f"🌐 Server will start on: http://{host}:{port}")
    print(f"📚 API Documentation: http://{host}:{port}/docs")
    print(f"🏥 Health Check: http://{host}:{port}/health")
    print()
    
    return app


# Create the FastAPI app instance
app = None

async def startup():
    """Startup event handler."""
    global app
    app = await create_app()

def get_app():
    """Get the FastAPI app instance."""
    if app is None:
        # For uvicorn, we need to create the app synchronously
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        global app
        app = loop.run_until_complete(create_app())
    return app

# Create app instance for uvicorn
app = get_app()

if __name__ == "__main__":
    # Get configuration from environment
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    log_level = os.getenv("LOG_LEVEL", "info")
    reload = os.getenv("RELOAD", "false").lower() == "true"
    
    print(f"🚀 Starting server on {host}:{port}")
    
    # Run the server
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        log_level=log_level,
        reload=reload,
        access_log=True
    )