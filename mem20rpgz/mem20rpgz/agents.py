"""Elemental Tetrad multi-agent studio: Narrative, Scene, Gameplay agents.

RPGAgent's core idea: a short story outline is converted into a playable
RPG by specialized agents exchanging structured data. This module implements
that pipeline hermetic-statically (deterministic, seeded) with an optional
live LLM mode via the mem20 gateway.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from .rng import RpgRandom

ELEMENTAL_TETRAD = ("mechanics", "story", "aesthetics", "technology")


@dataclass
class AgentOutput:
    """Structured output exchanged between agents (JSON payload)."""

    agent: str
    artifact: Dict[str, Any]

    def to_dict(self) -> Dict:
        return {"agent": self.agent, "artifact": self.artifact}


class BaseStudioAgent:
    """Base for specialized agents; deterministic unless live_mode."""

    name = "base"

    def __init__(self, seed: int = 0, live_mode: bool = False, gateway_url: str = "http://127.0.0.1:4000"):
        self.seed = seed
        self.live_mode = live_mode
        self.gateway_url = gateway_url

    def run(self, input_artifact: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

    async def _llm(self, prompt: str) -> str:
        import aiohttp

        from .llm import chat_completion

        return await chat_completion(self.gateway_url, prompt, self.seed)

    async def run_async(self, input_artifact: Dict[str, Any]) -> Dict[str, Any]:
        if self.live_mode:
            prompt = self._build_prompt(input_artifact)
            raw = await self._llm(prompt)
            return {"raw": raw, "note": "live_llm_mode"}
        return self.run(input_artifact)

    def _build_prompt(self, input_artifact: Dict[str, Any]) -> str:
        raise NotImplementedError


class NarrativeAgent(BaseStudioAgent):
    """Produces story: logline, acts, beats."""

    name = "narrative"

    HOOKS = ["lost heirloom", "zombie apocalypse", "dragon on the throne", "cursed carnival"]
    SETTINGS = ["misty coastline", "orphanage at night", "hollow mountain", "sunken cathedral"]

    def run(self, input_artifact: Dict[str, Any]) -> Dict[str, Any]:
        rng = RpgRandom(self.seed)
        outline = input_artifact.get("outline", "").strip() or None
        hook = outline or rng.choice(self.HOOKS)
        setting = input_artifact.get("setting") or rng.choice(self.SETTINGS)
        acts = input_artifact.get("acts", 3)
        beats = []
        for i in range(acts):
            beats.append({"act": i + 1, "kind": "setup" if i == 0 else ("climax" if i == acts - 1 else "escalation"), "summary": f"{hook} -- {setting} (act {i + 1})"})
        return {"logline": hook, "setting": setting, "acts": beats, "protagonist": input_artifact.get("protagonist", "the wanderer")}

    def _build_prompt(self, input_artifact: Dict[str, Any]) -> str:
        return f"Write an RPG story outline given: {input_artifact}"


class SceneAgent(BaseStudioAgent):
    """Produces scenes from story beats: locations, NPCs, exits."""

    name = "scene"

    TERRAINS = ["forest", "cave", "village", "castle", "ruin"]

    def run(self, input_artifact: Dict[str, Any]) -> Dict[str, Any]:
        rng = RpgRandom(self.seed + 1)
        story = input_artifact.get("story", {})
        beats = story.get("acts", [])
        scenes = []
        for beat in beats:
            scenes.append({
                "act": beat.get("act", 1),
                "name": f"{beat.get('summary', 'scene').split('--')[0].strip()} {beat.get('act', 1)}",
                "terrain": rng.choice(self.TERRAINS),
                "npcs": [{"name": rng.choice(["Old Merrim", "Sable", "Grimsby", "Lumen"]), "role": rng.choice(["innkeeper", "guard", "sage", "merchant"])}],
                "exits": [f"route {i}" for i in range(1, rng.int(1, 4))],
                "hazards": [rng.choice(["mudslide", "bandits", "wolves", "fog"])],
            })
        return {"scenes": scenes, "story_beats": len(beats)}

    def _build_prompt(self, input_artifact: Dict[str, Any]) -> str:
        return f"Design game scenes from story: {input_artifact}"


class GameplayAgent(BaseStudioAgent):
    """Produces gameplay mechanics from scenes: objectives, encounters, balance."""

    name = "gameplay"

    OBJECTIVES = ["collect relic", "defeat boss", "escort civilian", "light beacon"]
    ENEMY_KINDS = ["goblin", "skeleton", "cultist", "draconian"]

    def run(self, input_artifact: Dict[str, Any]) -> Dict[str, Any]:
        rng = RpgRandom(self.seed + 2)
        scenes = input_artifact.get("scenes", [])
        mechanics = []
        for i, scene in enumerate(scenes):
            mechanics.append({
                "scene": scene.get("name", f"scene {i}"),
                "objective": rng.choice(self.OBJECTIVES),
                "encounter": {"enemy": rng.choice(self.ENEMY_KINDS), "count": rng.int(1, 4)},
                "difficulty": rng.choice(["trivial", "fair", "grueling"]) if i % 2 else "fair",
            })
        return {"mechanics": mechanics, "tetrad_check": all(x in ELEMENTAL_TETRAD for x in ("mechanics", "story", "aesthetics", "technology"))}

    def _build_prompt(self, input_artifact: Dict[str, Any]) -> str:
        return f"Design gameplay mechanics from scenes: {input_artifact}"


class AestheticsAgent(BaseStudioAgent):
    """Aesthetics dimension of the tetrad: palette, tone, render hints."""

    name = "aesthetics"

    PALETTES = ["ember", "mint-null", "midnight gold", "sepia"]
    TONES = ["grim", "whimsical", "heroic", "uncanny"]

    def run(self, input_artifact: Dict[str, Any]) -> Dict[str, Any]:
        rng = RpgRandom(self.seed + 3)
        return {
            "palette": rng.choice(self.PALETTES),
            "tone": rng.choice(self.TONES),
            "guidance": ["high-contrast silhouettes", "diegetic UI", "camera slow-drip"],
        }

    def _build_prompt(self, input_artifact: Dict[str, Any]) -> str:
        return f"Recommend aesthetics for game: {input_artifact}"


class RPGStudio:
    """Orchestrates the agent pipeline (Elemental Tetrad) end-to-end."""

    def __init__(self, seed: int = 0, live_mode: bool = False, gateway_url: str = "http://127.0.0.1:4000"):
        self.seed = seed
        self.narrative = NarrativeAgent(seed, live_mode, gateway_url)
        self.scene = SceneAgent(seed, live_mode, gateway_url)
        self.gameplay = GameplayAgent(seed, live_mode, gateway_url)
        self.aesthetics = AestheticsAgent(seed, live_mode, gateway_url)
        self.history: List[AgentOutput] = []

    def produce(self, outline: str = "") -> Dict[str, Any]:
        """Run pipeline deterministically and return the compiled game design."""
        story = self.narrative.run({"outline": outline})
        scenes = self.scene.run({"story": story})
        mechanics = self.gameplay.run({"scenes": scenes.get("scenes", [])})
        aesthetics = self.aesthetics.run({})
        self.history = [
            AgentOutput("narrative", story),
            AgentOutput("scene", scenes),
            AgentOutput("gameplay", mechanics),
            AgentOutput("aesthetics", aesthetics),
        ]
        return {
            "story": story,
            "scenes": scenes,
            "gameplay": mechanics,
            "aesthetics": aesthetics,
            "tetrad": list(ELEMENTAL_TETRAD),
        }

    async def produce_async(self, outline: str = "") -> Dict[str, Any]:
        """Live-mode pipeline (uses gateway LLM when live_mode set)."""
        story = await self.narrative.run_async({"outline": outline})
        scenes = await self.scene.run_async({"story": story})
        mechanics = await self.gameplay.run_async({"scenes": scenes.get("scenes", [])})
        aesthetics = await self.aesthetics.run_async({})
        return {
            "story": story,
            "scenes": scenes,
            "gameplay": mechanics,
            "aesthetics": aesthetics,
            "tetrad": list(ELEMENTAL_TETRAD),
        }