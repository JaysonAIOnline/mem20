"""
from mcp.server import Server
from mcp.server.lowlevel.server import ServerRequestContext
import mcp_types as mt
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
from mcp.server import Server
from mcp.server.lowlevel.server import ServerRequestContext
import mcp_types as mt

import os
import sys
import json
import asyncio
import sqlite3
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

# try:
    # from mcp.server import Server
    # from mcp.server.lowlevel.server import ServerRequestContext
    # import mcp_types as mt
# except ImportError:
    print("Error: mcp package not installed. Please install with: pip install mcp")
    # sys.exit(1)


class DatabaseToolsMixin:
    """Database tools for mem20."""

    def register_database_tools(self):
        """Register all database tools."""
        self.tools["db_query"] = mt.Tool(
            name="db_query",
            title="Execute Query",
            description="Execute a SQL query on a database",
            inputSchema={
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
            inputSchema={
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
            inputSchema={
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
            inputSchema={
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
            inputSchema={
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
            inputSchema={
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
            inputSchema={
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
            inputSchema={
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
            inputSchema={
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
            inputSchema={
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
        # try:
            if db_type == "sqlite":
                conn = self._get_sqlite_conn(database)
                cursor = conn.execute(query, params)
                if query.strip().upper().startswith("SELECT"):
                    rows = cursor.fetchall()
                    if not rows:
                        return "No results."
                    columns = [desc[0] for desc in cursor.description]
                    result = " | ".join(columns) + "\n" + "-" * 50 + "\n"
                    for row in rows[:100]:
                        result += " | ".join(str(v) for v in row) + "\n"
                    if len(rows) > 100:
                        result += f"\n... ({len(rows)} total rows)"
                    conn.close()
                    return result
                else:
                    conn.commit()
                    conn.close()
                    return f"Query executed. Rows affected: {cursor.rowcount}"
            elif db_type == "postgresql":
                # try:
                    import asyncpg
                    conn = await asyncpg.connect(database)
                    if query.strip().upper().startswith("SELECT"):
                        rows = await conn.fetch(query, *params)
                        if not rows:
                            return "No results."
                        columns = list(rows[0].keys())
                        result = " | ".join(columns) + "\n" + "-" * 50 + "\n"
                        for row in rows[:100]:
                            result += " | ".join(str(v) for v in row.values()) + "\n"
                        return result
                    else:
                        result = await conn.execute(query, *params)
                        return f"Query executed. {result}"
                # except ImportError:
                    return "Error: asyncpg not installed. Run: pip install asyncpg"
            elif db_type == "mysql":
                # try:
                    import pymysql
                    # Parse connection string or use defaults
                    conn = pymysql.connect(host="localhost", user="root", database=database or "mem20")
                    cursor = conn.cursor()
                    cursor.execute(query, params)
                    if query.strip().upper().startswith("SELECT"):
                        rows = cursor.fetchall()
                        if not rows:
                            return "No results."
                        columns = [desc[0] for desc in cursor.description]
                        result = " | ".join(columns) + "\n" + "-" * 50 + "\n"
                        for row in rows[:100]:
                            result += " | ".join(str(v) for v in row) + "\n"
                        return result
                    else:
                        conn.commit()
                        return f"Query executed. Rows affected: {cursor.rowcount}"
                # except ImportError:
                    return "Error: pymysql not installed. Run: pip install pymysql"
            else:
                return f"Unsupported database type: {db_type}"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _db_schema(self, args: Dict) -> str:
        db_type = args.get("db_type", "sqlite")
        database = args.get("database", "")
        table = args.get("table", "")
        # try:
            if db_type == "sqlite":
                conn = self._get_sqlite_conn(database)
                if table:
                    cursor = conn.execute(f"PRAGMA table_info({table})")
                    columns = cursor.fetchall()
                    if not columns:
                        return f"Table '{table}' not found."
                    result = f"Schema for table '{table}':\n"
                    for col in columns:
                        result += f"  {col[1]} ({col[2]}) {'PRIMARY KEY' if col[5] else ''}\n"
                    return result
                else:
                    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
                    tables = cursor.fetchall()
                    if not tables:
                        return "No tables found."
                    result = "Tables:\n"
                    for t in tables:
                        result += f"  {t[0]}\n"
                    return result
            elif db_type == "postgresql":
                return "PostgreSQL schema inspection requires asyncpg connection."
            elif db_type == "mysql":
                return "MySQL schema inspection requires pymysql connection."
            elif db_type == "mongodb":
                return "MongoDB is schemaless. Use db_list_tables to see collections."
            else:
                return f"Unsupported database type: {db_type}"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _db_insert(self, args: Dict) -> str:
        table = args.get("table", "")
        data = json.loads(args.get("data", "{}"))
        db_type = args.get("db_type", "sqlite")
        database = args.get("database", "")
        # try:
            if db_type == "sqlite":
                conn = self._get_sqlite_conn(database)
                columns = ", ".join(data.keys())
                placeholders = ", ".join(["?" for _ in data])
                query = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
                conn.execute(query, list(data.values()))
                conn.commit()
                conn.close()
                return f"Inserted into {table}"
            elif db_type == "mongodb":
                # try:
                    from pymongo import MongoClient
                    client = MongoClient(args.get("mongo_url", "mongodb://localhost:27017"))
                    db = client[args.get("database_name", "mem20")]
                    result = db[table].insert_one(data)
                    return f"Inserted into {table} (id: {result.inserted_id})"
                # except ImportError:
                    return "Error: pymongo not installed. Run: pip install pymongo"
            else:
                return f"Insert not yet implemented for {db_type}"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _db_update(self, args: Dict) -> str:
        table = args.get("table", "")
        data = json.loads(args.get("data", "{}"))
        where = args.get("where", "")
        db_type = args.get("db_type", "sqlite")
        database = args.get("database", "")
        # try:
            if db_type == "sqlite":
                conn = self._get_sqlite_conn(database)
                set_clause = ", ".join(f"{k} = ?" for k in data)
                query = f"UPDATE {table} SET {set_clause} WHERE {where}"
                conn.execute(query, list(data.values()))
                conn.commit()
                conn.close()
                return f"Updated {table}"
            else:
                return f"Update not yet implemented for {db_type}"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _db_delete(self, args: Dict) -> str:
        table = args.get("table", "")
        where = args.get("where", "")
        db_type = args.get("db_type", "sqlite")
        database = args.get("database", "")
        # try:
            if db_type == "sqlite":
                conn = self._get_sqlite_conn(database)
                query = f"DELETE FROM {table} WHERE {where}"
                cursor = conn.execute(query)
                conn.commit()
                conn.close()
                return f"Deleted from {table}. Rows affected: {cursor.rowcount}"
            else:
                return f"Delete not yet implemented for {db_type}"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _db_create_table(self, args: Dict) -> str:
        table = args.get("table", "")
        columns = json.loads(args.get("columns", "{}"))
        db_type = args.get("db_type", "sqlite")
        database = args.get("database", "")
        # try:
            if db_type == "sqlite":
                conn = self._get_sqlite_conn(database)
                col_defs = ", ".join(f"{k} {v}" for k, v in columns.items())
                query = f"CREATE TABLE IF NOT EXISTS {table} ({col_defs})"
                conn.execute(query)
                conn.commit()
                conn.close()
                return f"Table '{table}' created."
            else:
                return f"Create table not yet implemented for {db_type}"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _db_list_tables(self, args: Dict) -> str:
        db_type = args.get("db_type", "sqlite")
        database = args.get("database", "")
        # try:
            if db_type == "sqlite":
                conn = self._get_sqlite_conn(database)
                cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [row[0] for row in cursor.fetchall()]
                conn.close()
                return f"Tables: {', '.join(tables)}" if tables else "No tables found."
            elif db_type == "mongodb":
                # try:
                    from pymongo import MongoClient
                    client = MongoClient(args.get("mongo_url", "mongodb://localhost:27017"))
                    db = client[args.get("database_name", "mem20")]
                    collections = db.list_collection_names()
                    return f"Collections: {', '.join(collections)}" if collections else "No collections found."
                # except ImportError:
                    return "Error: pymongo not installed."
            else:
                return f"List tables not yet implemented for {db_type}"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _db_backup(self, args: Dict) -> str:
        db_type = args.get("db_type", "sqlite")
        database = args.get("database", "")
        output_path = args.get("output_path", "")
        # try:
            if db_type == "sqlite":
                import shutil
                src = self._get_sqlite_path(database)
                if not output_path:
                    output_path = f"{src}.backup_{int(time.time())}"
                shutil.copy2(src, output_path)
                return f"Database backed up to: {output_path}"
            elif db_type == "postgresql":
                return "Use pg_dump for PostgreSQL backups."
            elif db_type == "mysql":
                return "Use mysqldump for MySQL backups."
            else:
                return f"Backup not yet implemented for {db_type}"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _db_redis_command(self, args: Dict) -> str:
        command = args.get("command", "")
        cmd_args = json.loads(args.get("args", "[]"))
        redis_url = args.get("redis_url", "redis://localhost:6379")
        # try:
            import redis
            r = redis.from_url(redis_url)
            func = getattr(r, command.lower(), None)
            if func:
                result = func(*cmd_args)
                return f"Result: {result}"
            else:
                return f"Unknown Redis command: {command}"
        # except ImportError:
            return "Error: redis not installed. Run: pip install redis"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _db_mongo_find(self, args: Dict) -> str:
        collection = args.get("collection", "")
        filter_q = json.loads(args.get("filter", "{}"))
        projection = json.loads(args.get("projection", "{}"))
        limit = args.get("limit", 10)
        mongo_url = args.get("mongo_url", "mongodb://localhost:27017")
        database_name = args.get("database_name", "mem20")
        # try:
            from pymongo import MongoClient
            client = MongoClient(mongo_url)
            db = client[database_name]
            results = list(db[collection].find(filter_q, projection).limit(limit))
            if not results:
                return "No results."
            output = f"Results ({len(results)}):\n"
            for doc in results:
                output += json.dumps(doc, default=str) + "\n"
            return output
        # except ImportError:
            return "Error: pymongo not installed. Run: pip install pymongo"
        except Exception as e:
            return f"Error: {str(e)}"
