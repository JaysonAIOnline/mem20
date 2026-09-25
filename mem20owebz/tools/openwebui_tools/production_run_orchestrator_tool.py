"""
title: Production Run Orchestrator
author: Jayson
version: 1.0
description: Force a Production Package through the full idea→game pipeline with gates (design → assets → assembly → polish → installable).
"""

from pydantic import BaseModel, Field
from typing import Optional
import json
from datetime import datetime


# Ordered pipeline spine — do not skip gates
STAGES = [
    {
        "id": 0,
        "name": "PACKAGE_LOCK",
        "goal": "Confirm Production Package [HUMAN] sections are signed, primary ENGINE is chosen, and slice is clear",
        "tools": ["read package", "ask human if unsigned"],
        "qa": "Human sign-off present + primary engine selected (Godot/Unity/Unreal/custom)",
        "next_on_pass": 1,
    },
    {
        "id": 1,
        "name": "DESIGN_SPINE",
        "goal": "World/systems/quests/narrative for vertical slice only",
        "tools": ["rpg_orchestrator", "storyline_maker", "genre pipeline", "tight_loop"],
        "qa": "qa_inspect design + narrative + systems",
        "next_on_pass": 2,
    },
    {
        "id": 2,
        "name": "SPACES_UI_VR",
        "goal": "Levels/tracks, UI specs, VR comfort if in scope",
        "tools": ["text_to_level", "text_image_to_ui", "text_to_vr"],
        "qa": "qa_inspect level + ui (+ export if VR)",
        "next_on_pass": 3,
    },
    {
        "id": 3,
        "name": "ASSET_PRODUCTION",
        "goal": "Generate P0 art/audio into _incoming, ID, manifest, validate",
        "tools": ["text_image_to_3d", "3d_screenshots", "audio_video_gen", "asset_assembly intake"],
        "qa": "qa_inspect 3d_asset + audio; all P0 validated",
        "next_on_pass": 4,
    },
    {
        "id": 4,
        "name": "ASSEMBLY",
        "goal": "Integrate validated assets, build slice scene, no loose files",
        "tools": ["asset_assembly integrate/scene", "unity/blender helpers"],
        "qa": "qa_inspect build; cold boot critical path",
        "next_on_pass": 5,
    },
    {
        "id": 5,
        "name": "FINAL_POLISH",
        "goal": "Fidelity ≥ 94% to package, zero Criticals",
        "tools": ["final_polish_team", "tight_loop rework"],
        "qa": "polish_round_summary + qa_gate ALLOW",
        "next_on_pass": 6,
    },
    {
        "id": 6,
        "name": "RELEASE_PACKAGE",
        "goal": "Platform builds + installable artifact + README_PLAYER",
        "tools": ["asset_assembly build/release", "export_targets"],
        "qa": "qa_inspect export + human cold playtest",
        "next_on_pass": 7,
    },
    {
        "id": 7,
        "name": "DONE",
        "goal": "Idea→game complete",
        "tools": [],
        "qa": "All gates green",
        "next_on_pass": None,
    },
]


