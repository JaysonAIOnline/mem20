"""
Thought Process Tools for mem20 MCP Server

Provides reasoning paradigms:
- Tree-of-Thoughts (ToT) — multi-path exploration with evaluation
- Reflexion — reflect on failures, store lessons to memory
- Least-to-Most — decompose hard problems into sub-problems
- ReAct — interleave reasoning with tool calls
- Beam Search — maintain top-K paths at each step

These are mem20's own reasoning capabilities, separate from Hermes A2A.
"""
import mcp_types as mt


import os
import sys
import json
from typing import Any, Dict, List, Optional



class ThoughtProcessMixin:
    """Reasoning paradigm tools for mem20."""

    def register_thought_process_tools(self):
        """Register all thought process tools."""
        # Tree-of-Thoughts reasoning
        self.tools["tot_reason"] = mt.Tool(
            name="tot_reason",
            title="Tree-of-Thoughts Reasoning",
            description="ToT explores multiple reasoning paths simultaneously, evaluates each against criteria, and selects the best. Useful for complex decisions with many valid approaches.",
            input_schema={
                "type": "object",
                "properties": {
                    "problem": {"type": "string", "description": "Problem to reason about"},
                    "branches": {"type": "integer", "description": "Number of reasoning paths to explore", "default": 3},
                    "depth": {"type": "integer", "description": "Depth of each reasoning path", "default": 3},
                    "evaluation_criteria": {"type": "string", "description": "How to evaluate paths (e.g., 'feasibility,novelty,simplicity')", "default": "feasibility,novelty,simplicity"},
                },
                "required": ["problem"],
            },
        )
        # Tree-of-Thoughts for modeling decisions
        self.tools["tot_modeling"] = mt.Tool(
            name="tot_modeling",
            title="ToT Modeling Decision",
            description="Specialized ToT for 3D modeling decisions — explores topology, mesh flow, and construction approaches",
            input_schema={
                "type": "object",
                "properties": {
                    "objective": {"type": "string", "description": "What you're trying to model"},
                    "constraints": {"type": "string", "description": "Constraints (poly count, style, engine, etc.)", "default": ""},
                    "branches": {"type": "integer", "description": "Number of modeling approaches to explore", "default": 3},
                },
                "required": ["objective"],
            },
        )
        # Tree-of-Thoughts for problem diagnosis
        self.tools["tot_diagnose"] = mt.Tool(
            name="tot_diagnose",
            title="ToT Problem Diagnosis",
            description="Specialized ToT for diagnosing issues — explores multiple root causes and solutions",
            input_schema={
                "type": "object",
                "properties": {
                    "symptom": {"type": "string", "description": "What's going wrong"},
                    "context": {"type": "string", "description": "Additional context about the system/state", "default": ""},
                    "branches": {"type": "integer", "description": "Number of hypotheses to explore", "default": 4},
                },
                "required": ["symptom"],
            },
        )
        # Reflexion — reflect on failures, store lessons
        self.tools["reflexion"] = mt.Tool(
            name="reflexion",
            title="Reflexion",
            description="Reflect on a completed task or failure, extract lessons, and store them to memory for future improvement",
            input_schema={
                "type": "object",
                "properties": {
                    "task_description": {"type": "string", "description": "What was attempted"},
                    "outcome": {"type": "string", "description": "What happened — success or failure details"},
                    "lessons": {"type": "string", "description": "Key lessons learned", "default": ""},
                    "store_to_memory": {"type": "boolean", "description": "Store lessons to mem20 memory", "default": True},
                },
                "required": ["task_description", "outcome"],
            },
        )
        # Least-to-Most — decompose hard problems
        self.tools["least_to_most"] = mt.Tool(
            name="least_to_most",
            title="Least-to-Most Decomposition",
            description="Decompose a complex problem into sub-problems from simplest to hardest, solve each, then combine",
            input_schema={
                "type": "object",
                "properties": {
                    "problem": {"type": "string", "description": "Complex problem to decompose"},
                    "sub_problems": {"type": "integer", "description": "Number of sub-problems to create", "default": 3},
                },
                "required": ["problem"],
            },
        )
        # ReAct — interleave reasoning with tool calls
        self.tools["react_reason"] = mt.Tool(
            name="react_reason",
            title="ReAct Reasoning",
            description="Interleave reasoning with tool calls: Think → Act → Observe → Think → Act. For tasks needing external information.",
            input_schema={
                "type": "object",
                "properties": {
                    "goal": {"type": "string", "description": "What you're trying to accomplish"},
                    "available_tools": {"type": "string", "description": "Tools you can use (e.g., 'memory_search,web_search,file_read')", "default": ""},
                    "max_iterations": {"type": "integer", "description": "Maximum think-act cycles", "default": 5},
                },
                "required": ["goal"],
            },
        )
        # Beam Search — maintain top-K paths
        self.tools["beam_search"] = mt.Tool(
            name="beam_search",
            title="Beam Search Reasoning",
            description="Maintain top-K reasoning paths at each step instead of committing to one. More thorough than ToT for deep problems.",
            input_schema={
                "type": "object",
                "properties": {
                    "problem": {"type": "string", "description": "Problem to solve"},
                    "beam_width": {"type": "integer", "description": "Number of paths to maintain (beam width)", "default": 3},
                    "depth": {"type": "integer", "description": "Maximum search depth", "default": 4},
                },
                "required": ["problem"],
            },
        )
        # Get ToT state — query persistent tree state
        self.tools["get_cognitive_tree_state"] = mt.Tool(
            name="get_cognitive_tree_state",
            title="Get Cognitive Tree State",
            description="Retrieves persistent telemetry data, active paths, or pruned branches for a given session.",
            input_schema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "The unique active session tracking hash"},
                    "include_pruned": {"type": "boolean", "description": "If true, returns discarded and low-score branches", "default": False},
                },
                "required": ["session_id"],
            },
        )

        # ToT state query
        self.tools["get_cognitive_tree_state"] = mt.Tool(
            name="get_cognitive_tree_state",
            title="Get Cognitive Tree State",
            description="Retrieves persistent telemetry data, active paths, or pruned branches for a given session.",
            input_schema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "The unique active session tracking hash"},
                    "include_pruned": {"type": "boolean", "description": "If true, returns discarded and low-score branches", "default": False},
                },
                "required": ["session_id"],
            },
        )

    def _get_cog_path(self) -> str:
        """Get the path to mem20's cognitive engine."""
        default = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "cog")
        return os.environ.get("MEM20_COG_PATH", default)

    def _get_tot_db_path(self) -> str:
        """Get the path to the ToT state database."""
        default = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "tot_state.db")
        return os.environ.get("MEM20_TOT_DB", default)

    async def _get_cognitive_tree_state(self, args: Dict) -> str:
        """Retrieve persistent ToT state for a session."""
        import sqlite3
        session_id = args.get("session_id", "")
        include_pruned = args.get("include_pruned", False)

        if not session_id:
            return "Error: session_id is required"

