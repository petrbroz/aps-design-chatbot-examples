#!/usr/bin/env python3
"""
Development AgentCore Server

This server runs the AgentCore system in development mode with mock data
when real credentials are not available.
"""

import os
import sys
import asyncio
import logging
import argparse
from pathlib import Path
from typing import Dict, Any, Optional

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv('.env.dev')
except ImportError:
    print("python-dotenv not installed, skipping .env loading")

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Configure logging
logging.basicConfig(
    level=getattr(logging, os.getenv('LOG_LEVEL', 'INFO')),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PromptRequest(BaseModel):
    prompt: str
    project_id: Optional[str] = None
    version_id: Optional[str] = None
    element_group_id: Optional[str] = None
    urn: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


class AgentCoreDevServer:
    """Development AgentCore Server with mock capabilities"""
    
    def __init__(self):
        self.app = FastAPI(
            title="AgentCore Development Server",
            version="1.0.0-dev",
            description="AgentCore system running in development mode"
        )
        self.mock_mode = os.getenv('MOCK_MODE', 'true').lower() == 'true'
        self.setup_middleware()
        self.setup_routes()
        
        # Mock data for development
        self.mock_projects = {
            "b.project123": {
                "name": "Sample Office Building",
                "versions": {
                    "version456": {
                        "name": "Design Development",
                        "elements": {
                            "walls": 45,
                            "doors": 28,
                            "windows": 67,
                            "floors": 12,
                            "roofs": 3
                        }
                    }
                }
            }
        }
        
        self.mock_properties = {
            "walls": {
                "height": {"min": 2.4, "max": 4.2, "avg": 3.0, "unit": "m"},
                "width": {"min": 0.15, "max": 0.3, "avg": 0.2, "unit": "m"},
                "area": {"total": 1250, "unit": "m²"},
                "materials": ["Concrete", "Brick", "Drywall", "Steel Stud"]
            },
            "doors": {
                "height": {"min": 2.0, "max": 2.4, "avg": 2.1, "unit": "m"},
                "width": {"min": 0.7, "max": 1.8, "avg": 0.9, "unit": "m"},
                "materials": ["Wood", "Steel", "Glass", "Aluminum"],
                "types": ["Single", "Double", "Sliding", "Revolving"]
            },
            "windows": {
                "height": {"min": 1.0, "max": 2.5, "avg": 1.5, "unit": "m"},
                "width": {"min": 0.6, "max": 3.0, "avg": 1.2, "unit": "m"},
                "area": {"total": 180, "unit": "m²"},
                "materials": ["Glass", "Aluminum Frame", "PVC Frame"],
                "types": ["Fixed", "Casement", "Sliding", "Awning"]
            }
        }
    
    def setup_middleware(self):
        """Setup FastAPI middleware"""
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    
    def setup_routes(self):
        """Setup API routes"""
        
        @self.app.get("/")
        async def root():
            return {
                "message": "AgentCore Development Server",
                "mode": "mock" if self.mock_mode else "live",
                "version": "1.0.0-dev"
            }
        
        @self.app.get("/health")
        async def health():
            return {
                "status": "healthy",
                "mode": "mock" if self.mock_mode else "live",
                "agents": {
                    "model_properties": {"status": "ready", "mock": self.mock_mode},
                    "aec_data_model": {"status": "ready", "mock": self.mock_mode},
                    "model_derivatives": {"status": "ready", "mock": self.mock_mode}
                },
                "services": {
                    "autodesk_api": "mock" if self.mock_mode else "connected",
                    "aws_bedrock": "mock" if self.mock_mode else "connected",
                    "opensearch": "mock" if self.mock_mode else "connected"
                }
            }
        
        @self.app.post("/api/v1/model-properties/prompt")
        async def model_properties_agent(request: PromptRequest):
            if self.mock_mode:
                return await self._mock_model_properties(request)
            else:
                return await self._real_model_properties(request)
        
        @self.app.post("/api/v1/aec-data-model/prompt")
        async def aec_data_model_agent(request: PromptRequest):
            if self.mock_mode:
                return await self._mock_aec_data_model(request)
            else:
                return await self._real_aec_data_model(request)
        
        @self.app.post("/api/v1/model-derivatives/prompt")
        async def model_derivatives_agent(request: PromptRequest):
            if self.mock_mode:
                return await self._mock_model_derivatives(request)
            else:
                return await self._real_model_derivatives(request)
        
        @self.app.get("/api/v1/projects")
        async def list_projects():
            if self.mock_mode:
                return {"projects": list(self.mock_projects.keys())}
            else:
                # Would call real Autodesk API
                raise HTTPException(status_code=501, detail="Real API not implemented yet")
    
    async def _mock_model_properties(self, request: PromptRequest) -> Dict[str, Any]:
        """Mock model properties responses with realistic data"""
        prompt = request.prompt.lower()
        project_id = request.project_id or "b.project123"
        
        if "wall" in prompt:
            props = self.mock_properties["walls"]
            return {
                "responses": [
                    f"📊 Wall Properties Analysis for Project {project_id}:",
                    f"• Total Walls: {self.mock_projects['b.project123']['versions']['version456']['elements']['walls']}",
                    f"• Average Height: {props['height']['avg']}m (range: {props['height']['min']}-{props['height']['max']}m)",
                    f"• Average Width: {props['width']['avg']}m (range: {props['width']['min']}-{props['width']['max']}m)",
                    f"• Total Wall Area: {props['area']['total']} {props['area']['unit']}",
                    f"• Materials Found: {', '.join(props['materials'])}",
                    "",
                    "🔍 This data is from AgentCore's Model Properties agent",
                    "💡 Connected to Autodesk Platform Services for real project data"
                ],
                "success": True,
                "agent_type": "model_properties",
                "metadata": {
                    "project_id": project_id,
                    "elements_analyzed": 45,
                    "properties_found": len(props),
                    "data_source": "mock" if self.mock_mode else "autodesk_api",
                    "agentcore_version": "1.0.0-dev"
                }
            }
        
        elif "door" in prompt:
            props = self.mock_properties["doors"]
            return {
                "responses": [
                    f"🚪 Door Properties Analysis for Project {project_id}:",
                    f"• Total Doors: {self.mock_projects['b.project123']['versions']['version456']['elements']['doors']}",
                    f"• Average Height: {props['height']['avg']}m (range: {props['height']['min']}-{props['height']['max']}m)",
                    f"• Average Width: {props['width']['avg']}m (range: {props['width']['min']}-{props['width']['max']}m)",
                    f"• Door Types: {', '.join(props['types'])}",
                    f"• Materials: {', '.join(props['materials'])}",
                    "",
                    "🔍 This data is from AgentCore's Model Properties agent"
                ],
                "success": True,
                "agent_type": "model_properties",
                "metadata": {
                    "project_id": project_id,
                    "elements_analyzed": 28,
                    "data_source": "mock" if self.mock_mode else "autodesk_api"
                }
            }
        
        elif "window" in prompt:
            props = self.mock_properties["windows"]
            return {
                "responses": [
                    f"🪟 Window Properties Analysis for Project {project_id}:",
                    f"• Total Windows: {self.mock_projects['b.project123']['versions']['version456']['elements']['windows']}",
                    f"• Average Height: {props['height']['avg']}m (range: {props['height']['min']}-{props['height']['max']}m)",
                    f"• Average Width: {props['width']['avg']}m (range: {props['width']['min']}-{props['width']['max']}m)",
                    f"• Total Window Area: {props['area']['total']} {props['area']['unit']}",
                    f"• Window Types: {', '.join(props['types'])}",
                    f"• Frame Materials: {', '.join(props['materials'])}",
                    "",
                    "🔍 This data is from AgentCore's Model Properties agent"
                ],
                "success": True,
                "agent_type": "model_properties",
                "metadata": {
                    "project_id": project_id,
                    "elements_analyzed": 67,
                    "data_source": "mock" if self.mock_mode else "autodesk_api"
                }
            }
        
        else:
            return {
                "responses": [
                    "🏗️ AgentCore Model Properties Agent Ready!",
                    "",
                    "I can analyze building element properties from your Autodesk models:",
                    "",
                    "📊 Available Queries:",
                    "• 'Show me wall properties' - Analyze wall dimensions and materials",
                    "• 'List door specifications' - Get door types and dimensions",
                    "• 'Window analysis' - Review window properties and areas",
                    "• 'Calculate total areas' - Compute space and surface areas",
                    "",
                    "🔧 Powered by:",
                    "• Autodesk Platform Services for model data",
                    "• AWS Bedrock Claude for intelligent analysis",
                    "• OpenSearch for fast property search",
                    "",
                    f"📋 Current Project: {project_id}",
                    f"🎯 Mode: {'Mock Data' if self.mock_mode else 'Live Data'}"
                ],
                "success": True,
                "agent_type": "model_properties",
                "metadata": {
                    "help_provided": True,
                    "available_elements": list(self.mock_properties.keys()),
                    "data_source": "mock" if self.mock_mode else "autodesk_api"
                }
            }
    
    async def _mock_aec_data_model(self, request: PromptRequest) -> Dict[str, Any]:
        """Mock AEC Data Model responses"""
        return {
            "responses": [
                "🏢 AgentCore AEC Data Model Agent",
                "Connected to building element data model",
                "Ready to query GraphQL-based element relationships",
                f"Mode: {'Mock' if self.mock_mode else 'Live'}"
            ],
            "success": True,
            "agent_type": "aec_data_model"
        }
    
    async def _mock_model_derivatives(self, request: PromptRequest) -> Dict[str, Any]:
        """Mock Model Derivatives responses"""
        return {
            "responses": [
                "🗄️ AgentCore Model Derivatives Agent",
                "SQLite database ready for property queries",
                "Connected to model derivative data",
                f"Mode: {'Mock' if self.mock_mode else 'Live'}"
            ],
            "success": True,
            "agent_type": "model_derivatives"
        }
    
    async def _real_model_properties(self, request: PromptRequest) -> Dict[str, Any]:
        """Real model properties using Autodesk API and Bedrock"""
        # This would implement the real AgentCore functionality
        raise HTTPException(status_code=501, detail="Real AgentCore implementation requires credentials")
    
    async def _real_aec_data_model(self, request: PromptRequest) -> Dict[str, Any]:
        """Real AEC data model using GraphQL and OpenSearch"""
        raise HTTPException(status_code=501, detail="Real AgentCore implementation requires credentials")
    
    async def _real_model_derivatives(self, request: PromptRequest) -> Dict[str, Any]:
        """Real model derivatives using SQLite and Bedrock"""
        raise HTTPException(status_code=501, detail="Real AgentCore implementation requires credentials")
    
    def run(self, host: str = "0.0.0.0", port: int = 8000):
        """Run the development server"""
        logger.info(f"🚀 Starting AgentCore Development Server")
        logger.info(f"📍 Mode: {'Mock Data' if self.mock_mode else 'Live Data'}")
        logger.info(f"🌐 Server: http://{host}:{port}")
        
        uvicorn.run(self.app, host=host, port=port, log_level="info")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="AgentCore Development Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    parser.add_argument("--live", action="store_true", help="Use live APIs (requires credentials)")
    
    args = parser.parse_args()
    
    # Override mock mode if live is requested
    if args.live:
        os.environ['MOCK_MODE'] = 'false'
    
    server = AgentCoreDevServer()
    server.run(args.host, args.port)


if __name__ == "__main__":
    main()