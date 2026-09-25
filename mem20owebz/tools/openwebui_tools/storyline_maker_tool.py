"""
title: Storyline Maker
author: Jayson
version: 1.0
description: Create structured storylines with characters, acts, scenes, and beats.
"""

from pydantic import BaseModel, Field
from typing import Optional
import json


class Tools:
    class Valves(BaseModel):
        default_genre: str = Field(default="sci-fi", description="Default genre if none given")

    def __init__(self):
        self.valves = self.Valves()

    def create_storyline(
        self,
        premise: str,
        genre: Optional[str] = None,
        length: str = "feature",
        tone: str = "dramatic",
        num_acts: int = 3,
    ) -> str:
        """
        Build a structured storyline from a premise.
        :param premise: Core idea or logline
        :param genre: Genre (sci-fi, fantasy, thriller, comedy, etc.)
        :param length: short, feature, series
        :param tone: dramatic, dark, hopeful, comedic, etc.
        :param num_acts: Number of acts (usually 3)
        """
        genre = genre or self.valves.default_genre

        structure = {
            "title_suggestions": [
                f"Working title based on: {premise[:40]}...",
                "Alternative title 2",
                "Alternative title 3",
            ],
            "logline": premise,
            "genre": genre,
            "tone": tone,
            "format": length,
            "characters": [
                {
                    "name": "Protagonist",
                    "role": "Main character",
                    "want": "What they consciously want",
                    "need": "What they actually need",
                    "arc": "How they change",
                },
                {
                    "name": "Antagonist",
                    "role": "Opposition",
                    "goal": "What they are trying to achieve",
                    "method": "How they oppose the hero",
                },
                {
                    "name": "Ally",
                    "role": "Supporting character",
                    "function": "Helps or complicates the journey",
                },
            ],
            "acts": [],
        }

        if num_acts >= 1:
            structure["acts"].append({
                "act": 1,
                "name": "Setup",
                "purpose": "Introduce world, character, and inciting incident",
                "key_beats": [
                    "Opening image",
                    "Introduce protagonist in their normal world",
                    "Inciting incident",
                    "Debate / refusal",
                    "Crossing the threshold",
                ],
                "scenes": [
                    {"scene": 1, "summary": "Open on the ordinary world"},
                    {"scene": 2, "summary": "Inciting incident hits"},
                    {"scene": 3, "summary": "Protagonist commits to the journey"},
                ],
            })
        if num_acts >= 2:
            structure["acts"].append({
                "act": 2,
                "name": "Confrontation",
                "purpose": "Rising action, obstacles, midpoint shift",
                "key_beats": [
                    "Tests, allies, enemies",
                    "Midpoint (false victory or false defeat)",
                    "Complications and higher stakes",
                    "All-is-lost moment",
                    "Dark night of the soul",
                ],
                "scenes": [
                    {"scene": 1, "summary": "First major obstacle"},
                    {"scene": 2, "summary": "Midpoint revelation"},
                    {"scene": 3, "summary": "Lowest point"},
                ],
            })
        if num_acts >= 3:
            structure["acts"].append({
                "act": 3,
                "name": "Resolution",
                "purpose": "Climax and new normal",
                "key_beats": [
                    "Gathering the team / final plan",
                    "Climax confrontation",
                    "Resolution of character arc",
                    "Final image",
                ],
                "scenes": [
                    {"scene": 1, "summary": "Final preparation"},
                    {"scene": 2, "summary": "Climax"},
                    {"scene": 3, "summary": "New equilibrium"},
                ],
            })

        structure["theme"] = "What the story is really about (fill in)"
        structure["next_steps"] = [
            "Expand each scene into a full beat sheet",
            "Write character bios",
            "Generate visual concept art for key scenes",
            "Turn acts into script pages or shot lists",
        ]

        return json.dumps(structure, indent=2)

    def expand_scene(self, scene_summary: str, characters: str = "", mood: str = "") -> str:
        """
        Expand a single scene into a detailed beat outline.
        :param scene_summary: Short description of the scene
        :param characters: Who is in the scene
        :param mood: Emotional tone
        """
        return json.dumps({
            "scene_summary": scene_summary,
            "characters": characters or "Protagonist + relevant others",
            "mood": mood or "match overall tone",
            "beats": [
                "Entry / establishing",
                "Conflict or revelation",
                "Turning point",
                "Exit / hook to next scene",
            ],
            "visual_notes": "Key images, lighting, camera ideas",
            "dialogue_goals": "What must be said or left unsaid",
        }, indent=2)
