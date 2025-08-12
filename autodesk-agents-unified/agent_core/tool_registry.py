"""
Tool Registry for centralized tool management in the AgentCore framework.
"""

import asyncio
from typing import Dict, List, Set, Optional, Any, Type
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

from .base_agent import BaseTool
from .models import ToolResult
from .logging import StructuredLogger


class ToolCategory(Enum):
    """Categories for organizing tools."""
    DATA_ACCESS = "data_access"
    QUERY_EXECUTION = "query_execution"
    FILE_OPERATIONS = "file_operations"
    AUTHENTICATION = "authentication"
    CACHING = "caching"
    TRANSFORMATION = "transformation"
    VALIDATION = "validation"
    MONITORING = "monitoring"
    GENERAL = "general"


@dataclass
class ToolMetadata:
    """Metadata for registered tools."""
    name: str
    description: str
    category: ToolCategory
    agent_types: Set[str] = field(default_factory=set)
    dependencies: List[str] = field(default_factory=list)
    version: str = "1.0.0"
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_used: Optional[datetime] = None
    usage_count: int = 0
    enabled: bool = True
    tags: Set[str] = field(default_factory=set)


@dataclass
class ToolRegistration:
    """Complete tool registration information."""
    tool_class: Type[BaseTool]
    metadata: ToolMetadata
    instance: Optional[BaseTool] = None


