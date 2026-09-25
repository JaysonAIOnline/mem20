"""
Procedural Tools Mixin for mem20 MCP Server

Provides procedural (how-to) skill tools backed by the memory engine's
ProceduralMemory store (procedural_memory.json under MEM20_STORE_PATH):

- procedural_add_skill
- procedural_get_skill
- procedural_find_skills
- procedural_execute_skill
- procedural_learn
- procedural_list_skills

Phase 8.1 kill-switch: the same MEM20_FLAG_WORLDMODEL_20 flag that governs the
world-model / self-model / affective toolset also gates these tools, so the
8.1 surface stays consistent. Keep the flag check below in sync with
tools/world_tools.py.
"""

import os
import sys
from typing import Any, Dict

try:
    from mcp.server import Server
    from mcp.server.lowlevel.server import ServerRequestContext
    import mcp_types as mt
except ImportError:
    print("Error: mcp package not installed. Please install with: pip install mcp")
    sys.exit(1)

# Phase 8.1 kill-switch (mirror of tools/world_tools.py). When off, the
# procedural MCP tools are NOT registered so 8.1 is not surfaceable.
PROCEDURAL_ENABLED = (
    os.environ.get("MEM20_FLAG_WORLDMODEL_20", "1").strip().lower()
    not in ("0", "false", "no", "off", "")
)


