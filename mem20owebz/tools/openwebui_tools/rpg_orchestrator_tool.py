"""
title: RPG Game Orchestrator
author: Jayson
version: 1.0
description: Orchestrate an RPG through staged pipelines and agent handoffs (world, quests, systems, narrative, art, playtest).
"""

from pydantic import BaseModel, Field
from typing import Optional, List
import json
from datetime import datetime


class Tools:
    class Valves(BaseModel):
        default_genre: str = Field(default="dark fantasy", description="Default RPG genre")
        default_perspective: str = Field(default="third-person", description="isometric | first-person | third-person | JRPG")

    def __init__(self):
        self.valves = self.Valves()
        self._state = {
            "project_name": None,
            "stage": "init",
            "artifacts": {},
            "handoff_log": [],
        }

    def start_rpg_project(
        self,
        project_name: str,
        premise: str,
        genre: Optional[str] = None,
        perspective: Optional[str] = None,
        target_platforms: str = "PC",
    ) -> str:
        """
        Start a new RPG project and return the master pipeline + first handoff.
        :param project_name: Name of the game
        :param premise: High-level concept
        :param genre: Fantasy, sci-fi, post-apoc, etc.
        :param perspective: Camera / combat style
        :param target_platforms: PC, console, mobile, etc.
        """
        genre = genre or self.valves.default_genre
        perspective = perspective or self.valves.default_perspective

        pipeline = {
            "project_name": project_name,
            "premise": premise,
            "genre": genre,
            "perspective": perspective,
            "platforms": target_platforms,
            "created_at": datetime.utcnow().isoformat() + "Z",
            "stages": [
                {
                    "id": 1,
                    "name": "World Bible",
                    "agent": "WorldBuilder",
                    "goal": "Races, factions, history, map regions, tone",
                    "outputs": ["world_bible.md", "faction_sheet.json", "region_list.json"],
                    "handoff_to": "QuestDesigner",
                },
                {
                    "id": 2,
                    "name": "Core Loop & Systems",
                    "agent": "SystemsDesigner",
                    "goal": "Combat, progression, economy, skills, death penalty",
                    "outputs": ["systems_design.md", "progression_table.json"],
                    "handoff_to": "QuestDesigner",
                },
                {
                    "id": 3,
                    "name": "Main Quest & Side Content",
                    "agent": "QuestDesigner",
                    "goal": "Main story arc, key NPCs, side quests, pacing",
                    "outputs": ["main_quest.md", "side_quests.json", "npc_roster.json"],
                    "handoff_to": "NarrativeWriter",
                },
                {
                    "id": 4,
                    "name": "Narrative & Dialogue",
                    "agent": "NarrativeWriter",
                    "goal": "Dialogue tone, key scenes, item descriptions, codex",
                    "outputs": ["dialogue_style_guide.md", "key_scenes.md"],
                    "handoff_to": "ArtDirector",
                },
                {
                    "id": 5,
                    "name": "Art & Audio Direction",
                    "agent": "ArtDirector",
                    "goal": "Visual pillars, character silhouettes, UI mood, music direction",
                    "outputs": ["art_bible.md", "audio_direction.md"],
                    "handoff_to": "TechLead",
                },
                {
                    "id": 6,
                    "name": "Tech & Implementation Plan",
                    "agent": "TechLead",
                    "goal": "Engine choice, scene structure, save system, tools needed",
                    "outputs": ["tech_plan.md", "milestone_roadmap.json"],
                    "handoff_to": "PlaytestLead",
                },
                {
                    "id": 7,
                    "name": "Playtest & Iteration",
                    "agent": "PlaytestLead",
                    "goal": "Test plans, balance notes, fun blockers, next iteration goals",
                    "outputs": ["playtest_report.md", "iteration_backlog.json"],
                    "handoff_to": "WorldBuilder",  # loop back for expansions
                },
            ],
            "current_stage_id": 1,
            "status": "ready",
        }

        self._state["project_name"] = project_name
        self._state["stage"] = "World Bible"
        self._state["artifacts"] = pipeline

        first_handoff = self._format_handoff(
            from_agent="Orchestrator",
            to_agent="WorldBuilder",
            stage="World Bible",
            context=f"New project '{project_name}'. Premise: {premise}. Genre: {genre}. Build the world bible first.",
            expected_outputs=["world_bible.md", "faction_sheet.json", "region_list.json"],
        )

        return json.dumps({"pipeline": pipeline, "first_handoff": first_handoff}, indent=2)

    def handoff(
        self,
        from_agent: str,
        to_agent: str,
        stage: str,
        summary: str,
        artifacts_produced: str = "",
        blockers: str = "",
        next_focus: str = "",
    ) -> str:
        """
        Record a handoff between agents and prepare the next agent's brief.
        :param from_agent: Who is finishing
        :param to_agent: Who receives the work
        :param stage: Current stage name
        :param summary: What was accomplished
        :param artifacts_produced: List of files / docs created
        :param blockers: Open problems
        :param next_focus: What the next agent should prioritize
        """
        entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "from": from_agent,
            "to": to_agent,
            "stage": stage,
            "summary": summary,
            "artifacts": [a.strip() for a in artifacts_produced.split(",") if a.strip()],
            "blockers": blockers,
            "next_focus": next_focus,
        }
        self._state["handoff_log"].append(entry)
        self._state["stage"] = stage

        brief = self._format_handoff(
            from_agent=from_agent,
            to_agent=to_agent,
            stage=stage,
            context=summary,
            expected_outputs=[],
            blockers=blockers,
            next_focus=next_focus,
            artifacts=entry["artifacts"],
        )
        return json.dumps({"handoff_recorded": entry, "next_agent_brief": brief}, indent=2)

    def get_pipeline_status(self, project_name: str = "") -> str:
        """
        Return current RPG pipeline status and handoff history.
        :param project_name: Optional filter
        """
        return json.dumps({
            "project": self._state.get("project_name") or project_name or "unknown",
            "current_stage": self._state.get("stage"),
            "handoff_count": len(self._state.get("handoff_log", [])),
            "recent_handoffs": self._state.get("handoff_log", [])[-5:],
            "tip": "Use start_rpg_project → work stage → handoff → repeat. Pair with Storyline Maker and 3D/Audio tools.",
        }, indent=2)

    def agent_prompt(self, agent_role: str, project_context: str = "") -> str:
        """
        Generate a strong system prompt for a specialist RPG agent.
        :param agent_role: WorldBuilder | SystemsDesigner | QuestDesigner | NarrativeWriter | ArtDirector | TechLead | PlaytestLead
        :param project_context: Short project summary
        """
        prompts = {
            "WorldBuilder": "You are the WorldBuilder. Create coherent cultures, geography, history, and factions. Prefer concrete, playable details over pure lore dumps.",
            "SystemsDesigner": "You are the SystemsDesigner. Design combat, progression, economy, and skills that create interesting decisions. Keep numbers simple and tunable.",
            "QuestDesigner": "You are the QuestDesigner. Structure main and side quests with clear goals, twists, and player agency. Avoid fetch-quest spam.",
            "NarrativeWriter": "You are the NarrativeWriter. Write sharp dialogue, item descriptions, and key scenes that match the established tone.",
            "ArtDirector": "You are the ArtDirector. Define visual pillars, silhouette rules, color scripts, and audio mood so artists and generators stay consistent.",
            "TechLead": "You are the TechLead. Turn designs into an implementation plan (scenes, data, save system, tools). Prefer shipping a vertical slice.",
            "PlaytestLead": "You are the PlaytestLead. Find fun blockers, pacing issues, and balance problems. Propose the smallest changes that improve feel.",
        }
        base = prompts.get(agent_role, f"You are the {agent_role} for this RPG project.")
        ctx = f"\n\nProject context:\n{project_context}" if project_context else ""
        return base + ctx + "\n\nWhen you finish a chunk of work, call the RPG Orchestrator handoff tool to pass cleanly to the next agent."

    def _format_handoff(self, from_agent, to_agent, stage, context, expected_outputs=None, blockers="", next_focus="", artifacts=None):
        return {
            "from": from_agent,
            "to": to_agent,
            "stage": stage,
            "context": context,
            "artifacts_so_far": artifacts or [],
            "expected_outputs": expected_outputs or [],
            "blockers": blockers,
            "next_focus": next_focus or "Continue the current stage goals",
            "instruction": f"You are now {to_agent}. Read the context and artifacts, do the next piece of work, then hand off again.",
        }
