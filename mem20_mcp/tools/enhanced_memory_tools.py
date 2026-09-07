"""
Enhanced Memory Tools Mixin for mem20 MCP Server

Provides new memory tools:
- Memory graph traversal
- Memory consolidation (auto-merge similar memories)
- Memory decay (time-based relevance reduction)
- Memory reinforcement (boost important memories)
- Memory clustering (group related memories)
- Memory timeline (chronological view)
- Memory export/import
- Memory versioning
- Memory sharing (export to share)
- Memory encryption
- Memory compression
- Memory deduplication
- Memory context window
- Memory triggers (event-based recall)
- Memory mood/emotion tagging
"""
import mcp_types as mt


import os
import sys
import json
import time
import asyncio
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta



class EnhancedMemoryToolsMixin:
    """Enhanced memory tools for mem20."""

    def register_enhanced_memory_tools(self):
        """Register all enhanced memory tools."""
        self.tools["memory_graph_traverse"] = mt.Tool(
            name="memory_graph_traverse",
            title="Graph Traversal",
            description="Traverse memory graph from a starting entity",
            input_schema={
                "type": "object",
                "properties": {
                    "start_entity": {"type": "string"},
                    "depth": {"type": "integer", "default": 2, "minimum": 1, "maximum": 5},
                    "direction": {"type": "string", "enum": ["forward", "backward", "both"], "default": "both"},
                },
                "required": ["start_entity"],
            },
        )
        self.tools["memory_consolidate"] = mt.Tool(
            name="memory_consolidate",
            title="Consolidate Memories",
            description="Auto-merge similar memories to reduce redundancy",
            input_schema={
                "type": "object",
                "properties": {
                    "threshold": {"type": "number", "default": 0.85, "minimum": 0.5, "maximum": 1.0},
                    "dry_run": {"type": "boolean", "default": True},
                    "category": {"type": "string", "default": ""},
                },
                "required": [],
            },
        )
        self.tools["memory_decay"] = mt.Tool(
            name="memory_decay",
            title="Memory Decay",
            description="Apply time-based decay to memory relevance",
            input_schema={
                "type": "object",
                "properties": {
                    "half_life_days": {"type": "integer", "default": 30},
                    "dry_run": {"type": "boolean", "default": True},
                },
                "required": [],
            },
        )
        self.tools["memory_reinforce"] = mt.Tool(
            name="memory_reinforce",
            title="Reinforce Memory",
            description="Boost importance of a memory",
            input_schema={
                "type": "object",
                "properties": {
                    "memory_id": {"type": "string"},
                    "boost_factor": {"type": "number", "default": 1.5, "minimum": 1.0, "maximum": 10.0},
                    "reason": {"type": "string", "default": ""},
                },
                "required": ["memory_id"],
            },
        )
        self.tools["memory_cluster"] = mt.Tool(
            name="memory_cluster",
            title="Cluster Memories",
            description="Group related memories into clusters",
            input_schema={
                "type": "object",
                "properties": {
                    "algorithm": {"type": "string", "enum": ["kmeans", "hierarchical", "dbscan", "topic"], "default": "topic"},
                    "num_clusters": {"type": "integer", "default": 5},
                    "min_cluster_size": {"type": "integer", "default": 2},
                },
                "required": [],
            },
        )
        self.tools["memory_timeline"] = mt.Tool(
            name="memory_timeline",
            title="Memory Timeline",
            description="View memories in chronological order",
            input_schema={
                "type": "object",
                "properties": {
                    "from_date": {"type": "string", "default": ""},
                    "to_date": {"type": "string", "default": ""},
                    "category": {"type": "string", "default": ""},
                    "limit": {"type": "integer", "default": 50},
                },
                "required": [],
            },
        )
        self.tools["memory_export"] = mt.Tool(
            name="memory_export",
            title="Export Memories",
            description="Export memories to various formats",
            input_schema={
                "type": "object",
                "properties": {
                    "format": {"type": "string", "enum": ["json", "csv", "markdown", "yaml"], "default": "json"},
                    "output_path": {"type": "string", "default": ""},
                    "category": {"type": "string", "default": ""},
                    "include_simulated": {"type": "boolean", "default": False},
                },
                "required": [],
            },
        )
        self.tools["memory_import"] = mt.Tool(
            name="memory_import",
            title="Import Memories",
            description="Import memories from file",
            input_schema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "format": {"type": "string", "enum": ["json", "csv", "markdown", "yaml"], "default": "json"},
                    "merge_strategy": {"type": "string", "enum": ["skip", "overwrite", "merge"], "default": "merge"},
                },
                "required": ["file_path"],
            },
        )
        self.tools["memory_deduplicate"] = mt.Tool(
            name="memory_deduplicate",
            title="Deduplicate Memories",
            description="Find and remove duplicate memories",
            input_schema={
                "type": "object",
                "properties": {
                    "similarity_threshold": {"type": "number", "default": 0.9, "minimum": 0.5, "maximum": 1.0},
                    "dry_run": {"type": "boolean", "default": True},
                },
                "required": [],
            },
        )
        self.tools["memory_triggers"] = mt.Tool(
            name="memory_triggers",
            title="Memory Triggers",
            description="Set up event-based memory triggers",
            input_schema={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["create", "list", "delete", "fire"], "default": "list"},
                    "trigger_name": {"type": "string", "default": ""},
                    "event": {"type": "string", "default": ""},
                    "memory_query": {"type": "string", "default": ""},
                },
                "required": [],
            },
        )
        self.tools["memory_mood_tag"] = mt.Tool(
            name="memory_mood_tag",
            title="Mood Tag",
            description="Tag memories with mood/emotion",
            input_schema={
                "type": "object",
                "properties": {
                    "memory_id": {"type": "string"},
                    "mood": {"type": "string", "enum": ["happy", "sad", "angry", "anxious", "excited", "calm", "neutral"], "default": "neutral"},
                    "intensity": {"type": "integer", "default": 5, "minimum": 1, "maximum": 10},
                },
                "required": ["memory_id"],
            },
        )
        self.tools["memory_context_window"] = mt.Tool(
            name="memory_context_window",
            title="Context Window",
            description="Get memories relevant to current context",
            input_schema={
                "type": "object",
                "properties": {
                    "context": {"type": "string"},
                    "window_size": {"type": "integer", "default": 10},
                    "recency_weight": {"type": "number", "default": 0.3},
                    "relevance_weight": {"type": "number", "default": 0.7},
                },
                "required": ["context"],
            },
        )
        self.tools["memory_stats"] = mt.Tool(
            name="memory_stats",
            title="Memory Statistics",
            description="Get detailed memory system statistics",
            input_schema={
                "type": "object",
                "properties": {
                    "include_categories": {"type": "boolean", "default": True},
                    "include_temporal": {"type": "boolean", "default": True},
                    "include_health": {"type": "boolean", "default": True},
                },
                "required": [],
            },
        )

    async def _memory_graph_traverse(self, args: Dict) -> str:
        start_entity = args.get("start_entity", "")
        depth = args.get("depth", 2)
        direction = args.get("direction", "both")
