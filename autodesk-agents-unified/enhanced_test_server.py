#!/usr/bin/env python3
"""
Enhanced test server with realistic model properties responses
"""

import asyncio
import logging
from fastapi import FastAPI
from fastapi.responses import JSONResponse
import uvicorn

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(title="Enhanced Unified Agent System", version="1.0.0")

@app.get("/")
async def root():
    return {"message": "Enhanced Unified Agent System is running!"}

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "message": "System is operational",
        "agents": {
            "model_properties": {"status": "ready"},
            "aec_data_model": {"status": "ready"}, 
            "model_derivatives": {"status": "ready"}
        }
    }

@app.post("/api/v1/model-properties/prompt")
async def model_properties_enhanced(request: dict):
    prompt = request.get("prompt", "")
    
    # Simulate realistic model properties responses based on prompt
    if "wall" in prompt.lower():
        return {
            "responses": [
                "I found wall properties in your model:",
                "• Wall Height: 3.0m (average)",
                "• Wall Width: 0.2m (typical)",
                "• Wall Material: Concrete, Brick, Drywall",
                "• Wall Count: 45 walls found",
                "• Wall Area: 1,250 m² (total)"
            ],
            "success": True,
            "agent_type": "model_properties",
            "metadata": {
                "elements_found": 45,
                "properties_analyzed": ["Height", "Width", "Material", "Area"],
                "project_id": "demo_project_123"
            }
        }
    elif "door" in prompt.lower():
        return {
            "responses": [
                "I found door properties in your model:",
                "• Door Height: 2.1m (standard)",
                "• Door Width: 0.9m (typical)",
                "• Door Material: Wood, Steel, Glass",
                "• Door Count: 28 doors found",
                "• Door Types: Single, Double, Sliding"
            ],
            "success": True,
            "agent_type": "model_properties",
            "metadata": {
                "elements_found": 28,
                "properties_analyzed": ["Height", "Width", "Material", "Type"],
                "project_id": "demo_project_123"
            }
        }
    elif "window" in prompt.lower():
        return {
            "responses": [
                "I found window properties in your model:",
                "• Window Height: 1.5m (average)",
                "• Window Width: 1.2m (typical)",
                "• Window Material: Glass, Aluminum Frame",
                "• Window Count: 67 windows found",
                "• Window Types: Fixed, Casement, Sliding"
            ],
            "success": True,
            "agent_type": "model_properties",
            "metadata": {
                "elements_found": 67,
                "properties_analyzed": ["Height", "Width", "Material", "Type"],
                "project_id": "demo_project_123"
            }
        }
    elif "list" in prompt.lower() or "available" in prompt.lower():
        return {
            "responses": [
                "Available properties in your model:",
                "📊 Element Categories:",
                "• Walls (45 elements)",
                "• Doors (28 elements)", 
                "• Windows (67 elements)",
                "• Floors (12 elements)",
                "• Roofs (3 elements)",
                "",
                "🔧 Available Properties:",
                "• Geometric: Height, Width, Length, Area, Volume",
                "• Material: Type, Finish, Thickness",
                "• Structural: Load Bearing, Fire Rating",
                "• Thermal: R-Value, U-Value"
            ],
            "success": True,
            "agent_type": "model_properties",
            "metadata": {
                "total_elements": 155,
                "categories": 5,
                "property_types": 12,
                "project_id": "demo_project_123"
            }
        }
    elif "area" in prompt.lower() or "size" in prompt.lower():
        return {
            "responses": [
                "Element areas in your model:",
                "📐 Area Analysis:",
                "• Total Floor Area: 2,450 m²",
                "• Wall Surface Area: 1,250 m²",
                "• Window Area: 180 m²",
                "• Door Area: 56 m²",
                "",
                "🏢 Space Breakdown:",
                "• Office Spaces: 1,800 m²",
                "• Common Areas: 450 m²",
                "• Circulation: 200 m²"
            ],
            "success": True,
            "agent_type": "model_properties",
            "metadata": {
                "total_area": 2450,
                "analysis_type": "area_calculation",
                "project_id": "demo_project_123"
            }
        }
    else:
        return {
            "responses": [
                "I can help you analyze model properties! Here's what I can do:",
                "",
                "🔍 Query Examples:",
                "• 'Show me wall properties'",
                "• 'List all door dimensions'", 
                "• 'What window types are available?'",
                "• 'Calculate total floor area'",
                "• 'List all available properties'",
                "",
                "📊 I can analyze:",
                "• Element dimensions and geometry",
                "• Material properties and specifications",
                "• Quantities and areas",
                "• Element relationships and connections"
            ],
            "success": True,
            "agent_type": "model_properties",
            "metadata": {
                "help_provided": True,
                "project_id": "demo_project_123"
            }
        }

