"""
Database Tools Mixin for mem20 MCP Server

Provides database tools with multi-backend support:
- SQLite (built-in, always available)
- PostgreSQL (via psycopg2/asyncpg)
- MySQL (via pymysql)
- Redis (via redis-py)
- MongoDB (via pymongo)
- Query builder
- Schema inspection
- Migration runner
"""
import mcp_types as mt


import os
import sys
import json
import asyncio
import sqlite3
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional



class DatabaseToolsMixin:
    """Database tools for mem20."""

    def register_database_tools(self):
        """Register all database tools."""
        self.tools["db_query"] = mt.Tool(
            name="db_query",
            title="Execute Query",
            description="Execute a SQL query on a database",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "SQL query to execute"},
                    "database": {"type": "string", "description": "Database connection string or path", "default": ""},
                    "db_type": {"type": "string", "enum": ["sqlite", "postgresql", "mysql", "redis", "mongodb"], "default": "sqlite"},
                    "params": {"type": "string", "description": "JSON array of query parameters", "default": "[]"},
                },
                "required": ["query"],
            },
        )
        self.tools["db_schema"] = mt.Tool(
            name="db_schema",
            title="Inspect Schema",
            description="Inspect database schema (tables, columns, indexes)",
            input_schema={
                "type": "object",
                "properties": {
                    "database": {"type": "string", "description": "Database connection string or path", "default": ""},
                    "db_type": {"type": "string", "enum": ["sqlite", "postgresql", "mysql", "mongodb"], "default": "sqlite"},
                    "table": {"type": "string", "description": "Specific table to inspect", "default": ""},
                },
                "required": [],
            },
        )
        self.tools["db_insert"] = mt.Tool(
            name="db_insert",
            title="Insert Data",
            description="Insert data into a database table",
            input_schema={
                "type": "object",
                "properties": {
                    "table": {"type": "string", "description": "Table name"},
                    "data": {"type": "string", "description": "JSON object of data to insert"},
                    "database": {"type": "string", "description": "Database connection string or path", "default": ""},
                    "db_type": {"type": "string", "enum": ["sqlite", "postgresql", "mysql", "mongodb"], "default": "sqlite"},
                },
                "required": ["table", "data"],
            },
        )
        self.tools["db_update"] = mt.Tool(
            name="db_update",
            title="Update Data",
            description="Update data in a database table",
            input_schema={
                "type": "object",
                "properties": {
                    "table": {"type": "string", "description": "Table name"},
                    "data": {"type": "string", "description": "JSON object of data to update"},
                    "where": {"type": "string", "description": "WHERE clause"},
                    "database": {"type": "string", "description": "Database connection string or path", "default": ""},
                    "db_type": {"type": "string", "enum": ["sqlite", "postgresql", "mysql", "mongodb"], "default": "sqlite"},
                },
                "required": ["table", "data", "where"],
            },
        )
        self.tools["db_delete"] = mt.Tool(
            name="db_delete",
            title="Delete Data",
            description="Delete data from a database table",
            input_schema={
                "type": "object",
                "properties": {
                    "table": {"type": "string", "description": "Table name"},
                    "where": {"type": "string", "description": "WHERE clause"},
                    "database": {"type": "string", "description": "Database connection string or path", "default": ""},
                    "db_type": {"type": "string", "enum": ["sqlite", "postgresql", "mysql", "mongodb"], "default": "sqlite"},
                },
                "required": ["table", "where"],
            },
        )
        self.tools["db_create_table"] = mt.Tool(
            name="db_create_table",
            title="Create Table",
            description="Create a new table in the database",
            input_schema={
                "type": "object",
                "properties": {
                    "table": {"type": "string", "description": "Table name"},
                    "columns": {"type": "string", "description": "JSON object of column definitions"},
                    "database": {"type": "string", "description": "Database connection string or path", "default": ""},
                    "db_type": {"type": "string", "enum": ["sqlite", "postgresql", "mysql"], "default": "sqlite"},
                },
                "required": ["table", "columns"],
            },
        )
        self.tools["db_list_tables"] = mt.Tool(
            name="db_list_tables",
            title="List Tables",
            description="List all tables in the database",
            input_schema={
                "type": "object",
                "properties": {
                    "database": {"type": "string", "description": "Database connection string or path", "default": ""},
                    "db_type": {"type": "string", "enum": ["sqlite", "postgresql", "mysql", "mongodb"], "default": "sqlite"},
                },
                "required": [],
            },
        )
        self.tools["db_backup"] = mt.Tool(
            name="db_backup",
            title="Backup Database",
            description="Create a backup of the database",
            input_schema={
                "type": "object",
                "properties": {
                    "database": {"type": "string", "description": "Database connection string or path", "default": ""},
                    "db_type": {"type": "string", "enum": ["sqlite", "postgresql", "mysql"], "default": "sqlite"},
                    "output_path": {"type": "string", "description": "Output path for backup", "default": ""},
                },
                "required": [],
            },
        )
        self.tools["db_redis_command"] = mt.Tool(
            name="db_redis_command",
            title="Redis Command",
            description="Execute a Redis command",
            input_schema={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Redis command (e.g., GET, SET, HGETALL)"},
                    "args": {"type": "string", "description": "JSON array of command arguments", "default": "[]"},
                    "redis_url": {"type": "string", "description": "Redis connection URL", "default": "redis://localhost:6379"},
                },
                "required": ["command"],
            },
        )
        self.tools["db_mongo_find"] = mt.Tool(
            name="db_mongo_find",
            title="MongoDB Find",
            description="Query MongoDB collection",
            input_schema={
                "type": "object",
                "properties": {
                    "collection": {"type": "string", "description": "Collection name"},
                    "filter": {"type": "string", "description": "JSON filter object", "default": "{}"},
                    "projection": {"type": "string", "description": "JSON projection object", "default": "{}"},
                    "limit": {"type": "integer", "description": "Limit results", "default": 10},
                    "mongo_url": {"type": "string", "description": "MongoDB connection URL", "default": "mongodb://localhost:27017"},
                    "database_name": {"type": "string", "description": "Database name", "default": "mem20"},
                },
                "required": ["collection"],
            },
        )

    def _get_sqlite_path(self, database: str = "") -> str:
        """Get SQLite database path."""
        if database:
            return database
        store_path = Path(os.environ.get("MEM20_STORE_PATH", Path.home() / ".mem20" / "store"))
        db_path = store_path / "mem20.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return str(db_path)

    def _get_sqlite_conn(self, database: str = ""):
        """Get SQLite connection."""
        path = self._get_sqlite_path(database)
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        return conn

    async def _db_query(self, args: Dict) -> str:
        query = args.get("query", "")
        db_type = args.get("db_type", "sqlite")
        database = args.get("database", "")
        params = json.loads(args.get("params", "[]"))
