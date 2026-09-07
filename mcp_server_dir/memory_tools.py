"""
Memory Tools Mixin for mem20 MCP Server

Core memory management tools.
"""

from mcp.server import Server
from mcp.server.lowlevel.server import ServerRequestContext
import mcp_types as mt

import os
import sys
import json
import re
import subprocess
import tempfile
import base64
import asyncio
import hashlib
import shutil
import glob
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
try:
    from memory import remember, recall, status as mem_status, rebuild_index, ledger_view
    MEMORY_SYSTEM_AVAILABLE = True
except ImportError:
    MEMORY_SYSTEM_AVAILABLE = False


class MemoryToolsMixin:
    def register_memory_tools(self):
        self.tools["memory_store"] = mt.Tool(
            name="memory_store",
            title="Store Memory",
            description="Store a fact in mem20's persistent memory system",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "The fact/content to store"},
                    "category": {"type": "string", "enum": ["user_pref", "project", "tool", "general"], "default": "general"},
                    "tags": {"type": "string", "description": "Comma-separated tags", "default": ""},
                },
                "required": ["content"],
            },
        )
        self.tools["memory_recall"] = mt.Tool(
            name="memory_recall",
            title="Recall Memory",
            description="Search and recall facts from mem20's memory system",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "category": {"type": "string", "enum": ["user_pref", "project", "tool", "general"], "default": ""},
                    "limit": {"type": "integer", "default": 10, "minimum": 1, "maximum": 50},
                },
                "required": ["query"],
            },
        )
        self.tools["memory_probe"] = mt.Tool(
            name="memory_probe",
            title="Probe Entity",
            description="Get all facts about a specific entity",
            inputSchema={
                "type": "object",
                "properties": {
                    "entity": {"type": "string", "description": "Entity name to probe"},
                    "min_trust": {"type": "number", "default": 0.3},
                },
                "required": ["entity"],
            },
        )
        self.tools["memory_reason"] = mt.Tool(
            name="memory_reason",
            title="Reason Across Entities",
            description="Compositional reasoning across multiple entities",
            inputSchema={
                "type": "object",
                "properties": {
                    "entities": {"type": "array", "items": {"type": "string"}, "description": "List of entity names"},
                    "min_trust": {"type": "number", "default": 0.3},
                },
                "required": ["entities"],
            },
        )
        self.tools["memory_status"] = mt.Tool(
            name="memory_status",
            title="Memory Status",
            description="Get mem20 memory system status and stats",
            inputSchema={"type": "object", "properties": {}},
        )
        self.tools["memory_contradict"] = mt.Tool(
            name="memory_contradict",
            title="Find Contradictions",
            description="Find facts that make conflicting claims about a topic",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Topic to check for contradictions"},
                    "min_trust": {"type": "number", "default": 0.3},
                },
                "required": ["query"],
            },
        )
        self.tools["memory_related"] = mt.Tool(
            name="memory_related",
            title="Find Related",
            description="Find facts related to an entity or topic",
            inputSchema={
                "type": "object",
                "properties": {
                    "entity": {"type": "string", "description": "Entity name"},
                    "min_trust": {"type": "number", "default": 0.3},
                },
                "required": ["entity"],
            },
        )
        self.tools["memory_feedback"] = mt.Tool(
            name="memory_feedback",
            title="Memory Feedback",
            description="Provide feedback on a memory fact",
            inputSchema={
                "type": "object",
                "properties": {
                    "fact_id": {"type": "integer", "description": "Fact ID"},
                    "rating": {"type": "string", "enum": ["helpful", "unhelpful"]},
                },
                "required": ["fact_id", "rating"],
            },
        )

    async def _memory_store(self, args: Dict) -> str:
        content = args.get("content", "")
        category = args.get("category", "general")
        tags = args.get("tags", "")
        if not MEMORY_SYSTEM_AVAILABLE:
            return "Error: Memory system not available"
        try:
            result = remember(content=content, category=category, tags=tags)
            return f"Stored: {result}"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _memory_recall(self, args: Dict) -> str:
        query = args.get("query", "")
        category = args.get("category", "")
        limit = args.get("limit", 10)
        if not MEMORY_SYSTEM_AVAILABLE:
            return "Error: Memory system not available"
        try:
            results = recall(query=query, category=category or None, limit=limit)
            return f"Recall results ({len(results)}):\n" + "\n".join(str(r) for r in results)
        except Exception as e:
            return f"Error: {str(e)}"

    async def _memory_probe(self, args: Dict) -> str:
        entity = args.get("entity", "")
        min_trust = args.get("min_trust", 0.3)
        if not MEMORY_SYSTEM_AVAILABLE:
            return "Error: Memory system not available"
        try:
            results = recall(query=entity, min_trust=min_trust)
            return f"Probe results for '{entity}' ({len(results)}):\n" + "\n".join(str(r) for r in results)
        except Exception as e:
            return f"Error: {str(e)}"

    async def _memory_reason(self, args: Dict) -> str:
        entities = args.get("entities", [])
        min_trust = args.get("min_trust", 0.3)
        if not MEMORY_SYSTEM_AVAILABLE:
            return "Error: Memory system not available"
        try:
            results = recall(query=" ".join(entities), min_trust=min_trust)
            return f"Reasoning across {len(entities)} entities ({len(results)} facts):\n" + "\n".join(str(r) for r in results)
        except Exception as e:
            return f"Error: {str(e)}"

    async def _memory_status(self) -> str:
        if not MEMORY_SYSTEM_AVAILABLE:
            return "Error: Memory system not available"
        try:
            return mem_status()
        except Exception as e:
            return f"Error: {str(e)}"

    async def _memory_contradict(self, args: Dict) -> str:
        return "Memory contradiction tool not yet implemented."

    async def _memory_related(self, args: Dict) -> str:
        return "Memory related tool not yet implemented."

    async def _memory_feedback(self, args: Dict) -> str:
        return "Memory feedback tool not yet implemented."
