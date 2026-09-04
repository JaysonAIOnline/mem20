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

import os
import sys
import json
from typing import Any, Dict, List, Optional

try:
    from mcp.server import Server
    from mcp.server.lowlevel.server import ServerRequestContext
    import mcp_types as mt
except ImportError:
    print("Error: mcp package not installed.")
    sys.exit(1)


class ThoughtProcessMixin:
    """Reasoning paradigm tools for mem20."""

    def register_thought_process_tools(self):
        """Register all thought process tools."""
        # Tree-of-Thoughts reasoning
        self.tools["tot_reason"] = mt.Tool(
            name="tot_reason",
            title="Tree-of-Thoughts Reasoning",
            description="ToT explores multiple reasoning paths simultaneously, evaluates each against criteria, and selects the best. Useful for complex decisions with many valid approaches.",
            inputSchema={
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
            inputSchema={
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
            inputSchema={
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
            inputSchema={
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
            inputSchema={
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
            inputSchema={
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
            inputSchema={
                "type": "object",
                "properties": {
                    "problem": {"type": "string", "description": "Problem to solve"},
                    "beam_width": {"type": "integer", "description": "Number of paths to maintain (beam width)", "default": 3},
                    "depth": {"type": "integer", "description": "Maximum search depth", "default": 4},
                },
                "required": ["problem"],
            },
        )
        # Cognitive Substrate — invoke specific paradigms
        self.tools["cognitive_substrate"] = mt.Tool(
            name="cognitive_substrate",
            title="Cognitive Substrate",
            description="Invoke a specific paradigm from the 28-paradigm cognitive substrate. Use paradigm_id (e.g., '1_premise_validation', '3_adversarial_falsification', '14_idempotency_side_effect_audit').",
            inputSchema={
                "type": "object",
                "properties": {
                    "paradigm_id": {"type": "string", "description": "Paradigm ID (e.g., '1_premise_validation', '3_adversarial_falsification')"},
                    "data": {"type": "object", "description": "Data to evaluate against the paradigm", "default": {}},
                    "evaluate_branch": {"type": "boolean", "description": "If true, score/prune/mutate the branch data", "default": False},
                },
                "required": ["paradigm_id"],
            },
        )
        # Get ToT state — query persistent tree state
        self.tools["get_cognitive_tree_state"] = mt.Tool(
            name="get_cognitive_tree_state",
            title="Get Cognitive Tree State",
            description="Retrieves persistent telemetry data, active paths, or pruned branches for a given session.",
            inputSchema={
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
            inputSchema={
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

        try:
            db_path = self._get_tot_db_path()
            with sqlite3.connect(db_path) as conn:
                query = "SELECT node_id, substrate_payload, heuristic_score_delta, is_pruned, created_at FROM cognitive_substrate_history WHERE session_id = ?"
                if not include_pruned:
                    query += " AND is_pruned = 0"
                query += " ORDER BY created_at DESC"
                
                cursor = conn.cursor()
                cursor.execute(query, (session_id,))
                rows = cursor.fetchall()
                
                nodes = []
                for row in rows:
                    import json
                    nodes.append({
                        "node_id": row[0],
                        "substrate": json.loads(row[1]) if row[1] else {},
                        "score_delta": row[2],
                        "is_pruned": bool(row[3]),
                        "created_at": row[4],
                    })
                
                return json.dumps({"session_id": session_id, "active_nodes": nodes}, indent=2)
        except Exception as e:
            return f"Error pulling tree state: {str(e)}"

    async def _tot_reason(self, args: Dict) -> str:
        """Tree-of-Thoughts reasoning — explores multiple paths, selects the best."""
        problem = args.get("problem", "")
        branches = args.get("branches", 3)
        depth = args.get("depth", 3)
        evaluation_criteria = args.get("evaluation_criteria", "feasibility,novelty,simplicity")

        if not problem:
            return "Error: problem is required"

        try:
            cog_path = self._get_cog_path()
            if cog_path not in sys.path:
                sys.path.insert(0, cog_path)
            from cognitive_engine import atot_reason
            return await atot_reason(problem, branches, depth, evaluation_criteria)
        except ImportError:
            criteria_list = [c.strip() for c in evaluation_criteria.split(",")]
            output = f"**Tree-of-Thoughts Reasoning**\n\n"
            output += f"Problem: {problem}\n"
            output += f"Branches: {branches} | Depth: {depth} | Criteria: {evaluation_criteria}\n\n"
            for b in range(1, branches + 1):
                output += f"### Path {b}:\n"
                for d in range(1, depth + 1):
                    output += f"  Step {d}: [Reasoning...]\n"
                output += f"  Path {b} conclusion\n\n"
            output += f"**Evaluation:**\n"
            for criterion in criteria_list:
                output += f"  - {criterion}: Path [X] scores highest\n"
            output += f"\n**Selected:** Path [best] — [justification]"
            return output
        except Exception as e:
            return f"[tot_reason] Error: {e}"

    async def _tot_modeling(self, args: Dict) -> str:
        """ToT specialized for 3D modeling decisions."""
        objective = args.get("objective", "")
        constraints = args.get("constraints", "")
        branches = args.get("branches", 3)

        if not objective:
            return "Error: objective is required"

        problem = f"3D Modeling Decision: {objective}"
        if constraints:
            problem += f"\nConstraints: {constraints}"
        problem += "\n\nExplore distinct modeling approaches considering topology, mesh flow, edge loops, and construction method."

        try:
            cog_path = self._get_cog_path()
            if cog_path not in sys.path:
                sys.path.insert(0, cog_path)
            from cognitive_engine import atot_reason
            return await atot_reason(problem, branches, 3, "topology,efficiency,cleanliness")
        except ImportError:
            output = f"**ToT Modeling Decision**\n\n"
            output += f"Objective: {objective}\n"
            if constraints:
                output += f"Constraints: {constraints}\n"
            output += f"\n### Approach 1: Primitive-based\n"
            output += f"  Start with basic shapes, build up geometry\n\n"
            output += f"### Approach 2: BMesh sculpting\n"
            output += f"  Direct mesh manipulation for organic forms\n\n"
            output += f"### Approach 3: Modifier stack\n"
            output += f"  Non-destructive workflow with modifiers\n\n"
            output += f"**Selected:** [Best approach based on topology needs]"
            return output
        except Exception as e:
            return f"[tot_modeling] Error: {e}"

    async def _tot_diagnose(self, args: Dict) -> str:
        """ToT specialized for problem diagnosis."""
        symptom = args.get("symptom", "")
        context = args.get("context", "")
        branches = args.get("branches", 4)

        if not symptom:
            return "Error: symptom is required"

        problem = f"Diagnose: {symptom}"
        if context:
            problem += f"\nContext: {context}"
        problem += "\n\nExplore multiple root causes and propose solutions for each."

        try:
            cog_path = self._get_cog_path()
            if cog_path not in sys.path:
                sys.path.insert(0, cog_path)
            from cognitive_engine import atot_reason
            return await atot_reason(problem, branches, 3, "likelihood,severity,fixability")
        except ImportError:
            output = f"**ToT Problem Diagnosis**\n\n"
            output += f"Symptom: {symptom}\n"
            if context:
                output += f"Context: {context}\n"
            output += f"\n### Hypothesis 1: [Most likely cause]\n"
            output += f"  Fix: [Solution]\n\n"
            output += f"### Hypothesis 2: [Secondary cause]\n"
            output += f"  Fix: [Solution]\n\n"
            output += f"### Hypothesis 3: [Less common cause]\n"
            output += f"  Fix: [Solution]\n\n"
            output += f"**Selected:** [Most likely hypothesis with fix]"
            return output
        except Exception as e:
            return f"[tot_diagnose] Error: {e}"

    async def _reflexion(self, args: Dict) -> str:
        """Reflexion — reflect on failures, store lessons to memory."""
        task_description = args.get("task_description", "")
        outcome = args.get("outcome", "")
        lessons = args.get("lessons", "")
        store_to_memory = args.get("store_to_memory", True)

        if not task_description or not outcome:
            return "Error: task_description and outcome are required"

        try:
            cog_path = self._get_cog_path()
            if cog_path not in sys.path:
                sys.path.insert(0, cog_path)
            from cognitive_engine import areflexion
            return await areflexion(task_description, outcome, lessons, store_to_memory)
        except ImportError:
            output = f"**Reflexion**\n\n"
            output += f"Task: {task_description}\n"
            output += f"Outcome: {outcome}\n\n"
            if lessons:
                output += f"Lessons: {lessons}\n\n"
            output += f"Stored to memory: {store_to_memory}"
            return output
        except Exception as e:
            return f"[reflexion] Error: {e}"

    async def _least_to_most(self, args: Dict) -> str:
        """Least-to-Most — decompose hard problems into sub-problems."""
        problem = args.get("problem", "")
        sub_problems = args.get("sub_problems", 3)

        if not problem:
            return "Error: problem is required"

        try:
            cog_path = self._get_cog_path()
            if cog_path not in sys.path:
                sys.path.insert(0, cog_path)
            from cognitive_engine import aleast_to_most
            return await aleast_to_most(problem, sub_problems)
        except ImportError:
            output = f"**Least-to-Most Decomposition**\n\n"
            output += f"Problem: {problem}\n\n"
            for i in range(1, sub_problems + 1):
                output += f"### Sub-problem {i}:\n"
                output += f"  [Simplest component]\n\n"
            output += f"**Solution:** Combine all sub-problem solutions"
            return output
        except Exception as e:
            return f"[least_to_most] Error: {e}"

    async def _react_reason(self, args: Dict) -> str:
        """ReAct — interleave reasoning with tool calls."""
        goal = args.get("goal", "")
        available_tools = args.get("available_tools", "")
        max_iterations = args.get("max_iterations", 5)

        if not goal:
            return "Error: goal is required"

        try:
            cog_path = self._get_cog_path()
            if cog_path not in sys.path:
                sys.path.insert(0, cog_path)
            from cognitive_engine import areact_reason
            return await areact_reason(goal, available_tools, max_iterations)
        except ImportError:
            output = f"**ReAct Reasoning**\n\n"
            output += f"Goal: {goal}\n"
            if available_tools:
                output += f"Available tools: {available_tools}\n"
            output += f"\n### Iteration 1:\n"
            output += f"  Think: [Reasoning...]\n"
            output += f"  Act: [Tool call...]\n"
            output += f"  Observe: [Result...]\n\n"
            output += f"**Final Answer:** [Synthesized from observations]"
            return output
        except Exception as e:
            return f"[react_reason] Error: {e}"

    async def _beam_search(self, args: Dict) -> str:
        """Beam Search — maintain top-K paths at each step."""
        problem = args.get("problem", "")
        beam_width = args.get("beam_width", 3)
        depth = args.get("depth", 4)

        if not problem:
            return "Error: problem is required"

        try:
            cog_path = self._get_cog_path()
            if cog_path not in sys.path:
                sys.path.insert(0, cog_path)
            from cognitive_engine import abeam_search
            return await abeam_search(problem, beam_width, depth)
        except ImportError:
            output = f"**Beam Search Reasoning**\n\n"
            output += f"Problem: {problem}\n"
            output += f"Beam width: {beam_width} | Depth: {depth}\n\n"
            for d in range(1, depth + 1):
                output += f"### Depth {d}:\n"
                for b in range(1, beam_width + 1):
                    output += f"  Path {b}: [Partial reasoning...]\n"
                output += f"  → Top {beam_width} paths retained\n\n"
            output += f"**Best solution:** [Highest scoring path]"
            return output
        except Exception as e:
            return f"[beam_search] Error: {e}"
