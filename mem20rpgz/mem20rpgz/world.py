"""World, scenes, NPCs, factions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Faction:
    """A faction with stance tracking."""

    name: str
    disposition: int = 0  # -100 hostile .. +100 allied
    traits: List[str] = field(default_factory=list)

    def shift(self, delta: int) -> int:
        self.disposition = max(-100, min(100, self.disposition + delta))
        return self.disposition

    @property
    def stance(self) -> str:
        if self.disposition <= -60:
            return "hostile"
        if self.disposition <= -20:
            return "unfriendly"
        if self.disposition >= 60:
            return "allied"
        if self.disposition >= 20:
            return "friendly"
        return "neutral"

    def to_dict(self) -> Dict:
        return {"name": self.name, "disposition": self.disposition, "traits": self.traits}


@dataclass
class NPC:
    """Non-player character."""

    name: str
    role: str = "villager"
    faction: str = ""
    dialogue: List[str] = field(default_factory=list)
    shop: List[str] = field(default_factory=list)

    def greet(self) -> str:
        return f"{self.name} ({self.role}) greets you." if self.dialogue else f"{self.name} is silent."

    def to_dict(self) -> Dict:
        return {"name": self.name, "role": self.role, "faction": self.faction, "dialogue": self.dialogue, "shop": self.shop}


@dataclass
class Scene:
    """A location / encounter scene."""

    name: str
    description: str = ""
    region: str = "wilderness"
    npcs: List[NPC] = field(default_factory=list)
    exits: List[str] = field(default_factory=list)
    hazards: List[str] = field(default_factory=list)
    treasure: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "description": self.description,
            "region": self.region,
            "npcs": [n.to_dict() for n in self.npcs],
            "exits": self.exits,
            "hazards": self.hazards,
            "treasure": self.treasure,
        }


class World:
    """Container of factions, NPCs, and scenes."""

    def __init__(self, name: str = "Aethel"):
        self.name = name
        self.factions: Dict[str, Faction] = {}
        self.scenes: Dict[str, Scene] = {}

    def add_faction(self, faction: Faction) -> None:
        self.factions[faction.name] = faction

    def add_scene(self, scene: Scene) -> None:
        self.scenes[scene.name] = scene

    def faction(self, name: str) -> Optional[Faction]:
        return self.factions.get(name)

    def scene(self, name: str) -> Optional[Scene]:
        return self.scenes.get(name)

    def register_npc(self, npc: NPC, scene_name: str) -> bool:
        sc = self.scenes.get(scene_name)
        if sc is None:
            return False
        sc.npcs.append(npc)
        return True

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "factions": [f.to_dict() for f in self.factions.values()],
            "scenes": {name: s.to_dict() for name, s in self.scenes.items()},
        }