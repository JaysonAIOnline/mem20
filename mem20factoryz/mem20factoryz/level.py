"""Level builder: assemble tiles, entities, objectives into a level."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

from .generator import BSPDungeonGenerator, LootGenerator, TerrainGenerator
from .prng import DeterministicPRNG


@dataclass
class Level:
    """Composable level package."""

    tiles: List[List[int]]
    entities: List[Dict] = field(default_factory=list)
    objectives: List[Dict] = field(default_factory=list)
    spawn: Tuple[int, int] = (0, 0)
    width: int = 0
    height: int = 0
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "tiles": self.tiles,
            "entities": self.entities,
            "objectives": self.objectives,
            "spawn": list(self.spawn),
            "width": self.width,
            "height": self.height,
            "metadata": self.metadata,
        }

    def json(self) -> str:
        return json.dumps(self.to_dict())


class LevelBuilder:
    """Composes generators into a finished level."""

    def __init__(self, config):
        self.config = config

    def build(self) -> Level:
        cfg = self.config
        dungeon = BSPDungeonGenerator().generate(cfg)
        tiles = dungeon["tiles"]
        h, w = len(tiles), len(tiles[0])
        prng = DeterministicPRNG(cfg.seed + 11)

        entities = []
        for i in range(cfg.enemies_per_level):
            entities.append({"type": "enemy", "id": f"e{i}", "kind": prng.choice(["grunt", "brute", "shaman", "stalker"])})
        for i in range(cfg.items_per_level):
            entities.append({"type": "item", "id": f"i{i}", "kind": prng.choice(["health", "mana", "gold", "weapon"])})

        objectives = []
        for i in range(cfg.objectives):
            objectives.append({"id": f"obj{i}", "type": "collection", "target": prng.choice(["enemy", "item"])})

        return Level(
            tiles=tiles,
            entities=entities,
            objectives=objectives,
            spawn=dungeon["spawn"],
            width=w,
            height=h,
            metadata={"seed": cfg.seed, "mode": "single-player", "rooms": len(dungeon["rooms"])},
        )

    def terrain_preview(self) -> List[List[int]]:
        terra = TerrainGenerator().generate(self.config)
        return TerrainGenerator().to_tiles(terra, levels=6)

    def loot_table(self) -> List[Dict]:
        return LootGenerator().generate(self.config)