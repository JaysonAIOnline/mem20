"""
Development Tools Mixin for mem20 MCP Server

Provides software development tools:
- Code execution (Python, JavaScript, Bash)
- Code linting/formatting
- Package management
- Git operations
- Docker management
- Environment management
- Testing utilities
- API testing
- Code search/grep
- Dependency analysis
"""
import mcp_types as mt



import os
import sys
import json
import subprocess
import tempfile
import asyncio
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional


class DevToolsMixin:
    """Development tools for mem20."""

    def register_dev_tools(self):
        """Register all development tools."""
        self.tools["dev_execute_python"] = mt.Tool(
            name="dev_execute_python",
            title="Execute Python Code",
            description="Execute Python code in a sandboxed environment",
            input_schema={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python code to execute"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 30},
                },
                "required": ["code"],
            },
        )
        self.tools["dev_execute_js"] = mt.Tool(
            name="dev_execute_js",
            title="Execute JavaScript",
            description="Execute JavaScript code using Node.js",
            input_schema={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "JavaScript code to execute"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 30},
                },
                "required": ["code"],
            },
        )
        self.tools["dev_execute_bash"] = mt.Tool(
            name="dev_execute_bash",
            title="Execute Bash Command",
            description="Execute a bash command",
            input_schema={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Bash command to execute"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 60},
                    "workdir": {"type": "string", "description": "Working directory", "default": "."},
                },
                "required": ["command"],
            },
        )
        self.tools["dev_lint_python"] = mt.Tool(
            name="dev_lint_python",
            title="Lint Python Code",
            description="Lint Python code using pylint or flake8",
            input_schema={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python code to lint"},
                    "linter": {"type": "string", "enum": ["pylint", "flake8", "ruff"], "default": "ruff"},
                },
                "required": ["code"],
            },
        )
        self.tools["dev_format_python"] = mt.Tool(
            name="dev_format_python",
            title="Format Python Code",
            description="Format Python code using black or autopep8",
            input_schema={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python code to format"},
                    "formatter": {"type": "string", "enum": ["black", "autopep8", "yapf"], "default": "black"},
                },
                "required": ["code"],
            },
        )
        self.tools["dev_search_code"] = mt.Tool(
            name="dev_search_code",
            title="Search Code",
            description="Search code patterns in files using grep/ripgrep",
            input_schema={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Search pattern (regex)"},
                    "path": {"type": "string", "description": "Path to search in", "default": "."},
                    "file_pattern": {"type": "string", "description": "File glob pattern", "default": "*"},
                    "context": {"type": "integer", "description": "Context lines", "default": 0},
                },
                "required": ["pattern"],
            },
        )
        self.tools["dev_dependency_analyze"] = mt.Tool(
            name="dev_dependency_analyze",
            title="Analyze Dependencies",
            description="Analyze project dependencies (Python, Node.js, etc.)",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Project path", "default": "."},
                    "language": {"type": "string", "enum": ["python", "nodejs", "rust", "go"], "default": "python"},
                },
                "required": [],
            },
        )
        self.tools["dev_run_tests"] = mt.Tool(
            name="dev_run_tests",
            title="Run Tests",
            description="Run project tests (pytest, jest, etc.)",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Project path", "default": "."},
                    "test_framework": {"type": "string", "enum": ["pytest", "jest", "go-test", "cargo-test"], "default": "pytest"},
                    "test_pattern": {"type": "string", "description": "Test pattern to match", "default": ""},
                },
                "required": [],
            },
        )
        self.tools["dev_api_test"] = mt.Tool(
            name="dev_api_test",
            title="Test API Endpoint",
            description="Test an HTTP API endpoint",
            input_schema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "API URL to test"},
                    "method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"], "default": "GET"},
                    "headers": {"type": "string", "description": "JSON string of headers", "default": "{}"},
                    "body": {"type": "string", "description": "Request body", "default": ""},
                },
                "required": ["url"],
            },
        )

    async def _dev_execute_python(self, args: Dict) -> str:
        code = args.get("code", "")
        timeout = args.get("timeout", 30)
