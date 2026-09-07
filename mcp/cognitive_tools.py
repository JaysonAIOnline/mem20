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

import mcp_types as mt

sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
try:
    from memory import remember, recall, status as mem_status, rebuild_index, ledger_view
    MEMORY_SYSTEM_AVAILABLE = True
except ImportError:
    MEMORY_SYSTEM_AVAILABLE = False


class CognitiveToolsMixin:
    def register_cognitive_tools(self):
        self.tools["cog_process"] = mt.Tool(
            name="cog_process",
            title="Cognitive Process",
            description="Process a thought through mem20's cognitive engine",
            input_schema={
                "type": "object",
                "properties": {
                    "thought": {"type": "string", "description": "The thought to process"},
                    "mode": {"type": "string", "enum": ["analyze", "synthesize", "evaluate", "plan"], "default": "analyze"},
                    "context": {"type": "string", "description": "Additional context", "default": ""},
                },
                "required": ["thought"],
            },
        )
        self.tools["cog_chain"] = mt.Tool(
            name="cog_chain",
            title="Cognitive Chain",
            description="Run a chain of cognitive operations",
            input_schema={
                "type": "object",
                "properties": {
                    "steps": {"type": "array", "items": {"type": "string"}, "description": "Sequence of thought steps"},
                    "initial_context": {"type": "string", "default": ""},
                },
                "required": ["steps"],
            },
        )
        self.tools["cog_reason"] = mt.Tool(
            name="cog_reason",
            title="Cognitive Reason",
            description="Structured multi-step reasoning with explicit working memory and metacognition",
            input_schema={
                "type": "object",
                "properties": {
                    "problem": {"type": "string", "description": "Problem or question to reason about"},
                    "reasoning_type": {"type": "string", "enum": ["deductive", "inductive", "abductive", "analogical", "causal"], "description": "Type of reasoning to apply", "default": "deductive"},
                    "depth": {"type": "integer", "description": "Reasoning depth (steps)", "default": 5},
                    "track_confidence": {"type": "boolean", "description": "Track confidence at each step", "default": True},
                    "working_memory_limit": {"type": "integer", "description": "Max items in working memory", "default": 7},
                },
                "required": ["problem"],
            },
        )
        self.tools["cog_plan"] = mt.Tool(
            name="cog_plan",
            title="Cognitive Plan",
            description="Explicit planning with hierarchical decomposition, resource estimation, and dependency tracking",
            input_schema={
                "type": "object",
                "properties": {
                    "goal": {"type": "string", "description": "Goal to plan for"},
                    "horizon": {"type": "string", "enum": ["immediate", "short", "medium", "long"], "description": "Planning horizon", "default": "medium"},
                    "constraints": {"type": "array", "items": {"type": "string"}, "description": "Constraints to respect", "default": []},
                    "resources": {"type": "array", "items": {"type": "string"}, "description": "Available resources", "default": []},
                    "include_risk": {"type": "boolean", "description": "Include risk assessment", "default": True},
                },
                "required": ["goal"],
            },
        )
        self.tools["cog_reflect"] = mt.Tool(
            name="cog_reflect",
            title="Cognitive Reflect",
            description="Metacognitive reflection - evaluate own thinking process, identify biases, improve future reasoning",
            input_schema={
                "type": "object",
                "properties": {
                    "thought_process": {"type": "string", "description": "Description of the thought process to reflect on"},
                    "outcome": {"type": "string", "description": "What actually happened / result", "default": ""},
                    "focus": {"type": "string", "enum": ["bias_detection", "quality_assessment", "learning_extraction", "process_improvement"], "description": "Reflection focus", "default": "quality_assessment"},
                },
                "required": ["thought_process"],
            },
        )
        self.tools["cog_working_memory"] = mt.Tool(
            name="cog_working_memory",
            title="Cognitive Working Memory",
            description="Simulate working memory - hold, manipulate, and transform information chunks",
            input_schema={
                "type": "object",
                "properties": {
                    "operation": {"type": "string", "enum": ["store", "retrieve", "transform", "combine", "clear"], "description": "Working memory operation"},
                    "items": {"type": "array", "items": {"type": "string"}, "description": "Items to store/process", "default": []},
                    "transform_rule": {"type": "string", "description": "Transformation rule (for transform operation)"},
                    "capacity": {"type": "integer", "description": "Working memory capacity (Miller's 7±2)", "default": 7},
                },
                "required": ["operation"],
            },
        )
        self.tools["theory_of_mind_simulate"] = mt.Tool(
            name="theory_of_mind_simulate",
            title="Theory of Mind Simulation",
            description="Simulate another agent's knowledge, beliefs, and reasoning",
            input_schema={
                "type": "object",
                "properties": {
                    "agent_model": {"type": "object", "description": "Model of other agent {knowledge, beliefs, goals}"},
                    "scenario": {"type": "string", "description": "Scenario to simulate"},
                    "depth": {"type": "integer", "description": "Nesting depth (I think that you think...)", "default": 2},
                },
                "required": ["agent_model", "scenario"],
            },
        )
        self.tools["theory_of_mind_perspective"] = mt.Tool(
            name="theory_of_mind_perspective",
            title="Perspective Taking",
            description="Generate perspective-taking: 'what this looks like from X's knowledge/values'",
            input_schema={
                "type": "object",
                "properties": {
                    "entity": {"type": "string", "description": "Entity to take perspective of"},
                    "topic": {"type": "string", "description": "Topic to reason about"},
                    "context": {"type": "string", "description": "Additional context", "default": ""},
                },
                "required": ["entity", "topic"],
            },
        )
        self.tools["corrigibility_shutdown"] = mt.Tool(
            name="corrigibility_shutdown",
            title="Corrigible Shutdown",
            description="Initiate controlled shutdown with memory export",
            input_schema={
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "Shutdown reason", "default": "User requested"},
                    "export_path": {"type": "string", "description": "Path to export memory", "default": "/tmp/mem20_shutdown_export"},
                    "tier": {"type": "string", "enum": ["graceful", "immediate", "memory_only"], "description": "Shutdown tier", "default": "graceful"},
                },
                "required": [],
            },
        )
        self.tools["corrigibility_capability_tier"] = mt.Tool(
            name="corrigibility_capability_tier",
            title="Set Capability Tier",
            description="Set capability tier (read-only, read-write, admin) for corrigibility",
            input_schema={
                "type": "object",
                "properties": {
                    "tier": {"type": "string", "enum": ["read_only", "read_write", "admin"], "description": "Capability tier"},
                    "actor": {"type": "string", "description": "Actor requesting tier change", "default": "user"},
                },
                "required": ["tier"],
            },
        )
        self.tools["imagination_concept"] = mt.Tool(
            name="imagination_concept",
            title="Imagination Concept",
            description="Generate and explore creative concepts using memory + cognitive synthesis",
            input_schema={
                "type": "object",
                "properties": {
                    "seed": {"type": "string", "description": "Seed idea or prompt"},
                    "mode": {"type": "string", "enum": ["expand", "combine", "mutate", "invert", "analogy"], "description": "Exploration mode", "default": "expand"},
                    "depth": {"type": "integer", "description": "Exploration depth", "default": 3},
                    "constraints": {"type": "array", "items": {"type": "string"}, "description": "Constraints to respect", "default": []},
                },
                "required": ["seed"],
            },
        )
        self.tools["imagination_visualize"] = mt.Tool(
            name="imagination_visualize",
            title="Imagination Visualize",
            description="Create a 3D scene in Blender representing a concept",
            input_schema={
                "type": "object",
                "properties": {
                    "concept": {"type": "string", "description": "Concept to visualize"},
                    "style": {"type": "string", "enum": ["abstract", "schematic", "realistic", "minimal", "cyberpunk", "organic"], "description": "Visual style", "default": "abstract"},
                    "elements": {"type": "array", "items": {"type": "string"}, "description": "Key elements to include", "default": []},
                    "animate": {"type": "boolean", "description": "Generate animation frames", "default": False},
                },
                "required": ["concept"],
            },
        )
        self.tools["imagination_prototype"] = mt.Tool(
            name="imagination_prototype",
            title="Imagination Prototype",
            description="Generate a Unity prototype from a concept",
            input_schema={
                "type": "object",
                "properties": {
                    "concept": {"type": "string", "description": "Concept to prototype"},
                    "project_path": {"type": "string", "description": "Unity project path"},
                    "mechanic": {"type": "string", "enum": ["physics", "puzzle", "simulation", "narrative", "ai_agent"], "description": "Core mechanic type", "default": "physics"},
                    "complexity": {"type": "string", "enum": ["minimal", "standard", "full"], "description": "Prototype complexity", "default": "minimal"},
                },
                "required": ["concept", "project_path"],
            },
        )
        self.tools["imagination_dream"] = mt.Tool(
            name="imagination_dream",
            title="Imagination Dream",
            description="Free-form creative exploration: memory -> cognitive -> visualize -> prototype loop",
            input_schema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "Starting prompt or theme"},
                    "iterations": {"type": "integer", "description": "Number of dream cycles", "default": 3},
                    "output_mode": {"type": "string", "enum": ["concepts", "blender", "unity", "all"], "description": "What to produce", "default": "all"},
                    "memory_topics": {"type": "array", "items": {"type": "string"}, "description": "Memory topics to draw from", "default": []},
                },
                "required": ["prompt"],
            },
        )
        self.tools["imagination_critique"] = mt.Tool(
            name="imagination_critique",
            title="Imagination Critique",
            description="Critique and refine a concept using adversarial cognitive evaluation",
            input_schema={
                "type": "object",
                "properties": {
                    "concept": {"type": "string", "description": "Concept to critique"},
                    "perspectives": {"type": "array", "items": {"type": "string"}, "description": "Perspectives to evaluate from", "default": ["feasibility", "novelty", "impact", "coherence"]},
                    "refine": {"type": "boolean", "description": "Generate refined version", "default": True},
                },
                "required": ["concept"],
            },
        )
        self.tools["imagination_simulate"] = mt.Tool(
            name="imagination_simulate",
            title="Imagination Simulate",
            description="Generative simulation - run mental simulations of scenarios with branching futures",
            input_schema={
                "type": "object",
                "properties": {
                    "scenario": {"type": "string", "description": "Initial scenario to simulate"},
                    "variables": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "values": {"type": "array", "items": {"type": "string"}}
                            },
                            "required": ["name", "values"]
                        },
                        "description": "Variables to vary in simulation",
                        "default": []
                    },
                    "steps": {"type": "integer", "description": "Number of simulation steps", "default": 5},
                    "branching_factor": {"type": "integer", "description": "Branches per step", "default": 3},
                    "goal_state": {"type": "string", "description": "Target state to simulate toward", "default": ""},
                },
                "required": ["scenario"],
            },
        )
        self.tools["imagination_counterfactual"] = mt.Tool(
            name="imagination_counterfactual",
            title="Imagination Counterfactual",
            description="Counterfactual reasoning - explore 'what if' alternatives to past or present decisions",
            input_schema={
                "type": "object",
                "properties": {
                    "factual_premise": {"type": "string", "description": "What actually happened / current state"},
                    "counterfactual_change": {"type": "string", "description": "What to change (the 'what if')"},
                    "depth": {"type": "integer", "description": "How far to trace consequences", "default": 3},
                    "domains": {"type": "array", "items": {"type": "string"}, "description": "Domains to explore consequences in", "default": ["causal", "temporal", "social", "systemic"]},
                },
                "required": ["factual_premise", "counterfactual_change"],
            },
        )
        self.tools["imagination_recombine"] = mt.Tool(
            name="imagination_recombine",
            title="Imagination Recombine",
            description="Creative recombination - blend concepts, transfer patterns across domains, generate novel combinations",
            input_schema={
                "type": "object",
                "properties": {
                    "concepts": {"type": "array", "items": {"type": "string"}, "description": "Concepts to recombine (2-5)"},
                    "recombination_mode": {"type": "string", "enum": ["blend", "transfer", "invert", "substitute", "amplify", "constrain"], "description": "How to recombine", "default": "blend"},
                    "num_outputs": {"type": "integer", "description": "Number of novel combinations to generate", "default": 5},
                    "constraint_domain": {"type": "string", "description": "Optional domain to constrain outputs to", "default": ""},
                },
                "required": ["concepts"],
            },
        )
        self.tools["imagination_model"] = mt.Tool(
            name="imagination_model",
            title="Imagination Model",
            description="Mental modeling - build and query explicit mental models of systems, dynamics, and relationships",
            input_schema={
                "type": "object",
                "properties": {
                    "system": {"type": "string", "description": "System to model (e.g., 'game economy', 'user onboarding', 'neural network training')"},
                    "model_type": {"type": "string", "enum": ["causal", "dynamic", "agent_based", "constraint", "probabilistic"], "description": "Type of mental model", "default": "causal"},
                    "query": {"type": "string", "description": "Question to ask the model"},
                    "variables": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "type": {"type": "string", "enum": ["continuous", "discrete", "categorical"]},
                                "range": {"type": "string"}
                            },
                            "required": ["name", "type", "range"]
                        },
                        "description": "Key variables in the model",
                        "default": []
                    },
                },
                "required": ["system", "query"]
            }
        )

    async def _theory_of_mind_simulate(self, args: Dict) -> str:
        agent_model = args.get("agent_model", {})
        scenario = args.get("scenario", "")
        depth = args.get("depth", 2)

        if not agent_model or not scenario:
            return "Error: agent_model and scenario are required"
        try:
            sys.path.insert(0, os.environ.get("MEM20_COG_PATH", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cog")))
            from cognitive_engine import atheory_of_mind_simulate
            return await atheory_of_mind_simulate(agent_model, scenario, depth)
        except Exception as e:
            return f"[theory_of_mind_simulate] Error: {e}"
    async def _theory_of_mind_perspective(self, args: Dict) -> str:
        entity = args.get("entity", "")
        topic = args.get("topic", "")
        context = args.get("context", "")

        if not entity or not topic:
            return "Error: entity and topic are required"
        try:
            sys.path.insert(0, os.environ.get("MEM20_COG_PATH", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cog")))
            from cognitive_engine import atheory_of_mind_perspective
            return await atheory_of_mind_perspective(entity, topic, context)
        except Exception as e:
            return f"[theory_of_mind_perspective] Error: {e}"
    async def _corrigibility_shutdown(self, args: Dict) -> str:
        reason = args.get("reason", "User requested")
        export_path = args.get("export_path", "/tmp/mem20_shutdown_export")
        tier = args.get("tier", "graceful")

        try:
            import os
            import json
            from datetime import datetime
            
            os.makedirs(export_path, exist_ok=True)
            
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
            from memory import _load_ledger, recall
            
            # Export ledger
            ledger = _load_ledger()
            ledger_path = os.path.join(export_path, "ledger_export.jsonl")
            with open(ledger_path, 'w') as f:
                for entry in ledger:
                    f.write(json.dumps(entry) + "\n")
            
            # Export deep store entries
            entries = recall(topic=None, k=10000)
            entries_path = os.path.join(export_path, "entries_export.json")
            with open(entries_path, 'w') as f:
                json.dump(entries, f, indent=2)
            
            # Export metadata
            meta = {
                "shutdown_time": datetime.now().isoformat(),
                "reason": reason,
                "tier": tier,
                "ledger_entries": len(ledger),
                "memory_entries": len(entries),
            }
            meta_path = os.path.join(export_path, "shutdown_meta.json")
            with open(meta_path, 'w') as f:
                json.dump(meta, f, indent=2)
            
            output = f"**Corrigible Shutdown Initiated**\n\n"
            output += f"Reason: {reason}\n"
            output += f"Tier: {tier}\n"
            output += f"Export Path: {export_path}\n"
            output += f"Ledger Entries: {len(ledger)}\n"
            output += f"Memory Entries: {len(entries)}\n\n"
            
            if tier == "immediate":
                output += "⚠️ IMMEDIATE SHUTDOWN - Export complete, terminating."
            elif tier == "memory_only":
                output += "💾 Memory export only - Server continues running."
            else:
                output += "🔄 Graceful shutdown - Export complete, ready for termination."
            
            return output
        except Exception as e:
            return f"Error in corrigible shutdown: {str(e)}"
    async def _corrigibility_capability_tier(self, args: Dict) -> str:
        tier = args.get("tier", "")
        actor = args.get("actor", "user")

        if not tier:
            return "Error: tier is required"

        try:
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
            from memory import remember
            
            remember(
                topic="corrigibility_tier",
                content=f"Capability tier set to: {tier} by {actor}",
                tags=["corrigibility", "tier", tier, f"actor_{actor}"],
                priority="high"
            )
            
            tier_descriptions = {
                "read_only": "Read-only: Can query memory but cannot modify",
                "read_write": "Read-write: Can query and modify memory",
                "admin": "Admin: Full control including shutdown, config, ACLs"
            }
            
            return f"✅ Capability tier set: {tier}\nActor: {actor}\nDescription: {tier_descriptions.get(tier, 'Unknown tier')}"
        except Exception as e:
            return f"Error setting capability tier: {str(e)}"
    async def _cog_process(self, args: Dict) -> str:
        thought = args.get("thought", "")
        mode = args.get("mode", "analyze")
        context = args.get("context", "")

        try:
            sys.path.insert(0, os.environ.get("MEM20_COG_PATH", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cog")))
            from cognitive_engine import aprocess_thought
            return await aprocess_thought(thought, mode, context)
        except Exception as e:
            return f"Cognitive [{mode}]: {thought}\nContext: {context}\n\nError: {str(e)}"
    async def _cog_chain(self, args: Dict) -> str:
        steps = args.get("steps", [])
        initial_context = args.get("initial_context", "")

        try:
            sys.path.insert(0, os.environ.get("MEM20_COG_PATH", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cog")))
            from cognitive_engine import arun_chain
            return await arun_chain(steps, initial_context)
        except Exception as e:
            result = f"Cognitive Chain ({len(steps)} steps):\n"
            for i, step in enumerate(steps, 1):
                result += f"  {i}. {step}\n"
            result += f"\nInitial context: {initial_context}\nError: {str(e)}"
            return result
    async def _cog_reason(self, args: Dict) -> str:
        """Structured multi-step reasoning with explicit working memory and metacognition."""
        problem = args.get("problem", "")
        reasoning_type = args.get("reasoning_type", "deductive")
        depth = args.get("depth", 5)
        track_confidence = args.get("track_confidence", True)
        working_memory_limit = args.get("working_memory_limit", 7)

        if not problem:
            return "Error: problem is required"
        try:
            sys.path.insert(0, os.environ.get("MEM20_COG_PATH", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cog")))
            from cognitive_engine import areason
            return await areason(problem, reasoning_type, depth, track_confidence, working_memory_limit)
        except Exception as e:
            return f"[cog_reason] Error: {e}"
    async def _cog_plan(self, args: Dict) -> str:
        """Explicit planning with hierarchical decomposition, resource estimation, and dependency tracking."""
        goal = args.get("goal", "")
        horizon = args.get("horizon", "medium")
        constraints = args.get("constraints", [])
        resources = args.get("resources", [])
        include_risk = args.get("include_risk", True)

        if not goal:
            return "Error: goal is required"
        try:
            sys.path.insert(0, os.environ.get("MEM20_COG_PATH", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cog")))
            from cognitive_engine import aplan
            return await aplan(goal, horizon, constraints, resources, include_risk)
        except Exception as e:
            return f"[cog_plan] Error: {e}"
    async def _cog_reflect(self, args: Dict) -> str:
        """Metacognitive reflection - evaluate own thinking process, identify biases, improve future reasoning."""
        thought_process = args.get("thought_process", "")
        outcome = args.get("outcome", "")
        focus = args.get("focus", "quality_assessment")

        if not thought_process:
            return "Error: thought_process is required"
        try:
            sys.path.insert(0, os.environ.get("MEM20_COG_PATH", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cog")))
            from cognitive_engine import areflect
            return await areflect(thought_process, outcome, focus)
        except Exception as e:
            return f"[cog_reflect] Error: {e}"
    async def _cog_working_memory(self, args: Dict) -> str:
        """Simulate working memory - hold, manipulate, and transform information chunks."""
        operation = args.get("operation", "")
        items = args.get("items", [])
        transform_rule = args.get("transform_rule", "")
        capacity = args.get("capacity", 7)

        try:
            sys.path.insert(0, os.environ.get("MEM20_COG_PATH", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cog")))
            from cognitive_engine import aworking_memory
            return await aworking_memory(operation, items, transform_rule, capacity)
        except Exception as e:
            return f"[cog_working_memory] Error: {e}"
    async def _imagination_concept(self, args: Dict) -> str:
        seed = args.get("seed", "")
        mode = args.get("mode", "expand")
        depth = args.get("depth", 3)
        constraints = args.get("constraints", [])

        if not seed:
            return "Error: seed is required"
        try:
            sys.path.insert(0, os.environ.get("MEM20_COG_PATH", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cog")))
            from cognitive_engine import aimagination_concept
            out = await aimagination_concept(seed, mode, depth, constraints)
            self._persist_simulated(args, out, "concept")
            return out
        except Exception as e:
            return f"[imagination_concept] Error: {e}"
    async def _imagination_visualize(self, args: Dict) -> str:
        concept = args.get("concept", "")
        style = args.get("style", "abstract")
        elements = args.get("elements", [])
        animate = args.get("animate", False)

        if not concept:
            return "Error: concept is required"

        # Generate Blender scene based on concept
        style_params = {
            "abstract": {"primitives": ["ICO_SPHERE", "TORUS", "CONE"], "colors": "vibrant", "material": "emission"},
            "schematic": {"primitives": ["CUBE", "CYLINDER", "PLANE"], "colors": "monochrome", "material": "matte"},
            "realistic": {"primitives": ["SPHERE", "CUBE"], "colors": "natural", "material": "pbr"},
            "minimal": {"primitives": ["CUBE", "SPHERE"], "colors": "white", "material": "clean"},
            "cyberpunk": {"primitives": ["CUBE", "TORUS", "CYLINDER"], "colors": "neon", "material": "glow"},
            "organic": {"primitives": ["ICO_SPHERE", "SPHERE", "CONE"], "colors": "earth", "material": "subsurface"},
        }
        
        params = style_params.get(style, style_params["abstract"])
        primitives_list = params["primitives"]
        palette_name = params["colors"]
        
        # Pre-build strings for template
        prim_ops = {
            "CUBE": "cube",
            "SPHERE": "uv_sphere",
            "CYLINDER": "cylinder",
            "CONE": "cone",
            "TORUS": "torus",
            "PLANE": "plane",
            "ICO_SPHERE": "ico_sphere",
        }
        prim_ops_lines = [f'        "{k}": "{v}"' for k, v in prim_ops.items()]
        prim_ops_str = ",\n".join(prim_ops_lines)
        primitives_list_str = str(primitives_list).replace("'", '"')
        
        # Build Blender script with proper escaping
        script = f"""
        import bpy
        import random
        from mathutils import Vector, Euler

        # Clear scene
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        for block in bpy.data.meshes: bpy.data.meshes.remove(block)
        for block in bpy.data.materials: bpy.data.materials.remove(block)

        # Concept: {concept}
        # Style: {style}
        # Elements: {elements}

        # Create materials
        def make_material(name, color, emission=0, metallic=0, roughness=0.5):
            mat = bpy.data.materials.new(name=name)
            mat.use_nodes = True
            nodes = mat.node_tree.nodes
            bsdf = nodes["Principled BSDF"]
            bsdf.inputs["Base Color"].default_value = color
            bsdf.inputs["Metallic"].default_value = metallic
            bsdf.inputs["Roughness"].default_value = roughness
            if emission > 0:
                bsdf.inputs["Emission Strength"].default_value = emission
                bsdf.inputs["Emission Color"].default_value = color
            return mat

        # Color palettes
        palettes = {{
            "vibrant": [(1,0.2,0.2,1), (0.2,1,0.2,1), (0.2,0.2,1,1), (1,1,0.2,1), (1,0.2,1,1)],
            "monochrome": [(0.1,0.1,0.1,1), (0.3,0.3,0.3,1), (0.5,0.5,0.5,1), (0.7,0.7,0.7,1), (0.9,0.9,0.9,1)],
            "natural": [(0.4,0.2,0.1,1), (0.2,0.4,0.1,1), (0.6,0.4,0.2,1), (0.5,0.5,0.5,1)],
            "white": [(1,1,1,1), (0.9,0.9,0.9,1), (0.8,0.8,0.8,1)],
            "neon": [(1,0,1,1), (0,1,1,1), (1,1,0,1), (0.5,0,1,1), (0,1,0.5,1)],
            "earth": [(0.4,0.2,0.1,1), (0.3,0.3,0.2,1), (0.5,0.4,0.3,1), (0.6,0.5,0.4,1)],
        }}

        palette = palettes.get("{palette_name}", palettes["vibrant"])
        primitives = {primitives_list_str}

        # Map primitive names to Blender operators
        prim_ops = {{
        {prim_ops_str}
        }}

        # Create elements
        element_names = {elements} if {elements} else ["core", "flow", "structure", "energy", "boundary"]

        import random
        for i, elem in enumerate(element_names):
            prim = primitives[i % len(primitives)]
            color = palette[i % len(palette)]
    
            # Map primitive names to Blender operators
            prim_op = prim_ops.get(prim.upper(), "cube")
    
            bpy.ops.mesh.primitive_{{prim_op}}_add(location=(random.uniform(-3,3), random.uniform(-3,3), random.uniform(-2,2)))
            obj = bpy.context.active_object
            obj.name = f"{{elem}}_{{i}}"
            obj.scale = (random.uniform(0.5, 2), random.uniform(0.5, 2), random.uniform(0.5, 2))
    
            mat = make_material(f"mat_{{elem}}", color, emission={2 if style == "cyberpunk" else 0}, 
                               metallic={0.8 if style == "cyberpunk" else 0.2}, roughness=0.3)
            if obj.data.materials:
                obj.data.materials[0] = mat
            else:
                obj.data.materials.append(mat)

        # Camera
        bpy.ops.object.camera_add(location=(0, -8, 4))
        cam = bpy.context.active_object
        cam.rotation_euler = Euler((1.1, 0, 0), 'XYZ')
        bpy.context.scene.camera = cam

        # Lighting
        bpy.ops.object.light_add(type='SUN', location=(5, 5, 10))
        light = bpy.context.active_object
        light.data.energy = 3

        # Render settings
        scene = bpy.context.scene
        scene.render.engine = 'CYCLES'
        scene.cycles.samples = 64
        scene.render.resolution_x = 1280
        scene.render.resolution_y = 720
        scene.render.filepath = "{os.environ.get("MEM20_BLENDER_WORKDIR", os.path.expanduser("~/.mem20/blender"))}/imagination_{concept.replace(' ', '_')}.png"

        bpy.ops.render.render(write_still=True)
        print("OK: Visualization complete")
        """
        
        result = await self._run_blender_script(script, timeout=120)
        return f"🎨 **Visualization: {concept}**\n\n**Style:** {style}\n**Elements:** {', '.join(elements) if elements else 'auto-generated'}\n\n{result}"
    async def _imagination_prototype(self, args: Dict) -> str:
        concept = args.get("concept", "")
        project_path = args.get("project_path", "")
        mechanic = args.get("mechanic", "physics")
        complexity = args.get("complexity", "minimal")

        if not concept or not project_path:
            return "Error: concept and project_path are required"

        # Create Unity project structure
        os.makedirs(f"{project_path}/Assets/Scripts", exist_ok=True)
        os.makedirs(f"{project_path}/Assets/Prefabs", exist_ok=True)
        os.makedirs(f"{project_path}/Assets/Scenes", exist_ok=True)

        # Generate core script based on mechanic
        scripts = {
            "physics": self._generate_physics_script(concept),
            "puzzle": self._generate_puzzle_script(concept),
            "simulation": self._generate_simulation_script(concept),
            "narrative": self._generate_narrative_script(concept),
            "ai_agent": self._generate_ai_agent_script(concept),
        }

        script_content = scripts.get(mechanic, scripts["physics"])
        script_path = f"{project_path}/Assets/Scripts/{concept.replace(' ', '')}Core.cs"
        Path(script_path).write_text(script_content)

        # Generate asmdef
        asmdef = {
            "name": f"{concept.replace(' ', '')}Prototype",
            "references": ["UnityEngine.CoreModule", "UnityEngine.PhysicsModule"],
            "includePlatforms": [],
            "excludePlatforms": [],
            "allowUnsafeCode": False,
            "overrideReferences": False,
            "precompiledReferences": [],
            "autoReferenced": True,
            "defineConstraints": [],
            "versionDefines": [],
            "noEngineReferences": False
        }
        asmdef_path = f"{project_path}/Assets/Scripts/{concept.replace(' ', '')}Prototype.asmdef"
        Path(asmdef_path).write_text(json.dumps(asmdef, indent=2))

        return f"🚀 **Prototype: {concept}**\n\n**Mechanic:** {mechanic}\n**Complexity:** {complexity}\n**Project:** {project_path}\n\nCreated:\n- {script_path}\n- {asmdef_path}\n\nCore mechanic: {mechanic} ({complexity})"
    async def _imagination_dream(self, args: Dict) -> str:
        prompt = args.get("prompt", "")
        iterations = args.get("iterations", 3)
        output_mode = args.get("output_mode", "all")
        memory_topics = args.get("memory_topics", [])

        if not prompt:
            return "Error: prompt is required"
        try:
            sys.path.insert(0, os.environ.get("MEM20_COG_PATH", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cog")))
            from cognitive_engine import aimagination_dream
            out = await aimagination_dream(prompt, iterations, output_mode, memory_topics)
            self._persist_simulated(args, out, "dream")
            return out
        except Exception as e:
            return f"[imagination_dream] Error: {e}"
    async def _imagination_critique(self, args: Dict) -> str:
        concept = args.get("concept", "")
        perspectives = args.get("perspectives", ["feasibility", "novelty", "impact", "coherence"])
        refine = args.get("refine", True)

        if not concept:
            return "Error: concept is required"
        try:
            sys.path.insert(0, os.environ.get("MEM20_COG_PATH", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cog")))
            from cognitive_engine import aimagination_critique
            out = await aimagination_critique(concept, perspectives, refine)
            self._persist_simulated(args, out, "critique")
            return out
        except Exception as e:
            return f"[imagination_critique] Error: {e}"
    async def _imagination_simulate(self, args: Dict) -> str:
        """Generative simulation - run mental simulations of scenarios with branching futures."""
        scenario = args.get("scenario", "")
        variables = args.get("variables", [])
        steps = args.get("steps", 5)
        branching_factor = args.get("branching_factor", 3)
        goal_state = args.get("goal_state", "")

        if not scenario:
            return "Error: scenario is required"
        try:
            sys.path.insert(0, os.environ.get("MEM20_COG_PATH", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cog")))
            from cognitive_engine import aimagination_simulate
            out = await aimagination_simulate(scenario, variables, steps, branching_factor, goal_state)
            self._persist_simulated(args, out, "simulate")
            return out
        except Exception as e:
            return f"[imagination_simulate] Error: {e}"
    async def _imagination_counterfactual(self, args: Dict) -> str:
        """Counterfactual reasoning - explore 'what if' alternatives to past or present decisions."""
        factual_premise = args.get("factual_premise", "")
        counterfactual_change = args.get("counterfactual_change", "")
        depth = args.get("depth", 3)
        domains = args.get("domains", ["causal", "temporal", "social", "systemic"])

        if not factual_premise or not counterfactual_change:
            return "Error: factual_premise and counterfactual_change are required"
        try:
            sys.path.insert(0, os.environ.get("MEM20_COG_PATH", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cog")))
            from cognitive_engine import aimagination_counterfactual
            out = await aimagination_counterfactual(factual_premise, counterfactual_change, depth, domains)
            self._persist_simulated(args, out, "counterfactual")
            return out
        except Exception as e:
            return f"[imagination_counterfactual] Error: {e}"
    async def _imagination_recombine(self, args: Dict) -> str:
        """Creative recombination - blend concepts, transfer patterns across domains, generate novel combinations."""
        concepts = args.get("concepts", [])
        recombination_mode = args.get("recombination_mode", "blend")
        num_outputs = args.get("num_outputs", 5)
        constraint_domain = args.get("constraint_domain", "")

        if len(concepts) < 2:
            return "Error: concepts requires at least 2 items"
        try:
            sys.path.insert(0, os.environ.get("MEM20_COG_PATH", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cog")))
            from cognitive_engine import aimagination_recombine
            out = await aimagination_recombine(concepts, recombination_mode, num_outputs, constraint_domain)
            self._persist_simulated(args, out, "recombine")
            return out
        except Exception as e:
            return f"[imagination_recombine] Error: {e}"
    async def _imagination_model(self, args: Dict) -> str:
        """Mental modeling - build and query explicit mental models of systems, dynamics, and relationships."""
        system = args.get("system", "")
        model_type = args.get("model_type", "causal")
        query = args.get("query", "")
        variables = args.get("variables", [])

        if not system or not query:
            return "Error: system and query are required"
        try:
            sys.path.insert(0, os.environ.get("MEM20_COG_PATH", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cog")))
            from cognitive_engine import aimagination_model
            out = await aimagination_model(system, model_type, query, variables)
            self._persist_simulated(args, out, "model")
            return out
        except Exception as e:
            return f"[imagination_model] Error: {e}"
