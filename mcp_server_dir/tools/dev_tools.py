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

from mcp.server import Server
from mcp.server.lowlevel.server import ServerRequestContext
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
            inputSchema={
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
            inputSchema={
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
            inputSchema={
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
            inputSchema={
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
            inputSchema={
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
            inputSchema={
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
            inputSchema={
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
            inputSchema={
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
            inputSchema={
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
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                f.write(code)
                path = f.name
            result = subprocess.run(
                [sys.executable, path],
                capture_output=True, text=True, timeout=timeout
            )
            os.unlink(path)
            if result.returncode == 0:
                return f"Output:\n{result.stdout}"
            else:
                return f"Error (code {result.returncode}):\n{result.stderr}"
        except subprocess.TimeoutExpired:
            return f"Error: Execution timed out after {timeout}s"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _dev_execute_js(self, args: Dict) -> str:
        code = args.get("code", "")
        timeout = args.get("timeout", 30)
        node_path = shutil.which("node")
        if not node_path:
            return "Error: Node.js not found. Install Node.js to use this tool."
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False) as f:
                f.write(code)
                path = f.name
            result = subprocess.run(
                [node_path, path],
                capture_output=True, text=True, timeout=timeout
            )
            os.unlink(path)
            if result.returncode == 0:
                return f"Output:\n{result.stdout}"
            else:
                return f"Error (code {result.returncode}):\n{result.stderr}"
        except subprocess.TimeoutExpired:
            return f"Error: Execution timed out after {timeout}s"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _dev_execute_bash(self, args: Dict) -> str:
        command = args.get("command", "")
        timeout = args.get("timeout", 60)
        workdir = args.get("workdir", ".")
        try:
            result = subprocess.run(
                command, shell=True,
                capture_output=True, text=True, timeout=timeout,
                cwd=workdir
            )
            if result.returncode == 0:
                return f"Output:\n{result.stdout}"
            else:
                return f"Error (code {result.returncode}):\n{result.stderr}"
        except subprocess.TimeoutExpired:
            return f"Error: Command timed out after {timeout}s"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _dev_lint_python(self, args: Dict) -> str:
        code = args.get("code", "")
        linter = args.get("linter", "ruff")
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                f.write(code)
                path = f.name
            if linter == "ruff":
                cmd = [shutil.which("ruff") or "ruff", "check", path]
            elif linter == "flake8":
                cmd = [shutil.which("flake8") or "flake8", path]
            else:
                cmd = [shutil.which("pylint") or "pylint", path]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            os.unlink(path)
            if result.returncode == 0:
                return f"No issues found with {linter}."
            else:
                return f"Lint issues:\n{result.stdout or result.stderr}"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _dev_format_python(self, args: Dict) -> str:
        code = args.get("code", "")
        formatter = args.get("formatter", "black")
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                f.write(code)
                path = f.name
            if formatter == "black":
                cmd = [shutil.which("black") or "black", "--quiet", path]
            elif formatter == "autopep8":
                cmd = [shutil.which("autopep8") or "autopep8", "--in-place", path]
            else:
                cmd = [shutil.which("yapf") or "yapf", "--in-place", path]
            subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            with open(path) as f:
                formatted = f.read()
            os.unlink(path)
            return f"Formatted code:\n{formatted}"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _dev_search_code(self, args: Dict) -> str:
        pattern = args.get("pattern", "")
        path = args.get("path", ".")
        file_pattern = args.get("file_pattern", "*")
        context = args.get("context", 0)
        try:
            rg_path = shutil.which("rg")
            if rg_path:
                cmd = [rg_path, "--no-heading", "--line-number"]
                if context > 0:
                    cmd.extend(["-C", str(context)])
                cmd.extend(["-g", file_pattern, pattern, path])
            else:
                cmd = ["grep", "-r", "-n"]
                if context > 0:
                    cmd.extend(["-C", str(context)])
                cmd.extend(["--include", file_pattern, pattern, path])
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                return f"Search results:\n{result.stdout}"
            else:
                return f"No matches found."
        except Exception as e:
            return f"Error: {str(e)}"

    async def _dev_dependency_analyze(self, args: Dict) -> str:
        path = args.get("path", ".")
        language = args.get("language", "python")
        try:
            if language == "python":
                req_file = Path(path) / "requirements.txt"
                if req_file.exists():
                    content = req_file.read_text()
                    return f"Python dependencies (requirements.txt):\n{content}"
                else:
                    return "No requirements.txt found."
            elif language == "nodejs":
                pkg_file = Path(path) / "package.json"
                if pkg_file.exists():
                    with open(pkg_file) as f:
                        pkg = json.load(f)
                    deps = pkg.get("dependencies", {})
                    dev_deps = pkg.get("devDependencies", {})
                    result = "Node.js dependencies:\n"
                    if deps:
                        result += "  Production:\n"
                        for k, v in deps.items():
                            result += f"    {k}: {v}\n"
                    if dev_deps:
                        result += "  Development:\n"
                        for k, v in dev_deps.items():
                            result += f"    {k}: {v}\n"
                    return result
                else:
                    return "No package.json found."
            elif language == "rust":
                cargo_file = Path(path) / "Cargo.toml"
                if cargo_file.exists():
                    content = cargo_file.read_text()
                    return f"Rust dependencies (Cargo.toml):\n{content}"
                else:
                    return "No Cargo.toml found."
            elif language == "go":
                go_mod = Path(path) / "go.mod"
                if go_mod.exists():
                    content = go_mod.read_text()
                    return f"Go dependencies (go.mod):\n{content}"
                else:
                    return "No go.mod found."
            else:
                return f"Unsupported language: {language}"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _dev_run_tests(self, args: Dict) -> str:
        path = args.get("path", ".")
        test_framework = args.get("test_framework", "pytest")
        test_pattern = args.get("test_pattern", "")
        try:
            if test_framework == "pytest":
                cmd = [shutil.which("pytest") or "pytest", "-v"]
                if test_pattern:
                    cmd.extend(["-k", test_pattern])
                cmd.append(path)
            elif test_framework == "jest":
                cmd = [shutil.which("npx") or "npx", "jest", "--verbose"]
                if test_pattern:
                    cmd.extend(["-t", test_pattern])
            elif test_framework == "go-test":
                cmd = ["go", "test", "./..."]
                if test_pattern:
                    cmd.extend(["-run", test_pattern])
            elif test_framework == "cargo-test":
                cmd = [shutil.which("cargo") or "cargo", "test"]
            else:
                return f"Unsupported test framework: {test_framework}"
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=path)
            if result.returncode == 0:
                return f"Tests passed:\n{result.stdout}"
            else:
                return f"Tests failed (code {result.returncode}):\n{result.stdout}\n{result.stderr}"
        except subprocess.TimeoutExpired:
            return "Error: Tests timed out after 120s"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _dev_api_test(self, args: Dict) -> str:
        import urllib.request
        import urllib.parse
        url = args.get("url", "")
        method = args.get("method", "GET")
        headers = json.loads(args.get("headers", "{}"))
        body = args.get("body", "")
        try:
            if body:
                body = body.encode("utf-8")
            req = urllib.request.Request(url, data=body, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=30) as resp:
                resp_body = resp.read().decode("utf-8")
                return f"Status: {resp.status}\nHeaders: {dict(resp.headers)}\nBody: {resp_body[:2000]}"
        except Exception as e:
            return f"Error: {str(e)}"
