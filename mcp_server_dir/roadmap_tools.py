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

# try:
    # from mcp.server import Server
    # from mcp.server.lowlevel.server import ServerRequestContext
    # import mcp_types as mt
# except ImportError:
    # print("Error: mcp package not installed. Please install with: pip install mcp")
    # sys.exit(1)

sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
# try:
    from memory import remember, recall, status as mem_status, rebuild_index, ledger_view
    MEMORY_SYSTEM_AVAILABLE = True
# except ImportError:
    MEMORY_SYSTEM_AVAILABLE = False


class RoadmapToolsMixin:
    def register_roadmap_tools(self):
        self.tools["roadmap_create"] = mt.Tool(
            name="roadmap_create",
            title="Create Roadmap",
            description="Create a new roadmap in mem20",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Roadmap name"},
                    "description": {"type": "string", "description": "Roadmap description"},
                    "phases": {"type": "array", "items": {"type": "string"}, "description": "Phase names"},
                },
                "required": ["name"],
            },
        )
        self.tools["roadmap_list"] = mt.Tool(
            name="roadmap_list",
            title="List Roadmaps",
            description="List all roadmaps in mem20",
            inputSchema={"type": "object", "properties": {}},
        )
        self.tools["roadmap_get"] = mt.Tool(
            name="roadmap_get",
            title="Get Roadmap",
            description="Get details of a specific roadmap",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Roadmap name"},
                },
                "required": ["name"],
            },
        )
        self.tools["roadmap_update_phase"] = mt.Tool(
            name="roadmap_update_phase",
            title="Update Roadmap Phase",
            description="Update a roadmap phase status",
            inputSchema={
                "type": "object",
                "properties": {
                    "roadmap": {"type": "string", "description": "Roadmap name"},
                    "phase": {"type": "string", "description": "Phase name"},
                    "status": {"type": "string", "enum": ["planned", "in_progress", "completed", "blocked"], "description": "Phase status"},
                    "notes": {"type": "string", "default": ""},
                },
                "required": ["roadmap", "phase", "status"],
            },
        )

    async def _roadmap_create(self, args: Dict) -> str:
        name = args.get("name", "")
        description = args.get("description", "")
        phases = args.get("phases", [])
        roadmap_dir = Path(os.environ.get("MEM20_ROADMAPS_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "roadmaps")))
        roadmap_dir.mkdir(parents=True, exist_ok=True)
        roadmap_file = roadmap_dir / f"{name}.json"
        
        roadmap_data = {
            "name": name,
            "description": description,
            "phases": [{"name": p, "status": "planned", "notes": ""} for p in phases],
            "created": str(Path(__file__).stat().st_mtime),
        }
        
        roadmap_file.write_text(json.dumps(roadmap_data, indent=2))
        return f"Created roadmap '{name}' with {len(phases)} phases at {roadmap_file}"
    async def _roadmap_list(self) -> str:
        roadmap_dir = Path(os.environ.get("MEM20_ROADMAPS_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "roadmaps")))
        if not roadmap_dir.exists():
            return "No roadmaps found."
        
        roadmaps = list(roadmap_dir.glob("*.json"))
        if not roadmaps:
            return "No roadmaps found."
        
        result = "Roadmaps:\n"
        for rm in roadmaps:
            data = json.loads(rm.read_text())
            result += f"  - {data['name']}: {data['description']} ({len(data['phases'])} phases)\n"
        return result
    async def _roadmap_get(self, args: Dict) -> str:
        name = args.get("name", "")
        roadmap_file = Path(os.environ.get("MEM20_ROADMAPS_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "roadmaps"))) / f"{name}.json"
        if not roadmap_file.exists():
            return f"Roadmap '{name}' not found."
        
        data = json.loads(roadmap_file.read_text())
        result = f"Roadmap: {data['name']}\nDescription: {data['description']}\n\nPhases:\n"
        for i, phase in enumerate(data['phases'], 1):
            result += f"  {i}. {phase['name']} - {phase['status']}\n"
            if phase['notes']:
                result += f"     Notes: {phase['notes']}\n"
        return result
    async def _roadmap_update_phase(self, args: Dict) -> str:
        roadmap_name = args.get("roadmap", "")
        phase_name = args.get("phase", "")
        status = args.get("status", "")
        notes = args.get("notes", "")
        
        roadmap_file = Path(os.environ.get("MEM20_ROADMAPS_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "roadmaps"))) / f"{roadmap_name}.json"
        if not roadmap_file.exists():
            return f"Roadmap '{roadmap_name}' not found."
        
        data = json.loads(roadmap_file.read_text())
        for phase in data['phases']:
            if phase['name'] == phase_name:
                phase['status'] = status
                phase['notes'] = notes
                roadmap_file.write_text(json.dumps(data, indent=2))
                return f"Updated phase '{phase_name}' to '{status}' in roadmap '{roadmap_name}'"
        
        return f"Phase '{phase_name}' not found in roadmap '{roadmap_name}'"
