"""
Unified Tool Registry for AgentCore

Provides centralized tool management, registration, and discovery
for all agents with support for different tool types and categories.
"""

import asyncio
from typing import Dict, Any, List, Optional, Callable, Union
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from enum import Enum

from .models import ToolResult, ErrorCodes
from .logging import StructuredLogger


class ToolCategory(Enum):
    """Tool categories for organization."""
    API_CLIENT = "api_client"
    DATA_PROCESSING = "data_processing"
    QUERY_EXECUTION = "query_execution"
    FILE_OPERATIONS = "file_operations"
    VECTOR_SEARCH = "vector_search"
    DATABASE = "database"
    UTILITY = "utility"


@dataclass
class ToolMetadata:
    """Metadata for a registered tool."""
    name: str
    description: str
    category: ToolCategory
    version: str = "1.0.0"
    requires_auth: bool = True
    async_tool: bool = False
    parameters: Dict[str, Any] = field(default_factory=dict)
    returns: Dict[str, Any] = field(default_factory=dict)
    examples: List[Dict[str, Any]] = field(default_factory=list)


class BaseTool(ABC):
    """
    Abstract base class for all tools.
    
    Provides common functionality and enforces consistent interfaces
    for all tools used by agents.
    """
    
    def __init__(self, name: str, description: str, category: ToolCategory):
        """Initialize base tool."""
        self.name = name
        self.description = description
        self.category = category
        self.logger: Optional[StructuredLogger] = None
        self._initialized = False
    
    def set_logger(self, logger: StructuredLogger) -> None:
        """Set logger for the tool."""
        self.logger = logger
    
    async def initialize(self, **kwargs) -> None:
        """Initialize the tool with any required setup."""
        self._initialized = True
        if self.logger:
            self.logger.debug(f"Tool initialized: {self.name}")
    
    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """
        Execute the tool with given parameters.
        
        Returns:
            ToolResult with the execution result
        """
        pass
    
    def get_metadata(self) -> ToolMetadata:
        """Get tool metadata."""
        return ToolMetadata(
            name=self.name,
            description=self.description,
            category=self.category,
            async_tool=True
        )
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check for the tool."""
        return {
            "name": self.name,
            "status": "healthy" if self._initialized else "not_initialized",
            "initialized": self._initialized
        }
    
    async def shutdown(self) -> None:
        """Shutdown the tool and cleanup resources."""
        self._initialized = False
        if self.logger:
            self.logger.debug(f"Tool shutdown: {self.name}")


class ToolRegistry:
    """
    Centralized registry for all agent tools.
    
    Manages tool registration, discovery, and lifecycle across
    all agents in the system.
    """
    
    def __init__(self, logger: StructuredLogger):
        """Initialize tool registry."""
        self.logger = logger
        
        # Tool storage
        self._tools: Dict[str, BaseTool] = {}
        self._tool_metadata: Dict[str, ToolMetadata] = {}
        self._categories: Dict[ToolCategory, List[str]] = {}
        self._agent_tools: Dict[str, List[str]] = {}
        
        # Initialize categories
        for category in ToolCategory:
            self._categories[category] = []
    
    def register_tool(self, tool: BaseTool, agent_types: Optional[List[str]] = None) -> None:
        """
        Register a tool in the registry.
        
        Args:
            tool: The tool instance to register
            agent_types: List of agent types that can use this tool
        """
        if tool.name in self._tools:
            self.logger.warning(f"Tool already registered, replacing: {tool.name}")
        
        # Set logger for the tool
        tool.set_logger(self.logger)
        
        # Store tool and metadata
        self._tools[tool.name] = tool
        self._tool_metadata[tool.name] = tool.get_metadata()
        
        # Add to category
        if tool.category not in self._categories:
            self._categories[tool.category] = []
        if tool.name not in self._categories[tool.category]:
            self._categories[tool.category].append(tool.name)
        
        # Associate with agent types
        if agent_types:
            for agent_type in agent_types:
                if agent_type not in self._agent_tools:
                    self._agent_tools[agent_type] = []
                if tool.name not in self._agent_tools[agent_type]:
                    self._agent_tools[agent_type].append(tool.name)
        
        self.logger.info(f"Tool registered: {tool.name}", extra={
            "category": tool.category.value,
            "agent_types": agent_types or []
        })
    
    def unregister_tool(self, tool_name: str) -> bool:
        """
        Unregister a tool from the registry.
        
        Args:
            tool_name: Name of the tool to unregister
            
        Returns:
            True if tool was unregistered, False if not found
        """
        if tool_name not in self._tools:
            return False
        
        tool = self._tools[tool_name]
        
        # Remove from category
        if tool.category in self._categories:
            if tool_name in self._categories[tool.category]:
                self._categories[tool.category].remove(tool_name)
        
        # Remove from agent associations
        for agent_type, tools in self._agent_tools.items():
            if tool_name in tools:
                tools.remove(tool_name)
        
        # Remove from registry
        del self._tools[tool_name]
        del self._tool_metadata[tool_name]
        
        self.logger.info(f"Tool unregistered: {tool_name}")
        return True
    
    def get_tool(self, tool_name: str) -> Optional[BaseTool]:
        """Get a tool by name."""
        return self._tools.get(tool_name)
    
    def get_tools_for_agent(self, agent_type: str) -> List[BaseTool]:
        """Get all tools available for a specific agent type."""
        tool_names = self._agent_tools.get(agent_type, [])
        return [self._tools[name] for name in tool_names if name in self._tools]
    
    def get_tools_by_category(self, category: ToolCategory) -> List[BaseTool]:
        """Get all tools in a specific category."""
        tool_names = self._categories.get(category, [])
        return [self._tools[name] for name in tool_names if name in self._tools]
    
    def list_tools(self) -> List[str]:
        """List all registered tool names."""
        return list(self._tools.keys())
    
    def get_tool_metadata(self, tool_name: str) -> Optional[ToolMetadata]:
        """Get metadata for a specific tool."""
        return self._tool_metadata.get(tool_name)
    
    def search_tools(self, query: str, category: Optional[ToolCategory] = None) -> List[str]:
        """
        Search for tools by name or description.
        
        Args:
            query: Search query
            category: Optional category filter
            
        Returns:
            List of matching tool names
        """
        query_lower = query.lower()
        matches = []
        
        for tool_name, metadata in self._tool_metadata.items():
            # Category filter
            if category and metadata.category != category:
                continue
            
            # Text search
            if (query_lower in tool_name.lower() or 
                query_lower in metadata.description.lower()):
                matches.append(tool_name)
        
        return matches
    
    async def initialize_all_tools(self) -> None:
        """Initialize all registered tools."""
        self.logger.info("Initializing all tools")
        
        for tool_name, tool in self._tools.items():
            try:
                await tool.initialize()
                self.logger.debug(f"Tool initialized: {tool_name}")
            except Exception as e:
                self.logger.error(f"Failed to initialize tool {tool_name}", extra={
                    "error": str(e),
                    "error_type": type(e).__name__
                })
    
    async def shutdown_all_tools(self) -> None:
        """Shutdown all registered tools."""
        self.logger.info("Shutting down all tools")
        
        for tool_name, tool in self._tools.items():
            try:
                await tool.shutdown()
                self.logger.debug(f"Tool shutdown: {tool_name}")
            except Exception as e:
                self.logger.error(f"Failed to shutdown tool {tool_name}", extra={
                    "error": str(e),
                    "error_type": type(e).__name__
                })
    
    async def health_check_all_tools(self) -> Dict[str, Any]:
        """Perform health check on all tools."""
        tool_health = {}
        
        for tool_name, tool in self._tools.items():
            try:
                health = await tool.health_check()
                tool_health[tool_name] = health
            except Exception as e:
                tool_health[tool_name] = {
                    "name": tool_name,
                    "status": "error",
                    "error": str(e)
                }
        
        return {
            "total_tools": len(self._tools),
            "tools": tool_health,
            "categories": {
                category.value: len(tools) 
                for category, tools in self._categories.items()
            }
        }
    
    def get_registry_stats(self) -> Dict[str, Any]:
        """Get registry statistics."""
        return {
            "total_tools": len(self._tools),
            "categories": {
                category.value: len(tools) 
                for category, tools in self._categories.items()
            },
            "agent_associations": {
                agent_type: len(tools) 
                for agent_type, tools in self._agent_tools.items()
            }
        }


class FunctionTool(BaseTool):
    """
    Wrapper for simple function-based tools.
    
    Allows registering regular functions or async functions as tools
    without requiring a full BaseTool implementation.
    """
    
    def __init__(self, name: str, description: str, category: ToolCategory,
                 func: Callable, is_async: bool = None):
        """
        Initialize function tool.
        
        Args:
            name: Tool name
            description: Tool description
            category: Tool category
            func: Function to wrap
            is_async: Whether function is async (auto-detected if None)
        """
        super().__init__(name, description, category)
        self.func = func
        self.is_async = is_async if is_async is not None else asyncio.iscoroutinefunction(func)
    
    async def execute(self, **kwargs) -> ToolResult:
        """Execute the wrapped function."""
        try:
            if self.logger:
                self.logger.debug(f"Executing function tool: {self.name}", extra={
                    "kwargs_keys": list(kwargs.keys())
                })
            
            if self.is_async:
                result = await self.func(**kwargs)
            else:
                result = self.func(**kwargs)
            
            return ToolResult(
                output=result,
                success=True,
                tool_name=self.name
            )
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"Function tool execution failed: {self.name}", extra={
                    "error": str(e),
                    "error_type": type(e).__name__
                })
            
            return ToolResult.error(
                error_message=str(e),
                tool_name=self.name,
                error_type=type(e).__name__
            )
    
    def get_metadata(self) -> ToolMetadata:
        """Get tool metadata."""
        metadata = super().get_metadata()
        metadata.async_tool = self.is_async
        return metadata