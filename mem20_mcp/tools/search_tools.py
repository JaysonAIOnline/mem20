"""
Search Tools Mixin for mem20 MCP Server

Provides search tools with multi-backend support:
- Web search (DuckDuckGo, Bing, Google)
- Local search (ripgrep, find)
- Knowledge base search
- Image search
- News search
- Academic search (arXiv, Semantic Scholar)
- Code search (GitHub)
"""
import mcp_types as mt


import os
import sys
import json
import asyncio
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional



class SearchToolsMixin:
    """Search tools for mem20."""

    def register_search_tools(self):
        """Register all search tools."""
        self.tools["search_web"] = mt.Tool(
            name="search_web",
            title="Web Search",
            description="Search the web using DuckDuckGo, Bing, or Google",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "engine": {"type": "string", "enum": ["duckduckgo", "bing", "google", "brave"], "default": "duckduckgo"},
                    "limit": {"type": "integer", "description": "Max results", "default": 10},
                    "safe_search": {"type": "boolean", "description": "Enable safe search", "default": True},
                },
                "required": ["query"],
            },
        )
        self.tools["search_local"] = mt.Tool(
            name="search_local",
            title="Local Search",
            description="Search files and directories locally",
            input_schema={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Search pattern"},
                    "path": {"type": "string", "description": "Path to search", "default": "."},
                    "file_type": {"type": "string", "description": "File type filter", "default": ""},
                    "max_results": {"type": "integer", "description": "Max results", "default": 50},
                },
                "required": ["pattern"],
            },
        )
        self.tools["search_knowledge_base"] = mt.Tool(
            name="search_knowledge_base",
            title="Knowledge Base Search",
            description="Search mem20's knowledge base",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "category": {"type": "string", "description": "Filter by category", "default": ""},
                    "limit": {"type": "integer", "description": "Max results", "default": 10},
                },
                "required": ["query"],
            },
        )
        self.tools["search_images"] = mt.Tool(
            name="search_images",
            title="Image Search",
            description="Search for images on the web",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "engine": {"type": "string", "enum": ["duckduckgo", "bing", "google"], "default": "duckduckgo"},
                    "limit": {"type": "integer", "description": "Max results", "default": 10},
                    "size": {"type": "string", "enum": ["small", "medium", "large"], "default": "medium"},
                },
                "required": ["query"],
            },
        )
        self.tools["search_news"] = mt.Tool(
            name="search_news",
            title="News Search",
            description="Search for news articles",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "engine": {"type": "string", "enum": ["duckduckgo", "bing", "google"], "default": "duckduckgo"},
                    "limit": {"type": "integer", "description": "Max results", "default": 10},
                    "time_range": {"type": "string", "enum": ["day", "week", "month", "year"], "default": "week"},
                },
                "required": ["query"],
            },
        )
        self.tools["search_academic"] = mt.Tool(
            name="search_academic",
            title="Academic Search",
            description="Search academic papers (arXiv, Semantic Scholar)",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "source": {"type": "string", "enum": ["arxiv", "semantic_scholar", "both"], "default": "both"},
                    "limit": {"type": "integer", "description": "Max results", "default": 10},
                    "year_from": {"type": "integer", "description": "From year", "default": 0},
                    "year_to": {"type": "integer", "description": "To year", "default": 0},
                },
                "required": ["query"],
            },
        )
        self.tools["search_code"] = mt.Tool(
            name="search_code",
            title="Code Search",
            description="Search code on GitHub",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "language": {"type": "string", "description": "Programming language", "default": ""},
                    "limit": {"type": "integer", "description": "Max results", "default": 10},
                },
                "required": ["query"],
            },
        )

    async def _search_web(self, args: Dict) -> str:
        query = args.get("query", "")
        engine = args.get("engine", "duckduckgo")
        limit = args.get("limit", 10)
