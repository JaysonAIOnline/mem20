"""
title: Tight Agent Loop
author: Jayson
version: 1.0
description: Structured multi-step agent loop with explicit plan → act → check → handoff cycles.
"""

from pydantic import BaseModel, Field
from typing import Optional
import json
from datetime import datetime


class Tools:
    class Valves(BaseModel):
        max_steps: int = Field(default=12, description="Max loop iterations")

    def __init__(self):
        self.valves = self.Valves()

    def start_loop(self, goal: str, constraints: str = "", success_criteria: str = "") -> str:
        """
        Start a tight agent loop for a goal.
        :param goal: What must be achieved
        :param constraints: Limits (time, tools, style)
        :param success_criteria: How we know it's done
        """
        return json.dumps({
            "loop_id": datetime.utcnow().strftime("%Y%m%d%H%M%S"),
            "goal": goal,
            "constraints": constraints,
            "success_criteria": success_criteria or "Goal completed with verified outputs",
            "state": "PLAN",
            "steps": [],
            "instruction": (
                "Cycle: PLAN (decompose) → ACT (use tools) → CHECK (verify) → "
                "HANDOFF or ITERATE. Never skip CHECK. Stop when success_criteria met."
            ),
        }, indent=2)

    def plan_step(self, goal: str, known_context: str = "") -> str:
        """Break goal into ordered sub-tasks."""
        return json.dumps({
            "phase": "PLAN",
            "goal": goal,
            "subtasks": [
                {"id": 1, "task": "Clarify unknowns", "status": "pending"},
                {"id": 2, "task": "Gather required assets/info", "status": "pending"},
                {"id": 3, "task": "Execute core work", "status": "pending"},
                {"id": 4, "task": "Self-check against success criteria", "status": "pending"},
                {"id": 5, "task": "Package deliverables", "status": "pending"},
            ],
            "context": known_context,
            "next": "ACT on subtask 1",
        }, indent=2)

    def check_step(self, deliverable_summary: str, success_criteria: str) -> str:
        """
        Verify work before handoff.
        :param deliverable_summary: What was produced
        :param success_criteria: Criteria to judge against
        """
        return json.dumps({
            "phase": "CHECK",
            "deliverable_summary": deliverable_summary,
            "success_criteria": success_criteria,
            "checklist": [
                {"item": "Matches requested goal", "pass": None},
                {"item": "No obvious missing pieces", "pass": None},
                {"item": "Format usable by next stage", "pass": None},
                {"item": "Known risks documented", "pass": None},
            ],
            "instruction": "Fill pass true/false. If any false → ITERATE. If all true → HANDOFF or DONE.",
        }, indent=2)

    def close_loop(self, goal: str, final_artifacts: str, notes: str = "") -> str:
        """Mark loop complete."""
        return json.dumps({
            "phase": "DONE",
            "goal": goal,
            "artifacts": [a.strip() for a in final_artifacts.split(",") if a.strip()],
            "notes": notes,
            "closed_at": datetime.utcnow().isoformat() + "Z",
        }, indent=2)
