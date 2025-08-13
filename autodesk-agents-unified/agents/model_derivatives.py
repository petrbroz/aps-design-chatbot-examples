"""
Model Derivatives Agent

Real implementation that makes actual calls to Autodesk Model Derivative API
and manages SQLite databases for derivative data analysis.
"""

import asyncio
import json
import sqlite3
import time
import os
from typing import Dict, Any, List, Optional
from pathlib import Path
import aiohttp
import aiofiles

from agentcore import (
    BaseAgent, AgentRequest, AgentResponse, AgentCapabilities,
    ExecutionContext, ToolResult, ErrorCodes
)
from agentcore.tools import BaseTool, ToolCategory
from agentcore.models import AgentType


class SQLDatabaseTool(BaseTool):
    """Tool for SQLite database operations on model derivative data."""
    
    def __init__(self, agent_core, database_path: str):
        super().__init__(
            name="sql_database_toolkit",
            description="Execute SQL queries on model derivative databases",
            category=ToolCategory.DATABASE
        )
        self.agent_core = agent_core
        self.database_path = Path(database_path)
        self.cache_manager = agent_core.cache_manager
        
        # Ensure database directory exists
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
    
    async def execute(self, query: str, project_id: str, version_id: str, **kwargs) -> ToolResult:
        """
        Execute SQL query on derivative database.
        
        Args:
            query: SQL query to execute
            project_id: Autodesk project ID
            version_id: Model version ID
            
        Returns:
            ToolResult with query results
        """
        try:
            # Get or create database for this project/version
            db_path = await self._get_database_path(project_id, version_id)
            
            # Ensure database exists and is populated
            await self._ensure_database_ready(db_path, project_id, version_id)
            
            # Execute query
            results = await self._execute_sql_query(db_path, query)
            
            if self.logger:
                self.logger.info("SQL query executed successfully", extra={
                    "project_id": project_id,
                    "version_id": version_id,
                    "query_length": len(query),
                    "results_count": len(results) if isinstance(results, list) else 1
                })
            
            return ToolResult(
                output={
                    "query": query,
                    "results": results,
                    "database_path": str(db_path),
                    "project_id": project_id,
                    "version_id": version_id
                },
                success=True,
                tool_name=self.name
            )
            
        except Exception as e:
            if self.logger:
                self.logger.error("SQL query execution failed", extra={
                    "project_id": project_id,
                    "version_id": version_id,
                    "query": query,
                    "error": str(e),
                    "error_type": type(e).__name__
                })
            
            return ToolResult.error(
                error_message=f"SQL query failed: {str(e)}",
                tool_name=self.name,
                error_type=type(e).__name__
            )
    
    async def _get_database_path(self, project_id: str, version_id: str) -> Path:
        """Get database path for project/version."""
        db_name = f"derivatives_{project_id}_{version_id}.db"
        return self.database_path.parent / db_name
    
    async def _ensure_database_ready(self, db_path: Path, project_id: str, version_id: str) -> None:
        """Ensure database exists and is populated with derivative data."""
        
        # Check if database exists and has data
        if db_path.exists():
            # Check if database has tables
            conn = sqlite3.connect(db_path)
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cursor.fetchall()
            conn.close()
            
            if tables:
                if self.logger:
                    self.logger.info("Using existing derivative database", extra={
                        "database_path": str(db_path),
                        "table_count": len(tables)
                    })
                return
        
        # Create and populate database
        await self._create_derivative_database(db_path, project_id, version_id)
    
    async def _create_derivative_database(self, db_path: Path, project_id: str, version_id: str) -> None:
        """Create and populate derivative database from Autodesk API."""
        
        if self.logger:
            self.logger.info("Creating derivative database", extra={
                "project_id": project_id,
                "version_id": version_id,
                "database_path": str(db_path)
            })
        
        # Get authentication token
        auth_context = await self.agent_core.auth_manager.get_client_token("data:read")
        
        # Get model URN
        urn = await self._get_model_urn(auth_context, project_id, version_id)
        
        # Fetch derivative data
        derivative_data = await self._fetch_derivative_data(auth_context, urn)
        
        # Create SQLite database
        await self._populate_database(db_path, derivative_data, project_id, version_id)
        
        if self.logger:
            self.logger.info("Derivative database created successfully", extra={
                "database_path": str(db_path),
                "project_id": project_id,
                "version_id": version_id
            })
    
    async def _get_model_urn(self, auth_context, project_id: str, version_id: str) -> str:
        """Get model URN from project and version IDs."""
        
        version_url = f"https://developer.api.autodesk.com/data/v1/projects/{project_id}/versions/{version_id}"
        headers = auth_context.to_headers()
        
        async with aiohttp.ClientSession() as session:
            async with session.get(version_url, headers=headers) as response:
                if response.status == 200:
                    version_data = await response.json()
                    storage_location = version_data["data"]["relationships"]["storage"]["data"]["id"]
                    
                    # Convert to base64 URN format
                    import base64
                    urn = base64.b64encode(storage_location.encode()).decode()
                    return f"urn:adsk.objects:os.object:{urn}"
                else:
                    error_text = await response.text()
                    raise Exception(f"Failed to get model URN: {response.status} - {error_text}")
    
    async def _fetch_derivative_data(self, auth_context, urn: str) -> Dict[str, Any]:
        """Fetch derivative data from Autodesk Model Derivative API."""
        
        # Get derivative manifest
        manifest_url = f"https://developer.api.autodesk.com/modelderivative/v2/designdata/{urn}/manifest"
        headers = auth_context.to_headers()
        
        async with aiohttp.ClientSession() as session:
            async with session.get(manifest_url, headers=headers) as response:
                if response.status == 200:
                    manifest_data = await response.json()
                    
                    # Extract derivative information
                    derivatives = []
                    if "derivatives" in manifest_data:
                        for derivative in manifest_data["derivatives"]:
                            derivatives.append({
                                "name": derivative.get("name", ""),
                                "hasThumbnail": derivative.get("hasThumbnail", False),
                                "status": derivative.get("status", ""),
                                "progress": derivative.get("progress", ""),
                                "outputType": derivative.get("outputType", ""),
                                "children": derivative.get("children", [])
                            })
                    
                    return {
                        "urn": urn,
                        "type": manifest_data.get("type", ""),
                        "region": manifest_data.get("region", ""),
                        "version": manifest_data.get("version", ""),
                        "derivatives": derivatives
                    }
                else:
                    error_text = await response.text()
                    raise Exception(f"Failed to fetch derivative data: {response.status} - {error_text}")
    
    async def _populate_database(self, db_path: Path, derivative_data: Dict[str, Any], 
                                project_id: str, version_id: str) -> None:
        """Populate SQLite database with derivative data."""
        
        conn = sqlite3.connect(db_path)
        
        try:
            # Create tables
            conn.execute("""
                CREATE TABLE IF NOT EXISTS models (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL,
                    version_id TEXT NOT NULL,
                    urn TEXT NOT NULL,
                    type TEXT,
                    region TEXT,
                    version TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS derivatives (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    model_id INTEGER,
                    name TEXT,
                    has_thumbnail BOOLEAN,
                    status TEXT,
                    progress TEXT,
                    output_type TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (model_id) REFERENCES models (id)
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS derivative_children (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    derivative_id INTEGER,
                    name TEXT,
                    type TEXT,
                    role TEXT,
                    mime TEXT,
                    urn TEXT,
                    FOREIGN KEY (derivative_id) REFERENCES derivatives (id)
                )
            """)
            
            # Insert model data
            cursor = conn.execute("""
                INSERT INTO models (project_id, version_id, urn, type, region, version)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                project_id,
                version_id,
                derivative_data["urn"],
                derivative_data.get("type", ""),
                derivative_data.get("region", ""),
                derivative_data.get("version", "")
            ))
            
            model_id = cursor.lastrowid
            
            # Insert derivatives
            for derivative in derivative_data.get("derivatives", []):
                cursor = conn.execute("""
                    INSERT INTO derivatives (model_id, name, has_thumbnail, status, progress, output_type)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    model_id,
                    derivative.get("name", ""),
                    derivative.get("hasThumbnail", False),
                    derivative.get("status", ""),
                    derivative.get("progress", ""),
                    derivative.get("outputType", "")
                ))
                
                derivative_id = cursor.lastrowid
                
                # Insert derivative children
                for child in derivative.get("children", []):
                    conn.execute("""
                        INSERT INTO derivative_children (derivative_id, name, type, role, mime, urn)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        derivative_id,
                        child.get("name", ""),
                        child.get("type", ""),
                        child.get("role", ""),
                        child.get("mime", ""),
                        child.get("urn", "")
                    ))
            
            conn.commit()
            
        finally:
            conn.close()
    
    async def _execute_sql_query(self, db_path: Path, query: str) -> List[Dict[str, Any]]:
        """Execute SQL query and return results."""
        
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row  # Enable column access by name
        
        try:
            cursor = conn.execute(query)
            rows = cursor.fetchall()
            
            # Convert to list of dictionaries
            results = []
            for row in rows:
                results.append(dict(row))
            
            return results
            
        finally:
            conn.close()


class ModelDerivativesAgent(BaseAgent):
    """
    Model Derivatives Agent that makes real calls to Autodesk Model Derivative API.
    
    Provides functionality to create SQLite databases from derivative data,
    execute SQL queries, and analyze model derivative information.
    """
    
    def __init__(self, agent_core, agent_config: Dict[str, Any]):
        """Initialize Model Derivatives agent."""
        super().__init__(agent_core, agent_config)
        
        # Get database configuration
        specific_config = agent_config.get("specific_config", {})
        self.database_path = specific_config.get("database_path", "./cache/derivatives.db")
        self.max_db_size_mb = specific_config.get("max_db_size_mb", 500)
        self.query_timeout = specific_config.get("query_timeout_seconds", 30)
    
    async def initialize(self) -> None:
        """Initialize the agent and register tools."""
        if self._initialized:
            return
        
        # Create and register tools
        tools = [
            SQLDatabaseTool(self.agent_core, self.database_path)
        ]
        
        for tool in tools:
            await tool.initialize()
            self.register_tool(tool.name, tool)
        
        self.logger.info("Model Derivatives agent initialized", extra={
            "tools_count": len(tools),
            "tools": [tool.name for tool in tools],
            "database_path": self.database_path
        })
        
        await super().initialize()
    
    async def process_prompt(self, request: AgentRequest, context: ExecutionContext) -> AgentResponse:
        """Process user prompt for model derivatives operations."""
        
        prompt = request.prompt.lower()
        project_id = context.project_id or request.context.get("project_id")
        version_id = context.version_id or request.context.get("version_id")
        
        if not project_id or not version_id:
            return AgentResponse.error(
                error_message="Project ID and Version ID are required for model derivatives operations",
                error_code=ErrorCodes.MISSING_PARAMETER,
                agent_type=self.get_agent_type()
            )
        
        try:
            responses = []
            
            # Determine operation based on prompt
            if "sql" in prompt or "query" in prompt or "select" in prompt:
                # Extract SQL query from prompt
                sql_query = self._extract_sql_query(prompt)
                
                tool_result = await self.execute_tool(
                    "sql_database_toolkit",
                    query=sql_query,
                    project_id=project_id,
                    version_id=version_id
                )
                
                if tool_result.success:
                    output = tool_result.output
                    results = output.get("results", [])
                    
                    responses.extend([
                        f"📊 SQL Query Results:",
                        f"🔍 Query: {sql_query}",
                        f"📋 Found {len(results)} results"
                    ])
                    
                    if results:
                        responses.append("\n📄 Results:")
                        
                        # Show first few results
                        for i, result in enumerate(results[:10]):
                            if isinstance(result, dict):
                                result_str = ", ".join([f"{k}: {v}" for k, v in result.items()])
                                responses.append(f"  {i+1}. {result_str}")
                            else:
                                responses.append(f"  {i+1}. {result}")
                        
                        if len(results) > 10:
                            responses.append(f"  ... and {len(results) - 10} more results")
                    else:
                        responses.append("  No results found")
                else:
                    responses.append(f"❌ SQL query failed: {tool_result.error_message}")
            
            elif "database" in prompt or "create" in prompt:
                # Create/setup database
                tool_result = await self.execute_tool(
                    "sql_database_toolkit",
                    query="SELECT name FROM sqlite_master WHERE type='table'",
                    project_id=project_id,
                    version_id=version_id
                )
                
                if tool_result.success:
                    output = tool_result.output
                    results = output.get("results", [])
                    
                    responses.extend([
                        f"🗄️ Model Derivatives Database Ready",
                        f"📋 Project: {project_id}",
                        f"📋 Version: {version_id}",
                        f"📊 Database Tables: {len(results)}"
                    ])
                    
                    if results:
                        responses.append("\n📂 Available Tables:")
                        for result in results:
                            table_name = result.get("name", "unknown")
                            responses.append(f"  • {table_name}")
                    
                    responses.extend([
                        "",
                        "💡 Example Queries:",
                        "• 'SELECT * FROM models' - Show model information",
                        "• 'SELECT * FROM derivatives' - List all derivatives",
                        "• 'SELECT * FROM derivative_children' - Show derivative files"
                    ])
                else:
                    responses.append(f"❌ Database setup failed: {tool_result.error_message}")
            
            elif "tables" in prompt or "schema" in prompt:
                # Show database schema
                tool_result = await self.execute_tool(
                    "sql_database_toolkit",
                    query="SELECT name, sql FROM sqlite_master WHERE type='table'",
                    project_id=project_id,
                    version_id=version_id
                )
                
                if tool_result.success:
                    output = tool_result.output
                    results = output.get("results", [])
                    
                    responses.extend([
                        f"📋 Database Schema",
                        f"🗄️ Tables: {len(results)}"
                    ])
                    
                    for result in results:
                        table_name = result.get("name", "unknown")
                        responses.append(f"\n📂 Table: {table_name}")
                        
                        # Show table structure
                        if table_name == "models":
                            responses.append("  Columns: id, project_id, version_id, urn, type, region, version")
                        elif table_name == "derivatives":
                            responses.append("  Columns: id, model_id, name, has_thumbnail, status, progress, output_type")
                        elif table_name == "derivative_children":
                            responses.append("  Columns: id, derivative_id, name, type, role, mime, urn")
                else:
                    responses.append(f"❌ Schema query failed: {tool_result.error_message}")
            
            else:
                # General help
                responses.extend([
                    "🗄️ Model Derivatives Agent - Real SQLite Database Integration",
                    "",
                    "I can help you work with model derivative data using SQL queries:",
                    "",
                    "📋 Available Operations:",
                    "• 'Create database' - Set up derivative database from Autodesk API",
                    "• 'Show tables' - Display database schema and structure",
                    "• 'SELECT * FROM models' - Query model information",
                    "• 'SELECT * FROM derivatives' - List derivative files",
                    "• Custom SQL queries for data analysis",
                    "",
                    "🔧 Real API Integration:",
                    "• Autodesk Model Derivative API for data extraction",
                    "• SQLite database for fast local queries",
                    "• Automatic database creation and population",
                    "",
                    f"📋 Current Context: Project {project_id}, Version {version_id}",
                    "",
                    "💡 Try: 'Create database' to get started!"
                ])
            
            return AgentResponse(
                responses=responses,
                success=True,
                metadata={
                    "project_id": project_id,
                    "version_id": version_id,
                    "operation_detected": self._detect_operation(prompt),
                    "tools_available": list(self._tools.keys()),
                    "database_path": self.database_path
                }
            )
            
        except Exception as e:
            self.logger.error("Error processing model derivatives prompt", extra={
                "prompt": request.prompt,
                "project_id": project_id,
                "version_id": version_id,
                "error": str(e),
                "error_type": type(e).__name__
            })
            
            return AgentResponse.error(
                error_message=f"Failed to process request: {str(e)}",
                error_code=ErrorCodes.UNKNOWN_ERROR,
                agent_type=self.get_agent_type()
            )
    
    def _extract_sql_query(self, prompt: str) -> str:
        """Extract SQL query from user prompt."""
        # Look for SQL keywords and extract query
        sql_keywords = ["select", "insert", "update", "delete", "create", "drop", "alter"]
        
        prompt_lower = prompt.lower()
        
        # Find SQL query in prompt
        for keyword in sql_keywords:
            if keyword in prompt_lower:
                # Extract from keyword to end or until common stop words
                start_idx = prompt_lower.find(keyword)
                query_part = prompt[start_idx:]
                
                # Clean up the query
                query_part = query_part.strip()
                if not query_part.endswith(";"):
                    query_part += ";"
                
                return query_part
        
        # Default queries based on prompt content
        if "model" in prompt_lower:
            return "SELECT * FROM models LIMIT 10;"
        elif "derivative" in prompt_lower:
            return "SELECT * FROM derivatives LIMIT 10;"
        else:
            return "SELECT name FROM sqlite_master WHERE type='table';"
    
    def _detect_operation(self, prompt: str) -> str:
        """Detect the intended operation from prompt."""
        prompt_lower = prompt.lower()
        
        if any(word in prompt_lower for word in ["sql", "query", "select"]):
            return "sql_query"
        elif "database" in prompt_lower or "create" in prompt_lower:
            return "create_database"
        elif "tables" in prompt_lower or "schema" in prompt_lower:
            return "show_schema"
        else:
            return "help"
    
    def get_capabilities(self) -> AgentCapabilities:
        """Get agent capabilities."""
        return AgentCapabilities(
            agent_type=self.get_agent_type(),
            name="Model Derivatives Agent",
            description="Analyzes model derivative data using SQLite databases and real Autodesk API integration",
            version="1.0.0",
            tools=["sql_database_toolkit"],
            supported_formats=["json", "text", "sql"],
            max_prompt_length=2000,
            requires_authentication=True,
            requires_project_context=True,
            requires_internet=True,
            typical_response_time_ms=5000
        )
    
    def get_agent_type(self) -> str:
        """Return agent type."""
        return AgentType.MODEL_DERIVATIVES.value