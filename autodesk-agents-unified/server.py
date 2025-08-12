#!/usr/bin/env python3
"""
Unified Agent System Server

This script starts the unified agent system with all three agent types
(Model Properties, AEC Data Model, Model Derivatives) running through
the AgentCore framework and Strands orchestrator.
"""

import os
import sys
import asyncio
import logging
import argparse
from pathlib import Path

import uvicorn
from fastapi import FastAPI

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from agent_core.core import AgentCore
from agent_core.config import CoreConfig
from agent_core.orchestrator import StrandsOrchestrator
from agent_core.api_gateway import APIGateway
from agent_core.agents.model_properties_agent import ModelPropertiesAgent
from agent_core.agents.aec_data_model_agent import AECDataModelAgent
from agent_core.agents.model_derivatives_agent import ModelDerivativesAgent


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class UnifiedAgentServer:
    """Unified Agent System Server"""
    
    def __init__(self, config_path: str = None, host: str = "0.0.0.0", port: int = 8000):
        self.config_path = config_path
        self.host = host
        self.port = port
        self.agent_core = None
        self.orchestrator = None
        self.api_gateway = None
        self.app = None
    
    async def initialize(self):
        """Initialize the unified agent system"""
        logger.info("🚀 Initializing Unified Agent System...")
        
        try:
            # 1. Initialize AgentCore
            logger.info("📋 Initializing AgentCore...")
            if self.config_path:
                config = CoreConfig.from_file(self.config_path)
            else:
                config = CoreConfig()
            
            self.agent_core = AgentCore(config)
            await self.agent_core.initialize()
            logger.info("✅ AgentCore initialized successfully")
            
            # 2. Initialize Strands Orchestrator
            logger.info("🎭 Initializing Strands Orchestrator...")
            self.orchestrator = StrandsOrchestrator(self.agent_core)
            await self.orchestrator.initialize()
            logger.info("✅ Strands Orchestrator initialized successfully")
            
            # 3. Register all three agent types
            logger.info("🤖 Registering agents...")
            
            # Model Properties Agent
            logger.info("  - Registering Model Properties Agent...")
            mp_agent = ModelPropertiesAgent(self.agent_core)
            await self.orchestrator.register_agent("model_properties", mp_agent)
            logger.info("    ✅ Model Properties Agent registered")
            
            # AEC Data Model Agent
            logger.info("  - Registering AEC Data Model Agent...")
            aec_agent = AECDataModelAgent(self.agent_core)
            await self.orchestrator.register_agent("aec_data_model", aec_agent)
            logger.info("    ✅ AEC Data Model Agent registered")
            
            # Model Derivatives Agent
            logger.info("  - Registering Model Derivatives Agent...")
            md_agent = ModelDerivativesAgent(self.agent_core)
            await self.orchestrator.register_agent("model_derivatives", md_agent)
            logger.info("    ✅ Model Derivatives Agent registered")
            
            logger.info("✅ All agents registered successfully")
            
            # 4. Initialize API Gateway
            logger.info("🌐 Initializing API Gateway...")
            self.api_gateway = APIGateway(
                strands=self.orchestrator,
                cors_origins=["*"],  # Configure as needed
                trusted_hosts=["*"]  # Configure as needed
            )
            await self.api_gateway.startup()
            self.app = self.api_gateway.get_app()
            logger.info("✅ API Gateway initialized successfully")
            
            # 5. Display system information
            await self._display_system_info()
            
            logger.info("🎉 Unified Agent System initialization complete!")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize system: {e}")
            await self.shutdown()
            raise
    
    async def _display_system_info(self):
        """Display system information"""
        logger.info("📊 System Information:")
        
        # AgentCore info
        system_info = await self.agent_core.get_system_info()
        logger.info(f"  🔧 AgentCore:")
        logger.info(f"    - Status: {'✅ Healthy' if system_info['healthy'] else '❌ Unhealthy'}")
        logger.info(f"    - AWS Region: {system_info['config']['aws_region']}")
        logger.info(f"    - Log Level: {system_info['config']['log_level']}")
        logger.info(f"    - Cache Directory: {system_info['config']['cache_directory']}")
        
        # Orchestrator info
        orchestrator_status = await self.orchestrator.get_orchestrator_status()
        logger.info(f"  🎭 Orchestrator:")
        logger.info(f"    - Status: {'✅ Initialized' if orchestrator_status['initialized'] else '❌ Not Initialized'}")
        logger.info(f"    - Registered Agents: {len(orchestrator_status['agents'])}")
        
        for agent_name, agent_info in orchestrator_status['agents'].items():
            status = "✅ Ready" if agent_info.get('initialized', False) else "❌ Not Ready"
            logger.info(f"      - {agent_name}: {status}")
        
        # API Gateway info
        gateway_metrics = self.api_gateway.get_metrics()
        logger.info(f"  🌐 API Gateway:")
        logger.info(f"    - Registered Agents: {len(gateway_metrics['registered_agents'])}")
        logger.info(f"    - Start Time: {gateway_metrics['start_time']}")
    
    async def shutdown(self):
        """Shutdown the unified agent system"""
        logger.info("🛑 Shutting down Unified Agent System...")
        
        try:
            if self.api_gateway:
                await self.api_gateway.shutdown()
                logger.info("✅ API Gateway shutdown complete")
            
            if self.orchestrator:
                await self.orchestrator.shutdown()
                logger.info("✅ Orchestrator shutdown complete")
            
            if self.agent_core:
                await self.agent_core.shutdown()
                logger.info("✅ AgentCore shutdown complete")
            
            logger.info("✅ Unified Agent System shutdown complete")
            
        except Exception as e:
            logger.error(f"❌ Error during shutdown: {e}")
    
    async def run_async(self):
        """Run the unified agent system server asynchronously"""
        logger.info(f"🚀 Starting Unified Agent System Server on {self.host}:{self.port}")
        
        # Initialize the system first
        await self.initialize()
        
        # Create uvicorn config
        config = uvicorn.Config(
            app=self.app,
            host=self.host,
            port=self.port,
            log_level="info",
            access_log=True,
            reload=False,
            workers=1
        )
        
        server = uvicorn.Server(config)
        
        # Run the server
        try:
            await server.serve()
        except KeyboardInterrupt:
            logger.info("🛑 Server stopped by user")
        except Exception as e:
            logger.error(f"❌ Server error: {e}")
            raise
        finally:
            await self.shutdown()
    
    def run(self):
        """Run the unified agent system server"""
        try:
            asyncio.run(self.run_async())
        except KeyboardInterrupt:
            logger.info("🛑 Server stopped by user")
        except Exception as e:
            logger.error(f"❌ Server error: {e}")
            sys.exit(1)


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Unified Agent System Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    parser.add_argument("--config", help="Path to configuration file")
    parser.add_argument("--dev", action="store_true", help="Run in development mode")
    
    args = parser.parse_args()
    
    # Set development mode
    if args.dev:
        logging.getLogger().setLevel(logging.DEBUG)
        os.environ["DEVELOPMENT"] = "true"
    
    # Create and run server
    server = UnifiedAgentServer(
        config_path=args.config,
        host=args.host,
        port=args.port
    )
    
    server.run()


if __name__ == "__main__":
    main()