"""Configuration for mem20rpgz."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

import yaml


@dataclass
class RPGConfig:
    """RPGAgent / story-to-play configuration."""

    seed: int = 20260917
    gateway_url: str = "http://127.0.0.1:4000"
    port: int = 8017
    player_level: int = 1
    party_size: int = 4
    initial_gold: int = 100
    inventory_capacity: int = 24
    quest_count: int = 3
    scenes_per_story: int = 6
    story_hooks: int = 3
    section: str = "rpg"
    extra: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path) -> "RPGConfig":
        p = Path(path)
        data = yaml.safe_load(p.read_text()) or {}
        section = data.pop("section", "")
        data.update(data.pop(section, {}) or {})
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known}, extra={k: v for k, v in data.items() if k not in known and k != "section"})

    def save(self, path: str | Path) -> None:
        Path(path).write_text(yaml.safe_dump(self.to_dict()))

    def to_dict(self) -> Dict[str, Any]:
        d = {k: v for k, v in self.__dict__.items() if k != "extra"}
        d.update(self.extra)
        return d