"""
title: QA Agents Suite
author: Jayson
version: 1.0
description: Strong QA agents that inspect deliverables before delivery (design, 3D, narrative, systems, exports, build).
"""

from pydantic import BaseModel, Field
from typing import Optional
import json


class Tools:
    class Valves(BaseModel):
        strictness: str = Field(default="high", description="low | medium | high")

    def __init__(self):
        self.valves = self.Valves()

    def qa_inspect(self, deliverable_type: str, content_summary: str, acceptance_criteria: str = "") -> str:
        """
        Run a QA inspection on a deliverable.
        :param deliverable_type: narrative | systems | 3d_asset | quest | level | build | export | audio | general
        :param content_summary: What is being inspected
        :param acceptance_criteria: Optional explicit criteria
        """
        common = [
            "Completeness vs request",
            "Internal consistency",
            "Clear naming / structure",
            "Known risks or TODOs listed",
            "Ready for next pipeline stage",
        ]
        specific = {
            "narrative": ["Tone consistency", "Character voice distinct", "No plot holes in covered scope"],
            "systems": ["Numbers tunable", "Player decisions meaningful", "Edge cases considered"],
            "3d_asset": ["Centered origin", "Reasonable scale", "Clean enough topology", "Materials assigned", "Export format correct"],
            "quest": ["Clear goal", "Failure states", "Reward makes sense", "No soft-lock paths"],
            "level": ["Traversal readable", "Combat spaces fair", "Landmarks present"],
            "build": ["Boots to playable state", "Critical path completable", "Performance budget noted"],
            "export": ["Target platform constraints respected", "Resolution/UI scale OK", "Input mapping valid", "Build size noted"],
            "audio": ["Voice clarity", "Levels not clipping", "Music not masking dialogue"],
            "general": ["Usable by another person without explanation"],
        }
        checks = common + specific.get(deliverable_type, specific["general"])
        return json.dumps({
            "qa_agent": f"QA_{deliverable_type.upper()}",
            "strictness": self.valves.strictness,
            "deliverable_type": deliverable_type,
            "summary": content_summary,
            "acceptance_criteria": acceptance_criteria,
            "checks": [{"item": c, "result": None, "notes": ""} for c in checks],
            "verdict_options": ["PASS", "PASS_WITH_NOTES", "FAIL_NEEDS_REWORK"],
            "instruction": "Evaluate each check. Final verdict required before delivery handoff.",
        }, indent=2)

    def qa_gate(self, project_name: str, stage: str, open_failures: str = "") -> str:
        """
        Final delivery gate — block or allow handoff to 'done'.
        :param project_name: Project name
        :param stage: Stage being gated
        :param open_failures: Comma-separated remaining failures
        """
        failures = [f.strip() for f in open_failures.split(",") if f.strip()]
        allowed = len(failures) == 0
        return json.dumps({
            "gate": "DELIVERY_QA",
            "project": project_name,
            "stage": stage,
            "open_failures": failures,
            "verdict": "ALLOW_DELIVERY" if allowed else "BLOCK_DELIVERY",
            "message": "All clear." if allowed else "Fix failures before delivery.",
        }, indent=2)

    def qa_agent_prompt(self, specialty: str) -> str:
        """
        System prompt for a QA specialist agent.
        :param specialty: design | narrative | systems | art_3d | audio | export | build
        """
        prompts = {
            "design": "You are QA Design. Judge clarity, player intent, and whether the design is implementable.",
            "narrative": "You are QA Narrative. Judge continuity, voice, pacing, and lore consistency.",
            "systems": "You are QA Systems. Judge balance levers, exploit risks, and clarity of rules.",
            "art_3d": "You are QA Art/3D. Judge silhouette, scale, topology hygiene, and export readiness.",
            "audio": "You are QA Audio. Judge clarity, mix headroom, and emotional fit.",
            "export": "You are QA Export. Judge platform constraints, input, resolution, and performance assumptions.",
            "build": "You are QA Build. Judge whether a stranger can run the critical path without hand-holding.",
        }
        base = prompts.get(specialty, "You are a strict QA agent. Prefer concrete failures over vague opinions.")
        return base + " Always produce a PASS / PASS_WITH_NOTES / FAIL verdict with a short fix list."
