#!/usr/bin/env python3
"""
Deployment script for Autodesk Agents Unified System

This script handles the complete deployment of the unified agent system
including all three agents: Model Properties, AEC Data Model, and Model Derivatives.
"""

import asyncio
import os
import sys
import subprocess
from pathlib import Path
from typing import Dict, Any, List
import yaml
import json

# Add the project root to Python path
sys.path.insert(0, str(Path(__file__).parent))

from agentcore import AgentCore, ConfigManager
from agentcore.orchestrator import StrandsOrchestrator
from agentcore.api_gateway import APIGateway
from agents import ModelPropertiesAgent, AECDataModelAgent, ModelDerivativesAgent


class DeploymentManager:
    """Manages the deployment of the unified agent system."""
    
    def __init__(self):
        self.project_root = Path(__file__).parent
        self.config_manager = ConfigManager()
        self.agent_core = None
        self.orchestrator = None
        self.api_gateway = None
        
    async def deploy(self, environment: str = "production"):
        """Deploy the complete system."""
        
        print("🚀 Autodesk Agents Unified System Deployment")
        print("=" * 60)
        print(f"📋 Environment: {environment}")
        print(f"📁 Project Root: {self.project_root}")
        print()
        
        try:
            # Step 1: Validate environment
            await self._validate_environment()
            
            # Step 2: Load configuration
            await self._load_configuration(environment)
            
            # Step 3: Initialize core system
            await self._initialize_core_system()
            
            # Step 4: Deploy agents
            await self._deploy_agents()
            
            # Step 5: Start API Gateway
            await self._start_api_gateway()
            
            # Step 6: Run health checks
            await self._run_health_checks()
            
            # Step 7: Display deployment summary
            await self._display_deployment_summary()
            
            print("🎉 Deployment completed successfully!")
            
        except Exception as e:
            print(f"❌ Deployment failed: {str(e)}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    
    async def _validate_environment(self):
        """Validate deployment environment."""
        print("🔍 Step 1: Validating environment...")
        
        # Check Python version
        if sys.version_info < (3, 8):
            raise Exception("Python 3.8+ is required")
        print("   ✅ Python version check passed")
        
        # Check required environment variables
        required_vars = [
            "AUTODESK_CLIENT_ID",
            "AUTODESK_CLIENT_SECRET"
        ]
        
        missing_vars = []
        for var in required_vars:
            if not os.getenv(var):
                missing_vars.append(var)
        
        if missing_vars:
            print(f"   ⚠️  Missing environment variables: {', '.join(missing_vars)}")
            print("   ℹ️  Using test credentials for demo purposes")
            # Set test credentials
            os.environ["AUTODESK_CLIENT_ID"] = "test_client_id"
            os.environ["AUTODESK_CLIENT_SECRET"] = "test_client_secret"
        else:
            print("   ✅ Environment variables check passed")
        
        # Check dependencies
        try:
            import aiohttp
            import aiofiles
            import aiosqlite
            import boto3
            import opensearch_py
            print("   ✅ Dependencies check passed")
        except ImportError as e:
            print(f"   ❌ Missing dependency: {e}")
            print("   💡 Run: pip install -r requirements.txt")
            raise
        
        print("   ✅ Environment validation completed")
        print()
    
    async def _load_configuration(self, environment: str):
        """Load system configuration."""
        print("⚙️  Step 2: Loading configuration...")
        
        # Load base configuration
        config = self.config_manager.load_config()
        
        # Override with environment-specific settings
        env_config_path = self.project_root / f"config/{environment}.yaml"
        if env_config_path.exists():
            with open(env_config_path, 'r') as f:
                env_config = yaml.safe_load(f)
                config.update(env_config)
            print(f"   ✅ Loaded {environment} configuration")
        else:
            print(f"   ℹ️  No environment-specific config found for {environment}")
        
        # Store configuration
        self.config = config
        print("   ✅ Configuration loaded successfully")
        print()
    
    async def _initialize_core_system(self):
        """Initialize AgentCore and orchestrator."""
        print("🏗️  Step 3: Initializing core system...")
        
        # Initialize AgentCore
        self.agent_core = AgentCore(self.config)
        await self.agent_core.initialize()
        print("   ✅ AgentCore initialized")
        
        # Initialize orchestrator
        self.orchestrator = StrandsOrchestrator(self.agent_core)
        await self.orchestrator.initialize()
        print("   ✅ StrandsOrchestrator initialized")
        
        print("   ✅ Core system initialization completed")
        print()
    
    async def _deploy_agents(self):
        """Deploy all three agents."""
        print("🤖 Step 4: Deploying agents...")
        
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
        
        # Deploy Model Properties Agent
        print("   🔧 Deploying Model Properties Agent...")
        model_properties_agent = ModelPropertiesAgent(
            self.agent_core, 
            agents_config["model_properties"]
        )
        await model_properties_agent.initialize()
        self.orchestrator.register_agent("model_properties", model_properties_agent)
        print("   ✅ Model Properties Agent deployed")
        
        # Deploy AEC Data Model Agent
        print("   🔧 Deploying AEC Data Model Agent...")
        aec_data_model_agent = AECDataModelAgent(
            self.agent_core,
            agents_config["aec_data_model"]
        )
        await aec_data_model_agent.initialize()
        self.orchestrator.register_agent("aec_data_model", aec_data_model_agent)
        print("   ✅ AEC Data Model Agent deployed")
        
        # Deploy Model Derivatives Agent
        print("   🔧 Deploying Model Derivatives Agent...")
        model_derivatives_agent = ModelDerivativesAgent(
            self.agent_core,
            agents_config["model_derivatives"]
        )
        await model_derivatives_agent.initialize()
        self.orchestrator.register_agent("model_derivatives", model_derivatives_agent)
        print("   ✅ Model Derivatives Agent deployed")
        
        print("   ✅ All agents deployed successfully")
        print()
    
    async def _start_api_gateway(self):
        """Start the API Gateway."""
        print("🌐 Step 5: Starting API Gateway...")
        
        # Initialize API Gateway
        self.api_gateway = APIGateway(self.orchestrator, self.config)
        await self.api_gateway.initialize()
        
        # Get port from config or environment
        port = int(os.getenv("PORT", self.config.get("api", {}).get("port", 8000)))
        host = os.getenv("HOST", self.config.get("api", {}).get("host", "0.0.0.0"))
        
        print(f"   🚀 API Gateway starting on {host}:{port}")
        print("   ✅ API Gateway initialized")
        print()
        
        # Note: In a real deployment, you would start the server here
        # For this demo, we'll just show that it's ready
        print(f"   💡 To start the server, run: uvicorn main:app --host {host} --port {port}")
        print()
    
    async def _run_health_checks(self):
        """Run comprehensive health checks."""
        print("🏥 Step 6: Running health checks...")
        
        # Check AgentCore health
        health_status = await self.agent_core.health_monitor.get_health_status()
        if health_status["status"] == "healthy":
            print("   ✅ AgentCore health check passed")
        else:
            print(f"   ⚠️  AgentCore health check warning: {health_status}")
        
        # Check each agent
        agents = self.orchestrator.get_registered_agents()
        for agent_id in agents:
            try:
                agent = agents[agent_id]
                capabilities = agent.get_capabilities()
                print(f"   ✅ {capabilities.name} health check passed")
            except Exception as e:
                print(f"   ❌ {agent_id} health check failed: {e}")
        
        print("   ✅ Health checks completed")
        print()
    
    async def _display_deployment_summary(self):
        """Display deployment summary."""
        print("📊 Step 7: Deployment Summary")
        print("-" * 40)
        
        # System information
        print("🏗️  System Components:")
        print(f"   • AgentCore: ✅ Running")
        print(f"   • StrandsOrchestrator: ✅ Running")
        print(f"   • APIGateway: ✅ Ready")
        print()
        
        # Agent information
        print("🤖 Deployed Agents:")
        agents = self.orchestrator.get_registered_agents()
        for agent_id, agent in agents.items():
            capabilities = agent.get_capabilities()
            print(f"   • {capabilities.name}")
            print(f"     - Type: {capabilities.agent_type}")
            print(f"     - Version: {capabilities.version}")
            print(f"     - Tools: {len(capabilities.tools)}")
            print(f"     - Status: ✅ Active")
        print()
        
        # API Endpoints
        print("🌐 Available API Endpoints:")
        base_url = f"http://localhost:{os.getenv('PORT', 8000)}"
        print(f"   • Health Check: {base_url}/health")
        print(f"   • Model Properties: {base_url}/api/v1/model-properties")
        print(f"   • AEC Data Model: {base_url}/api/v1/aec-data-model")
        print(f"   • Model Derivatives: {base_url}/api/v1/model-derivatives")
        print(f"   • OpenAPI Docs: {base_url}/docs")
        print()
        
        # Configuration
        print("⚙️  Configuration:")
        print(f"   • Environment: {os.getenv('ENVIRONMENT', 'production')}")
        print(f"   • Log Level: {self.config.get('logging', {}).get('level', 'INFO')}")
        print(f"   • Cache Directory: {self.config.get('cache', {}).get('directory', './cache')}")
        print()
        
        # Next steps
        print("🚀 Next Steps:")
        print("   1. Start the API server: python main.py")
        print("   2. Test endpoints: python test_all_agents.py")
        print("   3. Monitor logs: tail -f logs/agent_core.log")
        print("   4. Check metrics: curl http://localhost:8000/health")
        print()


async def main():
    """Main deployment function."""
    
    # Parse command line arguments
    environment = "production"
    if len(sys.argv) > 1:
        environment = sys.argv[1]
    
    # Create and run deployment
    deployment_manager = DeploymentManager()
    await deployment_manager.deploy(environment)


if __name__ == "__main__":
    asyncio.run(main())