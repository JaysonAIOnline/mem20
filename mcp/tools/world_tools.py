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

try:
    from mcp.server import Server
    from mcp.server.lowlevel.server import ServerRequestContext
    import mcp_types as mt
except ImportError:
    print("Error: mcp package not installed. Please install with: pip install mcp")
    sys.exit(1)

sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
try:
    from memory import remember, recall, status as mem_status, rebuild_index, ledger_view
    MEMORY_SYSTEM_AVAILABLE = True
except ImportError:
    MEMORY_SYSTEM_AVAILABLE = False


class WorldToolsMixin:
    def register_world_tools(self):
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
        self.tools["world_model_add_variable"] = mt.Tool(
            name="world_model_add_variable",
            title="World Model Add Variable",
            description="Add a state variable to the world model",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Variable name"},
                    "initial_value": {"type": "number", "description": "Initial value"},
                    "dynamics": {"type": "string", "description": "Dynamics type (constant, linear, exponential)", "default": "constant"},
                },
                "required": ["name", "initial_value"],
            },
        )
        self.tools["world_model_add_rule"] = mt.Tool(
            name="world_model_add_rule",
            title="World Model Add Rule",
            description="Add a transition rule to the world model",
            inputSchema={
                "type": "object",
                "properties": {
                    "condition": {"type": "string", "description": "Condition expression (e.g., 'temperature > 100')"},
                    "effect": {"type": "object", "description": "Effect as dict (e.g., {'pressure': 10})"},
                    "probability": {"type": "number", "description": "Rule probability", "default": 1.0},
                },
                "required": ["condition", "effect"],
            },
        )
        self.tools["world_model_simulate"] = mt.Tool(
            name="world_model_simulate",
            title="World Model Simulate",
            description="Run world model simulation for specified steps",
            inputSchema={
                "type": "object",
                "properties": {
                    "steps": {"type": "integer", "description": "Number of simulation steps", "default": 10},
                },
                "required": [],
            },
        )
        self.tools["world_model_predict"] = mt.Tool(
            name="world_model_predict",
            title="World Model Predict",
            description="Make predictions using the world model",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Predictive query"},
                    "horizon": {"type": "integer", "description": "Prediction horizon", "default": 10},
                },
                "required": ["query"],
            },
        )
        self.tools["world_model_get_state"] = mt.Tool(
            name="world_model_get_state",
            title="World Model Get State",
            description="Get current world model state",
            inputSchema={"type": "object", "properties": {}},
        )
        self.tools["world_model_reset"] = mt.Tool(
            name="world_model_reset",
            title="World Model Reset",
            description="Reset the world model to empty",
            inputSchema={"type": "object", "properties": {}},
        )
        self.tools["world_model_record_prediction"] = mt.Tool(
            name="world_model_record_prediction",
            title="World Model Record Prediction",
            description="Record a prediction emitted by simulation for later reality-checking. "
                        "Returns a prediction_id used as prediction_ref when promoting a "
                        "simulated fact via resolved_via_prediction_error.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The predictive query / claim"},
                    "prediction": {"type": "string", "description": "The predicted outcome", "default": ""},
                    "horizon": {"type": "integer", "description": "Forecast horizon (steps)", "default": 10},
                },
                "required": ["query"],
            },
        )
        self.tools["world_model_resolve_prediction"] = mt.Tool(
            name="world_model_resolve_prediction",
            title="World Model Resolve Prediction",
            description="Resolve a recorded prediction against reality. Set "
                        "resolved_in_favor=true only when the simulated belief was confirmed; "
                        "this is the evidence required to promote via prediction-error resolution.",
            inputSchema={
                "type": "object",
                "properties": {
                    "prediction_id": {"type": "string", "description": "prediction_id from world_model_record_prediction"},
                    "observed_outcome": {"type": "string", "description": "What actually happened"},
                    "resolved_in_favor": {"type": "boolean", "description": "True only if the simulated belief was confirmed"},
                },
                "required": ["prediction_id", "observed_outcome", "resolved_in_favor"],
            },
        )
        self.tools["affective_set_value"] = mt.Tool(
            name="affective_set_value",
            title="Set Affective Value",
            description="Set a core value with weight and description",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Value name"},
                    "weight": {"type": "number", "description": "Value weight/importance"},
                    "description": {"type": "string", "description": "Value description", "default": ""},
                },
                "required": ["name", "weight"],
            },
        )
        self.tools["affective_set_emotion"] = mt.Tool(
            name="affective_set_emotion",
            title="Set Affective Emotion",
            description="Set current emotional state",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Emotion name"},
                    "intensity": {"type": "number", "description": "Intensity -1.0 to 1.0"},
                    "cause": {"type": "string", "description": "Cause of emotion", "default": ""},
                },
                "required": ["name", "intensity"],
            },
        )
        self.tools["affective_add_goal"] = mt.Tool(
            name="affective_add_goal",
            title="Add Affective Goal",
            description="Add or update a goal with priority and target state",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Goal name"},
                    "priority": {"type": "number", "description": "Goal priority"},
                    "target_state": {"type": "object", "description": "Target state as dict", "default": {}},
                },
                "required": ["name", "priority"],
            },
        )
        self.tools["affective_update_preference"] = mt.Tool(
            name="affective_update_preference",
            title="Update Affective Preference",
            description="Update learned preference for a context",
            inputSchema={
                "type": "object",
                "properties": {
                    "context": {"type": "string", "description": "Context name"},
                    "preference": {"type": "string", "description": "Preference name"},
                    "strength": {"type": "number", "description": "Preference strength"},
                },
                "required": ["context", "preference", "strength"],
            },
        )
        self.tools["affective_evaluate"] = mt.Tool(
            name="affective_evaluate",
            title="Affective Evaluate",
            description="Evaluate a situation against values and goals",
            inputSchema={
                "type": "object",
                "properties": {
                    "situation": {"type": "object", "description": "Situation as dict"},
                },
                "required": ["situation"],
            },
        )
        self.tools["affective_get_state"] = mt.Tool(
            name="affective_get_state",
            title="Get Affective State",
            description="Get current affective state (values, emotions, goals, preferences)",
            inputSchema={"type": "object", "properties": {}},
        )

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
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
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
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
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
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
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
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
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
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
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
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
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
    async def _world_model_add_variable(self, args: Dict) -> str:
        name = args.get("name", "")
        initial_value = args.get("initial_value", 0)
        dynamics = args.get("dynamics", "constant")

        if not name:
            return "Error: name is required"

        try:
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
            from memory import world_model_add_variable
            
            result = world_model_add_variable(name, initial_value, dynamics)
            return f"✅ Variable added: {result['variable']} = {result['initial_value']} ({result['dynamics']})"
        except Exception as e:
            return f"Error adding world model variable: {str(e)}"
    async def _world_model_add_rule(self, args: Dict) -> str:
        condition = args.get("condition", "")
        effect = args.get("effect", {})
        probability = args.get("probability", 1.0)

        if not condition or not effect:
            return "Error: condition and effect are required"

        try:
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
            from memory import world_model_add_rule
            
            result = world_model_add_rule(condition, effect, probability)
            return f"✅ Rule added: IF {result['condition']} THEN {result['effect']} (p={result['probability']})"
        except Exception as e:
            return f"Error adding world model rule: {str(e)}"
    async def _world_model_simulate(self, args: Dict) -> str:
        steps = args.get("steps", 10)

        try:
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
            from memory import world_model_simulate
            
            result = world_model_simulate(steps)
            output = f"**World Model Simulation** ({result['steps']} steps)\n\n"
            output += f"Final state: {result['final_state']}\n\n"
            output += "Trajectory:\n"
            for i, state in enumerate(result['trajectory']):
                output += f"  Step {i+1}: {state}\n"
            return output
        except Exception as e:
            return f"Error simulating world model: {str(e)}"
    async def _world_model_predict(self, args: Dict) -> str:
        query = args.get("query", "")
        horizon = args.get("horizon", 10)

        if not query:
            return "Error: query is required"

        try:
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
            from memory import world_model_predict
            
            result = world_model_predict(query, horizon)
            output = f"**World Model Prediction**\n\n"
            output += f"Query: {result['query']}\n"
            if 'prediction' in result:
                output += f"Prediction: {result['prediction']}\n"
                output += f"Final value: {result['final_value']} (threshold: {result['threshold']})\n"
                output += f"Trajectory: {result['trajectory']}\n"
            else:
                output += f"Final state: {result['final_state']}\n"
                output += f"Trajectory: {result['trajectory']}\n"
            return output
        except Exception as e:
            return f"Error predicting with world model: {str(e)}"
    async def _world_model_get_state(self, args: Dict) -> str:
        try:
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
            from memory import world_model_get_state
            
            state = world_model_get_state()
            if not state:
                return "World model is empty (no variables defined)"
            
            output = "**World Model Current State**\n\n"
            for var, val in state.items():
                output += f"  {var}: {val}\n"
            return output
        except Exception as e:
            return f"Error getting world model state: {str(e)}"
    async def _world_model_reset(self, args: Dict) -> str:
        try:
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
            from memory import world_model_reset

            result = world_model_reset()
            return f"✅ {result['status']}"
        except Exception as e:
            return f"Error resetting world model: {str(e)}"
    async def _world_model_record_prediction(self, args: Dict) -> str:
        query = args.get("query", "")
        prediction = args.get("prediction", "")
        horizon = int(args.get("horizon", 10))

        if not query:
            return "Error: query is required"

        try:
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
            from memory import world_model_record_prediction

            result = world_model_record_prediction(query, prediction or None, horizon)
            return (f"✅ Prediction recorded: prediction_id={result['prediction_id']} "
                    f"(use as prediction_ref when promoting via resolved_via_prediction_error)")
        except Exception as e:
            return f"Error recording prediction: {str(e)}"
    async def _world_model_resolve_prediction(self, args: Dict) -> str:
        prediction_id = args.get("prediction_id", "")
        observed_outcome = args.get("observed_outcome", "")
        resolved_in_favor = bool(args.get("resolved_in_favor", False))

        if not prediction_id or not observed_outcome:
            return "Error: prediction_id and observed_outcome are required"

        try:
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
            from memory import world_model_resolve_prediction

            result = world_model_resolve_prediction(prediction_id, observed_outcome, resolved_in_favor)
            verdict = "in favor" if result["resolved_in_favor"] else "against"
            return (f"✅ Prediction {prediction_id} resolved {verdict}. "
                    f"observed_outcome={result['observed_outcome']!r}")
        except Exception as e:
            return f"Error resolving prediction: {str(e)}"
    async def _affective_set_value(self, args: Dict) -> str:
        name = args.get("name", "")
        weight = args.get("weight", 0)
        description = args.get("description", "")

        if not name:
            return "Error: name is required"

        try:
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
            from memory import affective_set_value
            
            result = affective_set_value(name, weight, description)
            return f"✅ Value set: {result['value']} (weight: {result['weight']}) - {result['description']}"
        except Exception as e:
            return f"Error setting affective value: {str(e)}"
    async def _affective_set_emotion(self, args: Dict) -> str:
        name = args.get("name", "")
        intensity = args.get("intensity", 0)
        cause = args.get("cause", "")

        if not name:
            return "Error: name is required"

        try:
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
            from memory import affective_set_emotion
            
            result = affective_set_emotion(name, intensity, cause)
            return f"✅ Emotion set: {result['emotion']} (intensity: {result['intensity']}) - {result['cause']}"
        except Exception as e:
            return f"Error setting affective emotion: {str(e)}"
    async def _affective_add_goal(self, args: Dict) -> str:
        name = args.get("name", "")
        priority = args.get("priority", 0)
        target_state = args.get("target_state", {})

        if not name:
            return "Error: name is required"

        try:
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
            from memory import affective_add_goal
            
            result = affective_add_goal(name, priority, target_state)
            return f"✅ Goal added: {result['goal']} (priority: {result['priority']}) - Target: {result['target_state']}"
        except Exception as e:
            return f"Error adding affective goal: {str(e)}"
    async def _affective_update_preference(self, args: Dict) -> str:
        context = args.get("context", "")
        preference = args.get("preference", "")
        strength = args.get("strength", 0)

        if not context or not preference:
            return "Error: context and preference are required"

        try:
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
            from memory import affective_update_preference
            
            result = affective_update_preference(context, preference, strength)
            return f"✅ Preference updated: {result['context']} -> {result['preference']} = {result['strength']}"
        except Exception as e:
            return f"Error updating affective preference: {str(e)}"
    async def _affective_evaluate(self, args: Dict) -> str:
        situation = args.get("situation", {})

        if not situation:
            return "Error: situation is required"

        try:
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
            from memory import affective_evaluate
            
            result = affective_evaluate(situation)
            output = f"**Affective Evaluation**\n\n"
            output += f"Situation: {situation}\n\n"
            output += f"Value Alignment:\n"
            for val, score in result.get('value_alignment', {}).items():
                output += f"  {val}: {score:.2f}\n"
            output += f"\nGoal Progress:\n"
            for goal, progress in result.get('goal_progress', {}).items():
                output += f"  {goal}: {progress:.2f}\n"
            output += f"\nDominant Emotion: {result.get('dominant_emotion', 'neutral')}"
            return output
        except Exception as e:
            return f"Error evaluating affective state: {str(e)}"
    async def _affective_get_state(self, args: Dict) -> str:
        try:
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
            from memory import affective_get_state
            
            state = affective_get_state()
            output = "**Affective State**\n\n"
            output += f"Values: {state.get('values', {})}\n"
            output += f"Emotions: {state.get('emotions', {})}\n"
            output += f"Goals: {state.get('goals', {})}\n"
            output += f"Preferences: {state.get('preferences', {})}"
            return output
        except Exception as e:
            return f"Error getting affective state: {str(e)}"
