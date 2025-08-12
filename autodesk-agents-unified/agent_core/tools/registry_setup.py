"""
Tool registry setup for Model Properties tools.
"""

from ..tool_registry import ToolRegistry, ToolCategory
from .model_properties import (
    CreateIndexTool,
    ListIndexPropertiesTool,
    QueryIndexTool,
    ExecuteJQQueryTool
)
from .model_derivatives import (
    SetupDatabaseTool,
    SQLQueryTool,
    GetTableInfoTool,
    GetSampleDataTool
)


def register_model_properties_tools(registry: ToolRegistry) -> None:
    """
    Register all Model Properties tools with the tool registry.
    
    Args:
        registry: The ToolRegistry instance to register tools with
    """
    # Register CreateIndexTool
    registry.register_tool(
        tool_class=CreateIndexTool,
        name="create_index",
        description="Builds a Model Properties index for a given design ID, including all available properties and property values for individual design elements. Returns the ID of the created index.",
        category=ToolCategory.DATA_ACCESS,
        agent_types=["model_properties"],
        dependencies=[],
        version="1.0.0",
        tags=["autodesk", "construction", "index", "properties"],
        enabled=True
    )
    
    # Register ListIndexPropertiesTool
    registry.register_tool(
        tool_class=ListIndexPropertiesTool,
        name="list_index_properties",
        description="Lists available properties for a Model Properties index of given ID. Returns a JSON with property categories, names, and keys.",
        category=ToolCategory.DATA_ACCESS,
        agent_types=["model_properties"],
        dependencies=["create_index"],
        version="1.0.0",
        tags=["autodesk", "construction", "properties", "metadata"],
        enabled=True
    )
    
    # Register QueryIndexTool
    registry.register_tool(
        tool_class=QueryIndexTool,
        name="query_index",
        description="Queries a Model Properties index of the given ID with a Model Property Service Query Language query. Returns a JSON list with properties of matching design elements.",
        category=ToolCategory.QUERY_EXECUTION,
        agent_types=["model_properties"],
        dependencies=["create_index"],
        version="1.0.0",
        tags=["autodesk", "construction", "query", "search"],
        enabled=True
    )
    
    # Register ExecuteJQQueryTool
    registry.register_tool(
        tool_class=ExecuteJQQueryTool,
        name="execute_jq_query",
        description="Processes the given JSON input with the given jq query, and returns the result as a JSON.",
        category=ToolCategory.TRANSFORMATION,
        agent_types=["model_properties", "aec_data_model", "model_derivatives"],  # Can be used by multiple agents
        dependencies=[],
        version="1.0.0",
        tags=["json", "transformation", "query", "jq"],
        enabled=True
    )

def register_model_derivatives_tools(registry: ToolRegistry) -> None:
    """
    Register all Model Derivatives tools with the tool registry.
    
    Args:
        registry: The ToolRegistry instance to register tools with
    """
    # Register SetupDatabaseTool
    registry.register_tool(
        tool_class=SetupDatabaseTool,
        name="setup_database",
        description="Sets up a SQLite database with model properties for a given URN. Downloads model metadata, properties, and creates a structured database for querying design element properties.",
        category=ToolCategory.DATA_ACCESS,
        agent_types=["model_derivatives"],
        dependencies=[],
        version="1.0.0",
        tags=["autodesk", "sqlite", "database", "setup", "properties"],
        enabled=True
    )
    
    # Register SQLQueryTool
    registry.register_tool(
        tool_class=SQLQueryTool,
        name="sql_query",
        description="Executes a SQL query on the SQLite database containing model properties. Returns the query results as a list of dictionaries.",
        category=ToolCategory.QUERY_EXECUTION,
        agent_types=["model_derivatives"],
        dependencies=["setup_database"],
        version="1.0.0",
        tags=["sql", "query", "database", "search"],
        enabled=True
    )
    
    # Register GetTableInfoTool
    registry.register_tool(
        tool_class=GetTableInfoTool,
        name="get_table_info",
        description="Gets information about the database schema, including table names, column names, and data types. Useful for understanding the database structure.",
        category=ToolCategory.METADATA,
        agent_types=["model_derivatives"],
        dependencies=["setup_database"],
        version="1.0.0",
        tags=["database", "schema", "metadata", "info"],
        enabled=True
    )
    
    # Register GetSampleDataTool
    registry.register_tool(
        tool_class=GetSampleDataTool,
        name="get_sample_data",
        description="Gets sample data from a database table to help understand the data structure and content. Returns a limited number of rows from the specified table.",
        category=ToolCategory.DATA_ACCESS,
        agent_types=["model_derivatives"],
        dependencies=["setup_database"],
        version="1.0.0",
        tags=["database", "sample", "data", "preview"],
        enabled=True
    )