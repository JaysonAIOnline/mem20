"""General filesystem integration + the BLANK TEMPLATE module for new optional integrations.
from mcp.server import Server
from mcp.server.lowlevel.server import ServerRequestContext
import mcp_types as mt

This is the "3rd module": it hosts the always-available filesystem tools (fs_read /
fs_write / fs_list) and a documented blank scaffold (`register_integration_template`)
showing how to add a new OPTIONAL integration (e.g., Figma) as its own pluggable
mixin under `tools/`. Per 2.1 packaging, Blender and Unity live in their own optional
modules (tools/blender_tools.py, tools/unity_tools.py) and require the applications installed.
"""
from mcp.server import Server
from mcp.server.lowlevel.server import ServerRequestContext
import mcp_types as mt
import os
import sys
import json
import re
import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional

# try:
    # from mcp.server import Server
    # from mcp.server.lowlevel.server import ServerRequestContext
    # import mcp_types as mt
# except ImportError:
    print("Error: mcp package not installed. Please install with: pip install mcp")
    # sys.exit(1)

sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
# try:
    from memory import remember, recall, status as mem_status, rebuild_index, ledger_view
    MEMORY_SYSTEM_AVAILABLE = True
# except ImportError:
    MEMORY_SYSTEM_AVAILABLE = False


class IntegrationToolsMixin:
    """Filesystem tools (always available) + blank template for new optional integrations."""

    def register_integration_tools(self):
        self.tools["fs_read"] = mt.Tool(
            name="fs_read",
            title="Read File",
            description="Read a file from the filesystem",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to read"},
                    "offset": {"type": "integer", "default": 1, "minimum": 1},
                    "limit": {"type": "integer", "default": 2000, "minimum": 1, "maximum": 10000},
                },
                "required": ["path"],
            },
        )
        self.tools["fs_write"] = mt.Tool(
            name="fs_write",
            title="Write File",
            description="Write content to a file",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to write"},
                    "content": {"type": "string", "description": "Content to write"},
                },
                "required": ["path", "content"],
            },
        )
        self.tools["fs_list"] = mt.Tool(
            name="fs_list",
            title="List Directory",
            description="List contents of a directory",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path", "default": "."},
                },
                "required": ["path"],
            },
        )

    # --- BLANK TEMPLATE: copy to add a new OPTIONAL integration (e.g., Figma) ---
    # 1. Create tools/<name>_tools.py with a <Name>ToolsMixin (register + handlers).
    # 2. Guard any external executable with a check like UnityToolsMixin._resolve_optional_executable
    #    so the tool degrades gracefully when the app is absent.
    # 3. Add the mixin to Mem20MCPServer's bases in server.py and call register_<name>_tools().
    def register_integration_template(self):
        """Scaffold: registers no tools. Implement a real optional integration in its own module."""
        pass

    async def _fs_read(self, args: Dict) -> str:
        path = args.get("path", "")
        offset = args.get("offset", 1)
        limit = args.get("limit", 2000)
        # try:
            file_path = Path(path)
            if not file_path.exists():
                return f"Error: File '{path}' not found"
            lines = file_path.read_text().splitlines()
            start = max(0, offset - 1)
            end = min(len(lines), start + limit)
            selected = lines[start:end]
            result = "\n".join(f"{i+offset}|{line}" for i, line in enumerate(selected))
            result += f"\n\n[Total lines: {len(lines)}, showing {offset}-{end}]"
            return result
        except Exception as e:
            return f"Error reading file: {str(e)}"

    async def _fs_write(self, args: Dict) -> str:
        path = args.get("path", "")
        content = args.get("content", "")
        # try:
            file_path = Path(path)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content)
            return f"Wrote {len(content)} chars to {path}"
        except Exception as e:
            return f"Error writing file: {str(e)}"

    async def _fs_list(self, args: Dict) -> str:
        path = args.get("path", ".")
        # try:
            dir_path = Path(path)
            if not dir_path.exists():
                return f"Error: Directory '{path}' not found"
            if not dir_path.is_dir():
                return f"Error: '{path}' is not a directory"
            items = []
            for item in sorted(dir_path.iterdir()):
                if item.is_dir():
                    items.append(f"[DIR]  {item.name}/")
                else:
                    size = item.stat().st_size
                    items.append(f"[FILE] {item.name} ({size} bytes)")
            return f"Contents of {path}:\n" + "\n".join(items)
        except Exception as e:
            return f"Error listing directory: {str(e)}"