class Tools:
    class Valves(BaseModel):
        fidelity_target: float = Field(default=0.94)
        supervision: str = Field(
            default="every_handoff",
            description="every_handoff | end_of_stage | autonomous_with_qa",
        )

    def __init__(self):
        self.valves = self.Valves()

    def start_production_run(
        self,
        project_name: str,
        package_path_or_summary: str,
        genre: str = "RPG",
        platforms: str = "Windows",
    ) -> str:
        """
        Begin a full production run from a Production Package (path, paste, or summary).
        :param project_name: Project folder name
        :param package_path_or_summary: Path to PRODUCTION_PACKAGE.md or pasted core intent
        :param genre: Racing | FPS | TPS | Adventure | OpenWorld | RPG
        :param platforms: Comma-separated export targets
        """
        return json.dumps({
            "run_id": datetime.utcnow().strftime("%Y%m%d%H%M%S"),
            "project_name": project_name,
            "package_ref": package_path_or_summary[:2000],
            "genre": genre,
            "platforms": [p.strip() for p in platforms.split(",") if p.strip()],
            "supervision": self.valves.supervision,
            "fidelity_target": self.valves.fidelity_target,
            "current_stage_id": 0,
            "stages": STAGES,
            "status": "RUNNING",
            "instruction_for_jayson": (
                "You MUST execute stages in order. "
                "At each stage: (1) PLAN with tight loop, (2) ACT using listed tools/pipelines, "
                "(3) CHECK, (4) run listed QA, (5) call production_run_advance only on PASS. "
                "Do not skip to assets before design PASS. Do not build from _incoming. "
                "Do not claim DONE without Stage 6 release artifacts + human playtest note."
            ),
            "first_action": "Execute Stage 0 PACKAGE_LOCK — verify human sign-off, primary engine choice (§1.6 / §11.1), and vertical slice clarity.",
        }, indent=2)

    def production_run_status(
        self,
        project_name: str,
        current_stage_id: int,
        stage_notes: str = "",
        open_blockers: str = "",
    ) -> str:
        """
        Report where the run is and what to do next.
        :param current_stage_id: 0-7
        :param stage_notes: Progress summary
        :param open_blockers: Comma-separated blockers
        """
        stage = next((s for s in STAGES if s["id"] == current_stage_id), STAGES[0])
        blockers = [b.strip() for b in open_blockers.split(",") if b.strip()]
        return json.dumps({
            "project_name": project_name,
            "current_stage": stage,
            "notes": stage_notes,
            "blockers": blockers,
            "can_advance": len(blockers) == 0,
            "next_stage_id": stage.get("next_on_pass"),
            "reminder": "QA must PASS before production_run_advance.",
        }, indent=2)

    def production_run_advance(
        self,
        project_name: str,
        from_stage_id: int,
        qa_verdict: str,
        evidence: str,
    ) -> str:
        """
        Advance to the next stage only if QA passed.
        :param from_stage_id: Stage you are leaving
        :param qa_verdict: PASS | PASS_WITH_NOTES | FAIL
        :param evidence: Short proof (what was checked)
        """
        verdict = (qa_verdict or "").upper().strip()
        stage = next((s for s in STAGES if s["id"] == from_stage_id), None)
        if not stage:
            return json.dumps({"error": "invalid stage id"})
        if verdict not in ("PASS", "PASS_WITH_NOTES"):
            return json.dumps({
                "advanced": False,
                "reason": "QA did not pass",
                "qa_verdict": verdict,
                "stay_on_stage": from_stage_id,
                "action": "Fix blockers, re-run QA, then advance again",
            }, indent=2)
        nxt = stage.get("next_on_pass")
        next_stage = next((s for s in STAGES if s["id"] == nxt), None)
        return json.dumps({
            "advanced": True,
            "from": stage["name"],
            "to": next_stage["name"] if next_stage else "DONE",
            "to_stage_id": nxt,
            "evidence": evidence,
            "instruction": (
                f"Begin stage {nxt}: {next_stage['name']}. Goal: {next_stage['goal']}. "
                f"Tools: {', '.join(next_stage['tools']) or 'n/a'}. QA: {next_stage['qa']}."
            ) if next_stage else "Production run complete. Idea→game achieved.",
        }, indent=2)

    def production_run_playbook(self) -> str:
        """Return the full forced playbook for Jayson."""
        return json.dumps({
            "title": "Forced production run playbook",
            "doc_refs": [
                "PRODUCTION_PACKAGE_TEMPLATE.md",
                "FIRST_GAME_WALKTHROUGH.md",
                "pipelines/games/asset_assembly.md",
                "pipelines/games/final_polish.md",
                "pipelines/games/genre_pipelines.md",
                "pipelines/games/export_targets.md",
            ],
            "stages": STAGES,
            "hard_rules": [
                "Never skip stages",
                "Never integrate from _incoming without validate",
                "Never ALLOW delivery under fidelity target",
                "Human owns package [HUMAN] sections and final playtest",
                "Manifest is law for shipped assets",
            ],
        }, indent=2)
