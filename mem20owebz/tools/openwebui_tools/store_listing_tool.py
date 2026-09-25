"""
title: Store Listing Pack
author: Jayson
version: 1.0
description: Draft store copy and asset request list from a production package pitch.
"""

from pydantic import BaseModel, Field
import json


class Tools:
    class Valves(BaseModel):
        max_short_chars: int = Field(default=300)

    def __init__(self):
        self.valves = self.Valves()

    def draft_store_listing(
        self,
        title: str,
        pitch: str,
        genre: str,
        platforms: str,
        rating: str = "TBD",
    ) -> str:
        """Draft listing fields. Human must approve before any store upload."""
        short = (pitch or "").strip()
        if len(short) > self.valves.max_short_chars:
            short = short[: self.valves.max_short_chars - 1] + "…"
        plats = [p.strip() for p in platforms.split(",") if p.strip()]
        return json.dumps({
            "title": title,
            "short_description": short,
            "long_description_outline": [
                "Fantasy / what you do",
                "Genre and perspective",
                "Platforms: " + ", ".join(plats),
                "Content rating: " + rating,
                "Known limitations (honest)",
            ],
            "tags": [genre],
            "screenshot_shots": [
                "hero key art",
                "gameplay 1 (core loop)",
                "gameplay 2 (setpiece)",
                "UI/HUD readable",
            ],
            "pipeline": "pipelines/games/store_listing.md",
            "do_not": "Do not create store accounts or upload; this is copy + art list only.",
        }, indent=2)
