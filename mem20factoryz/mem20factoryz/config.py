"""Configuration for mem20factoryz."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


@dataclass
class FactoryConfig:
    """GameFactory-3A configuration."""

    seed: int = 20260910
    gateway_url: str = "http://127.0.0.1:4000"
    port: int = 8016
    width: int = 64
    height: int = 64
    tile_count: int = 16
    enemies_per_level: int = 6
    items_per_level: int = 8
    asset_resolution: int = 32
    narrative_segments: int = 12
    max_playtest_steps: int = 500
    objectives: int = 3
    section: str = "factory"
    extra: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path) -> "FactoryConfig":
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