class ToolRegistry:
    """
    Centralized registry for managing agent tools.
    
    Provides functionality for:
    - Tool registration and categorization
    - Tool discovery for agents
    - Tool lifecycle management
    - Tool usage tracking and metrics
    """
    
    def __init__(self, logger: Optional[StructuredLogger] = None):
        """
        Initialize the tool registry.
        
        Args:
            logger: Optional logger instance for registry operations
        """
        self.logger = logger
        self._tools: Dict[str, ToolRegistration] = {}
        self._categories: Dict[ToolCategory, Set[str]] = {
            category: set() for category in ToolCategory
        }
        self._agent_tools: Dict[str, Set[str]] = {}
        self._tool_dependencies: Dict[str, Set[str]] = {}
        self._initialized = False
        
        if self.logger:
            self.logger.info("ToolRegistry initialized")
    
    async def initialize(self) -> None:
        """Initialize the tool registry."""
        if self._initialized:
            return
        
        if self.logger:
            self.logger.info("Initializing ToolRegistry")
        
        # Initialize any registered tools that need initialization
        for registration in self._tools.values():
            if registration.instance and hasattr(registration.instance, 'initialize'):
                try:
                    await registration.instance.initialize()
                    if self.logger:
                        self.logger.debug(f"Initialized tool: {registration.metadata.name}")
                except Exception as e:
                    if self.logger:
                        self.logger.error(
                            f"Failed to initialize tool: {registration.metadata.name}",
                            error=str(e)
                        )
        
        self._initialized = True
        if self.logger:
            self.logger.info(f"ToolRegistry initialized with {len(self._tools)} tools")
    
    async def shutdown(self) -> None:
        """Shutdown the tool registry and cleanup resources."""
        if not self._initialized:
            return
        
        if self.logger:
            self.logger.info("Shutting down ToolRegistry")
        
        # Shutdown all tool instances
        for registration in self._tools.values():
            if registration.instance and hasattr(registration.instance, 'shutdown'):
                try:
                    await registration.instance.shutdown()
                    if self.logger:
                        self.logger.debug(f"Shutdown tool: {registration.metadata.name}")
                except Exception as e:
                    if self.logger:
                        self.logger.error(
                            f"Failed to shutdown tool: {registration.metadata.name}",
                            error=str(e)
                        )
        
        self._initialized = False
        if self.logger:
            self.logger.info("ToolRegistry shutdown completed")
    
    def register_tool(
        self,
        tool_class: Type[BaseTool],
        name: str,
        description: str,
        category: ToolCategory,
        agent_types: Optional[List[str]] = None,
        dependencies: Optional[List[str]] = None,
        version: str = "1.0.0",
        tags: Optional[List[str]] = None,
        enabled: bool = True
    ) -> None:
        """
        Register a tool in the registry.
        
        Args:
            tool_class: The tool class to register
            name: Unique name for the tool
            description: Description of the tool's functionality
            category: Category for organizing the tool
            agent_types: List of agent types that can use this tool
            dependencies: List of tool names this tool depends on
            version: Tool version
            tags: Additional tags for categorization
            enabled: Whether the tool is enabled
            
        Raises:
            ValueError: If tool name already exists or is invalid
        """
        if not name or not name.strip():
            raise ValueError("Tool name cannot be empty")
        
        if name in self._tools:
            raise ValueError(f"Tool '{name}' is already registered")
        
        if not issubclass(tool_class, BaseTool):
            raise ValueError("tool_class must be a subclass of BaseTool")
        
        # Create metadata
        metadata = ToolMetadata(
            name=name,
            description=description,
            category=category,
            agent_types=set(agent_types or []),
            dependencies=dependencies or [],
            version=version,
            tags=set(tags or []),
            enabled=enabled
        )
        
        # Create registration
        registration = ToolRegistration(
            tool_class=tool_class,
            metadata=metadata
        )
        
        # Register the tool
        self._tools[name] = registration
        self._categories[category].add(name)
        
        # Update agent-tool mappings
        for agent_type in metadata.agent_types:
            if agent_type not in self._agent_tools:
                self._agent_tools[agent_type] = set()
            self._agent_tools[agent_type].add(name)
        
        # Update dependency mappings
        if metadata.dependencies:
            self._tool_dependencies[name] = set(metadata.dependencies)
        
        if self.logger:
            self.logger.info(
                f"Registered tool: {name}",
                category=category.value,
                agent_types=list(metadata.agent_types),
                dependencies=metadata.dependencies
            )
    
    def unregister_tool(self, name: str) -> None:
        """
        Unregister a tool from the registry.
        
        Args:
            name: Name of the tool to unregister
            
        Raises:
            ValueError: If tool is not found
        """
        if name not in self._tools:
            raise ValueError(f"Tool '{name}' is not registered")
        
        registration = self._tools[name]
        metadata = registration.metadata
        
        # Remove from categories
        self._categories[metadata.category].discard(name)
        
        # Remove from agent-tool mappings
        for agent_type in metadata.agent_types:
            if agent_type in self._agent_tools:
                self._agent_tools[agent_type].discard(name)
                if not self._agent_tools[agent_type]:
                    del self._agent_tools[agent_type]
        
        # Remove from dependencies
        if name in self._tool_dependencies:
            del self._tool_dependencies[name]
        
        # Remove tool
        del self._tools[name]
        
        if self.logger:
            self.logger.info(f"Unregistered tool: {name}")
    
    def get_tool_instance(self, name: str, **init_kwargs) -> BaseTool:
        """
        Get an instance of a registered tool.
        
        Args:
            name: Name of the tool
            **init_kwargs: Additional initialization arguments
            
        Returns:
            BaseTool: Instance of the requested tool
            
        Raises:
            ValueError: If tool is not found or disabled
        """
        if name not in self._tools:
            raise ValueError(f"Tool '{name}' is not registered")
        
        registration = self._tools[name]
        
        if not registration.metadata.enabled:
            raise ValueError(f"Tool '{name}' is disabled")
        
        # Create instance if not cached or if init_kwargs provided
        if registration.instance is None or init_kwargs:
            try:
                registration.instance = registration.tool_class(
                    name=registration.metadata.name,
                    description=registration.metadata.description,
                    **init_kwargs
                )
                if self.logger:
                    self.logger.debug(f"Created instance for tool: {name}")
            except Exception as e:
                if self.logger:
                    self.logger.error(f"Failed to create tool instance: {name}", error=str(e))
                raise
        
        # Update usage tracking
        registration.metadata.last_used = datetime.utcnow()
        registration.metadata.usage_count += 1
        
        return registration.instance
    
    def get_tools_for_agent(self, agent_type: str) -> List[BaseTool]:
        """
        Get all tools assigned to a specific agent type.
        
        Args:
            agent_type: The agent type identifier
            
        Returns:
            List[BaseTool]: List of tool instances for the agent
        """
        if agent_type not in self._agent_tools:
            return []
        
        tools = []
        for tool_name in self._agent_tools[agent_type]:
            try:
                tool = self.get_tool_instance(tool_name)
                tools.append(tool)
            except Exception as e:
                if self.logger:
                    self.logger.error(
                        f"Failed to get tool instance for agent {agent_type}",
                        tool_name=tool_name,
                        error=str(e)
                    )
        
        return tools
    
    def get_tools_by_category(self, category: ToolCategory) -> List[str]:
        """
        Get all tool names in a specific category.
        
        Args:
            category: The tool category
            
        Returns:
            List[str]: List of tool names in the category
        """
        return list(self._categories.get(category, set()))
    
    def get_tools_by_tags(self, tags: List[str]) -> List[str]:
        """
        Get all tool names that have any of the specified tags.
        
        Args:
            tags: List of tags to search for
            
        Returns:
            List[str]: List of tool names with matching tags
        """
        matching_tools = []
        tag_set = set(tags)
        
        for name, registration in self._tools.items():
            if registration.metadata.tags.intersection(tag_set):
                matching_tools.append(name)
        
        return matching_tools
    
    def search_tools(
        self,
        query: str,
        category: Optional[ToolCategory] = None,
        agent_type: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> List[str]:
        """
        Search for tools based on various criteria.
        
        Args:
            query: Search query to match against name and description
            category: Optional category filter
            agent_type: Optional agent type filter
            tags: Optional tags filter
            
        Returns:
            List[str]: List of matching tool names
        """
        matching_tools = []
        query_lower = query.lower() if query else ""
        
        for name, registration in self._tools.items():
            metadata = registration.metadata
            
            # Check if tool matches filters
            if category and metadata.category != category:
                continue
            
            if agent_type and agent_type not in metadata.agent_types:
                continue
            
            if tags and not metadata.tags.intersection(set(tags)):
                continue
            
            # Check if query matches name or description
            if query:
                if (query_lower not in name.lower() and 
                    query_lower not in metadata.description.lower()):
                    continue
            
            matching_tools.append(name)
        
        return matching_tools
    
    def get_tool_metadata(self, name: str) -> ToolMetadata:
        """
        Get metadata for a specific tool.
        
        Args:
            name: Name of the tool
            
        Returns:
            ToolMetadata: Metadata for the tool
            
        Raises:
            ValueError: If tool is not found
        """
        if name not in self._tools:
            raise ValueError(f"Tool '{name}' is not registered")
        
        return self._tools[name].metadata
    
    def get_tool_dependencies(self, name: str) -> List[str]:
        """
        Get dependencies for a specific tool.
        
        Args:
            name: Name of the tool
            
        Returns:
            List[str]: List of dependency tool names
        """
        return list(self._tool_dependencies.get(name, set()))
    
    def validate_dependencies(self, name: str) -> bool:
        """
        Validate that all dependencies for a tool are registered.
        
        Args:
            name: Name of the tool to validate
            
        Returns:
            bool: True if all dependencies are satisfied
        """
        if name not in self._tool_dependencies:
            return True
        
        dependencies = self._tool_dependencies[name]
        for dep in dependencies:
            if dep not in self._tools:
                return False
            if not self._tools[dep].metadata.enabled:
                return False
        
        return True
    
    def enable_tool(self, name: str) -> None:
        """
        Enable a tool.
        
        Args:
            name: Name of the tool to enable
            
        Raises:
            ValueError: If tool is not found
        """
        if name not in self._tools:
            raise ValueError(f"Tool '{name}' is not registered")
        
        self._tools[name].metadata.enabled = True
        
        if self.logger:
            self.logger.info(f"Enabled tool: {name}")
    
    def disable_tool(self, name: str) -> None:
        """
        Disable a tool.
        
        Args:
            name: Name of the tool to disable
            
        Raises:
            ValueError: If tool is not found
        """
        if name not in self._tools:
            raise ValueError(f"Tool '{name}' is not registered")
        
        self._tools[name].metadata.enabled = False
        
        if self.logger:
            self.logger.info(f"Disabled tool: {name}")
    
    def is_tool_enabled(self, name: str) -> bool:
        """
        Check if a tool is enabled.
        
        Args:
            name: Name of the tool
            
        Returns:
            bool: True if tool is enabled, False otherwise
        """
        if name not in self._tools:
            return False
        
        return self._tools[name].metadata.enabled
    
    def get_registry_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the tool registry.
        
        Returns:
            Dict containing registry statistics
        """
        total_tools = len(self._tools)
        enabled_tools = sum(1 for reg in self._tools.values() if reg.metadata.enabled)
        disabled_tools = total_tools - enabled_tools
        
        category_counts = {
            category.value: len(tools) 
            for category, tools in self._categories.items()
        }
        
        agent_tool_counts = {
            agent_type: len(tools)
            for agent_type, tools in self._agent_tools.items()
        }
        
        total_usage = sum(reg.metadata.usage_count for reg in self._tools.values())
        
        return {
            "total_tools": total_tools,
            "enabled_tools": enabled_tools,
            "disabled_tools": disabled_tools,
            "category_counts": category_counts,
            "agent_tool_counts": agent_tool_counts,
            "total_usage": total_usage,
            "initialized": self._initialized
        }
    
    def list_all_tools(self) -> List[Dict[str, Any]]:
        """
        Get a list of all registered tools with their metadata.
        
        Returns:
            List of tool information dictionaries
        """
        tools = []
        
        for name, registration in self._tools.items():
            metadata = registration.metadata
            tools.append({
                "name": name,
                "description": metadata.description,
                "category": metadata.category.value,
                "agent_types": list(metadata.agent_types),
                "dependencies": metadata.dependencies,
                "version": metadata.version,
                "enabled": metadata.enabled,
                "tags": list(metadata.tags),
                "usage_count": metadata.usage_count,
                "last_used": metadata.last_used.isoformat() if metadata.last_used else None,
                "created_at": metadata.created_at.isoformat()
            })
        
        return tools