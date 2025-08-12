#!/usr/bin/env python3
"""
Simple test server to verify the system works
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
app = FastAPI(title="Unified Agent System Test", version="1.0.0")

@app.get("/")
async def root():
    return {"message": "Unified Agent System is running!"}

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
async def model_properties_test(request: dict):
    return {
        "responses": [
            "This is a test response from the Model Properties agent.",
            "The unified system is working correctly!"
        ],
        "success": True,
        "agent_type": "model_properties"
    }

@app.post("/api/v1/aec-data-model/prompt")
async def aec_data_model_test(request: dict):
    return {
        "responses": [
            "This is a test response from the AEC Data Model agent.",
            "The unified system is working correctly!"
        ],
        "success": True,
        "agent_type": "aec_data_model"
    }

@app.post("/api/v1/model-derivatives/prompt")
async def model_derivatives_test(request: dict):
    return {
        "responses": [
            "This is a test response from the Model Derivatives agent.",
            "The unified system is working correctly!"
        ],
        "success": True,
        "agent_type": "model_derivatives"
    }

if __name__ == "__main__":
    logger.info("🚀 Starting Simple Test Server...")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")