class ProceduralToolsMixin:
    """Procedural skill tools for mem20."""

    def register_procedural_tools(self):
        """Register all procedural skill tools (honors the 8.1 kill-switch)."""
        self.procedural_enabled = PROCEDURAL_ENABLED
        if not PROCEDURAL_ENABLED:
            return
        self.tools["procedural_add_skill"] = mt.Tool(
            name="procedural_add_skill",
            title="Add Procedural Skill",
            description="Add a procedural skill (how-to knowledge) with steps, preconditions, and effects",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Skill name"},
                    "description": {"type": "string", "description": "Skill description"},
                    "steps": {"type": "array", "items": {"type": "string"}, "description": "Ordered steps"},
                    "preconditions": {"type": "object", "description": "Precondition key-value pairs", "default": {}},
                    "effects": {"type": "object", "description": "Effect key-value pairs", "default": {}},
                    "category": {"type": "string", "description": "Skill category", "default": "general"},
                },
                "required": ["name", "description", "steps"],
            },
        )

        self.tools["procedural_get_skill"] = mt.Tool(
            name="procedural_get_skill",
            title="Get Procedural Skill",
            description="Retrieve a procedural skill by name",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Skill name"},
                },
                "required": ["name"],
            },
        )
        self.tools["procedural_find_skills"] = mt.Tool(
            name="procedural_find_skills",
            title="Find Procedural Skills",
            description="Find skills matching category and/or preconditions",
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "Filter by category", "default": ""},
                    "preconditions": {"type": "object", "description": "Match skills with these preconditions", "default": {}},
                },
                "required": [],
            },
        )
        self.tools["procedural_execute_skill"] = mt.Tool(
            name="procedural_execute_skill",
            title="Execute Procedural Skill",
            description="Execute a skill with optional context",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Skill name"},
                    "context": {"type": "object", "description": "Execution context", "default": {}},
                },
                "required": ["name"],
            },
        )
        self.tools["procedural_learn"] = mt.Tool(
            name="procedural_learn",
            title="Learn from Skill Execution",
            description="Update a skill based on execution experience",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Skill name"},
                    "success": {"type": "boolean", "description": "Whether execution succeeded"},
                    "modified_steps": {"type": "array", "items": {"type": "string"}, "description": "Modified steps if any", "default": []},
                    "new_preconditions": {"type": "object", "description": "New preconditions learned", "default": {}},
                    "new_effects": {"type": "object", "description": "New effects learned", "default": {}},
                },
                "required": ["name", "success"],
            },
        )
        self.tools["procedural_list_skills"] = mt.Tool(
            name="procedural_list_skills",
            title="List Procedural Skills",
            description="List all procedural skills, optionally filtered by category",
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "Filter by category", "default": ""},
                },
                "required": [],
            },
        )

    def _procedural_store_path(self):
        """Helper to get the memory store path."""
        return os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store"))

    async def _procedural_add_skill(self, args: Dict) -> str:
        name = args.get("name", "")
        description = args.get("description", "")
        steps = args.get("steps", [])
        preconditions = args.get("preconditions", {})
        effects = args.get("effects", {})
        category = args.get("category", "general")

        if not name or not description or not steps:
            return "Error: name, description, and steps are required"

        try:
            sys.path.insert(0, self._procedural_store_path())
            from memory import procedural_add_skill

            result = procedural_add_skill(name, description, steps, preconditions, effects, category)
            return f"✅ Skill added: {result['skill']}\nDescription: {result['description']}\nSteps: {len(result['steps'])}"
        except Exception as e:
            return f"Error adding skill: {str(e)}"

    async def _procedural_get_skill(self, args: Dict) -> str:
        name = args.get("name", "")

        if not name:
            return "Error: name is required"

        try:
            sys.path.insert(0, self._procedural_store_path())
            from memory import procedural_get_skill

            result = procedural_get_skill(name)
            if "error" in result:
                return result["error"]

            output = f"**Skill: {result['name']}**\n"
            output += f"  Description: {result['description']}\n"
            output += f"  Category: {result['category']}\n"
            output += f"  Steps ({len(result['steps'])}):\n"
            for i, step in enumerate(result['steps'], 1):
                output += f"    {i}. {step}\n"
            output += f"  Preconditions: {result['preconditions']}\n"
            output += f"  Effects: {result['effects']}\n"
            output += f"  Execution count: {result['execution_count']}\n"
            output += f"  Success rate: {result['success_rate']:.2f}"
            return output
        except Exception as e:
            return f"Error getting skill: {str(e)}"

    async def _procedural_find_skills(self, args: Dict) -> str:
        category = args.get("category", "")
        preconditions = args.get("preconditions", {})

        try:
            sys.path.insert(0, self._procedural_store_path())
            from memory import procedural_find_skills

            skills = procedural_find_skills(category if category else None, preconditions if preconditions else None)

            if not skills:
                return f"No skills found (category: {category or 'all'})"

            output = f"**Found {len(skills)} skills** (category: {category or 'all'})\n\n"
            for s in skills:
                output += f"• **{s['name']}** ({s['category']}): {s['description'][:80]}...\n"
                output += f"  Steps: {len(s['steps'])}, Executions: {s['execution_count']}, Success: {s['success_rate']:.2f}\n\n"
            return output
        except Exception as e:
            return f"Error finding skills: {str(e)}"

    async def _procedural_execute_skill(self, args: Dict) -> str:
        name = args.get("name", "")
        context = args.get("context", {})

        if not name:
            return "Error: name is required"

        try:
            sys.path.insert(0, self._procedural_store_path())
            from memory import procedural_execute_skill

            result = procedural_execute_skill(name, context)
            if "error" in result:
                return result["error"]

            output = f"**Executed: {name}**\n"
            output += f"  Context: {context}\n"
            output += f"  Result: {result}"
            return output
        except Exception as e:
            return f"Error executing skill: {str(e)}"

    async def _procedural_learn(self, args: Dict) -> str:
        name = args.get("name", "")
        success = args.get("success", False)
        modified_steps = args.get("modified_steps", [])
        new_preconditions = args.get("new_preconditions", {})
        new_effects = args.get("new_effects", {})

        if not name:
            return "Error: name is required"

        try:
            sys.path.insert(0, self._procedural_store_path())
            from memory import procedural_learn

            result = procedural_learn(name, success, modified_steps if modified_steps else None,
                                      new_preconditions if new_preconditions else None,
                                      new_effects if new_effects else None)
            return f"✅ Learning recorded for {name}: {result}"
        except Exception as e:
            return f"Error learning from skill: {str(e)}"

    async def _procedural_list_skills(self, args: Dict) -> str:
        category = args.get("category", "")

        try:
            sys.path.insert(0, self._procedural_store_path())
            from memory import procedural_list_skills

            skills = procedural_list_skills(category if category else None)

            if not skills:
                return f"No skills found (category: {category or 'all'})"

            output = f"**All Skills** (category: {category or 'all'})\n\n"
            for s in skills:
                output += f"• **{s['name']}** ({s['category']}): {s['description'][:80]}...\n"
            return output
        except Exception as e:
            return f"Error listing skills: {str(e)}"