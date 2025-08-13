"""
AgentCore - Unified Autodesk Agent Framework

A production-ready framework for building and deploying Autodesk API agents
with real-time data integration, vector search, and intelligent responses.
"""

from .core import AgentCore
from .config import CoreConfig, AgentConfig, ConfigManager
from .auth import AuthenticationManager, AuthContext
from .logging import StructuredLogger, TraceContext
from .health import HealthMonitor
from .cache import CacheManager
from .models import (
    AgentRequest, AgentResponse, AgentCapabilities,
    ExecutionContext, ToolResult, ErrorCodes, AgentType
)
from .base_agent import BaseAgent, AgentExecutionError
from .error_handler import ErrorHandler, ErrorContext, ErrorSeverity
from .strands import StrandsOrchestrator, AgentRouter, AgentStatus
from .tools import ToolRegistry, BaseTool, FunctionTool, ToolCategory, ToolMetadata
from .vector_store import OpenSearchVectorStore, BedrockEmbeddings, Document, SearchResult

__version__ = "1.0.0"
__all__ = [
    "AgentCore",
    "CoreConfig", 
    "AgentConfig",
    "ConfigManager",
    "AuthenticationManager",
    "AuthContext",
    "StructuredLogger",
    "TraceContext",
    "HealthMonitor",
    "CacheManager",
    "AgentRequest",
    "AgentResponse", 
    "AgentCapabilities",
    "ExecutionContext",
    "ToolResult",
    "ErrorCodes",
    "AgentType",
    "BaseAgent",
    "AgentExecutionError",
    "ErrorHandler",
    "ErrorContext",
    "ErrorSeverity",
    "StrandsOrchestrator",
    "AgentRouter",
    "AgentStatus",
    "ToolRegistry",
    "BaseTool",
    "FunctionTool",
    "ToolCategory",
    "ToolMetadata",
    "OpenSearchVectorStore",
    "BedrockEmbeddings",
    "Document",
    "SearchResult"
]