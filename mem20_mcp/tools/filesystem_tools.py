"""
Filesystem Tools Mixin for mem20 MCP Server

Provides advanced filesystem tools:
- File read/write with encoding detection
- Directory operations
- File search with glob/regex
- File metadata
- Symlink operations
- File comparison (diff)
- Archive operations (zip, tar)
- File watching
- Permission management
- Disk usage analysis
"""
import mcp_types as mt


import os
import sys
import json
import shutil
import hashlib
import tempfile
import asyncio
import zipfile
import tarfile
from pathlib import Path
from typing import Any, Dict, List, Optional



class FilesystemToolsMixin:
    """Advanced filesystem tools for mem20."""

    def register_filesystem_tools(self):
        """Register all filesystem tools."""
        self.tools["fs_read_advanced"] = mt.Tool(
            name="fs_read_advanced",
            title="Read File (Advanced)",
            description="Read file with encoding detection and line numbers",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"},
                    "offset": {"type": "integer", "default": 1},
                    "limit": {"type": "integer", "default": 2000},
                    "encoding": {"type": "string", "description": "Force encoding", "default": ""},
                },
                "required": ["path"],
            },
        )
        self.tools["fs_write_advanced"] = mt.Tool(
            name="fs_write_advanced",
            title="Write File (Advanced)",
            description="Write file with encoding and atomic write support",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"},
                    "content": {"type": "string", "description": "Content to write"},
                    "encoding": {"type": "string", "default": "utf-8"},
                    "append": {"type": "boolean", "default": False},
                    "atomic": {"type": "boolean", "default": True},
                },
                "required": ["path", "content"],
            },
        )
        self.tools["fs_search"] = mt.Tool(
            name="fs_search",
            title="Search Files",
            description="Search files by name pattern or content",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "default": "."},
                    "name_pattern": {"type": "string", "default": ""},
                    "content_pattern": {"type": "string", "default": ""},
                    "file_type": {"type": "string", "default": ""},
                    "max_results": {"type": "integer", "default": 50},
                },
                "required": ["path"],
            },
        )
        self.tools["fs_metadata"] = mt.Tool(
            name="fs_metadata",
            title="File Metadata",
            description="Get file metadata (size, modified, permissions, hash)",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "compute_hash": {"type": "boolean", "default": False},
                },
                "required": ["path"],
            },
        )
        self.tools["fs_diff"] = mt.Tool(
            name="fs_diff",
            title="File Diff",
            description="Compare two files and show differences",
            input_schema={
                "type": "object",
                "properties": {
                    "file1": {"type": "string"},
                    "file2": {"type": "string"},
                    "context_lines": {"type": "integer", "default": 3},
                },
                "required": ["file1", "file2"],
            },
        )
        self.tools["fs_archive_create"] = mt.Tool(
            name="fs_archive_create",
            title="Create Archive",
            description="Create a zip or tar archive",
            input_schema={
                "type": "object",
                "properties": {
                    "output_path": {"type": "string"},
                    "files": {"type": "string", "description": "JSON array of file paths"},
                    "format": {"type": "string", "enum": ["zip", "tar", "tar.gz"], "default": "zip"},
                },
                "required": ["output_path", "files"],
            },
        )
        self.tools["fs_archive_extract"] = mt.Tool(
            name="fs_archive_extract",
            title="Extract Archive",
            description="Extract a zip or tar archive",
            input_schema={
                "type": "object",
                "properties": {
                    "archive_path": {"type": "string"},
                    "output_dir": {"type": "string"},
                    "format": {"type": "string", "enum": ["zip", "tar", "tar.gz"], "default": "zip"},
                },
                "required": ["archive_path", "output_dir"],
            },
        )
        self.tools["fs_disk_usage"] = mt.Tool(
            name="fs_disk_usage",
            title="Disk Usage",
            description="Analyze disk usage for a directory",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "default": "."},
                    "max_depth": {"type": "integer", "default": 2},
                    "limit": {"type": "integer", "default": 20},
                },
                "required": [],
            },
        )
        self.tools["fs_watch"] = mt.Tool(
            name="fs_watch",
            title="Watch Directory",
            description="Watch a directory for changes",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "duration_seconds": {"type": "integer", "default": 10},
                    "recursive": {"type": "boolean", "default": True},
                },
                "required": ["path"],
            },
        )
        self.tools["fs_permissions"] = mt.Tool(
            name="fs_permissions",
            title="Manage Permissions",
            description="Get or set file permissions",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "mode": {"type": "string", "description": "Octal mode (e.g., 755)", "default": ""},
                    "owner": {"type": "string", "default": ""},
                    "group": {"type": "string", "default": ""},
                },
                "required": ["path"],
            },
        )

    async def _fs_read_advanced(self, args: Dict) -> str:
        path = args.get("path", "")
        offset = args.get("offset", 1)
        limit = args.get("limit", 2000)
        encoding = args.get("encoding", "")