@app.post("/api/v1/aec-data-model/prompt")
async def aec_data_model_enhanced(request: dict):
    prompt = request.get("prompt", "")
    
    if "wall" in prompt.lower():
        return {
            "responses": [
                "Found wall elements in the AEC data model:",
                "🧱 Wall Elements (45 found):",
                "• Exterior Walls: 28 elements",
                "• Interior Walls: 17 elements",
                "• Load-bearing: 12 elements",
                "• Partition: 33 elements",
                "",
                "📋 Properties Available:",
                "• Structural properties: Thickness, Material, Load capacity",
                "• Thermal properties: R-value, U-value",
                "• Fire rating: 1-hour, 2-hour ratings"
            ],
            "success": True,
            "agent_type": "aec_data_model",
            "metadata": {
                "elements_found": 45,
                "element_types": ["exterior", "interior", "load_bearing", "partition"],
                "graphql_query_executed": True
            }
        }
    else:
        return {
            "responses": [
                "AEC Data Model agent ready! I can help you query building elements:",
                "• Find specific element types (walls, doors, windows)",
                "• Analyze element relationships and connections", 
                "• Query element properties and attributes",
                "• Search using GraphQL-based queries"
            ],
            "success": True,
            "agent_type": "aec_data_model"
        }

@app.post("/api/v1/model-derivatives/prompt")
async def model_derivatives_enhanced(request: dict):
    prompt = request.get("prompt", "")
    
    if "database" in prompt.lower() or "setup" in prompt.lower():
        return {
            "responses": [
                "Setting up SQLite database for model derivatives:",
                "📊 Database Setup Complete:",
                "• Properties loaded: 1,247 elements",
                "• Database size: 2.3 MB",
                "• Tables created: elements, properties, relationships",
                "• Indexes created for optimal query performance",
                "",
                "✅ Ready for SQL queries!"
            ],
            "success": True,
            "agent_type": "model_derivatives",
            "metadata": {
                "database_setup": True,
                "elements_loaded": 1247,
                "database_size_mb": 2.3
            }
        }
    elif "query" in prompt.lower() or "sql" in prompt.lower():
        return {
            "responses": [
                "Executing SQL query on model derivatives:",
                "🔍 Query Results:",
                "• Found 23 elements matching criteria",
                "• Average area: 45.2 m²",
                "• Total volume: 1,038 m³",
                "",
                "📋 Sample Results:",
                "• Element ID: 1001, Type: Wall, Area: 52.3 m²",
                "• Element ID: 1045, Type: Floor, Area: 125.7 m²",
                "• Element ID: 1089, Type: Roof, Area: 89.1 m²"
            ],
            "success": True,
            "agent_type": "model_derivatives",
            "metadata": {
                "query_executed": True,
                "results_count": 23,
                "execution_time_ms": 45
            }
        }
    else:
        return {
            "responses": [
                "Model Derivatives agent ready! I can help you:",
                "• Set up SQLite database from model derivatives",
                "• Execute SQL queries on element properties",
                "• Analyze geometric and property data",
                "• Generate reports and summaries"
            ],
            "success": True,
            "agent_type": "model_derivatives"
        }

if __name__ == "__main__":
    logger.info("🚀 Starting Enhanced Test Server...")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")