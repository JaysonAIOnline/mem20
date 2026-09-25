"""Configuration for mem20autouez."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class AutoUEConfig:
    """Native AutoUE configuration."""
    host: str = "0.0.0.0"
    port: int = 8004
    gateway_url: str = "http://127.0.0.1:4000"
    ue_host: str = "127.0.0.1"
    ue_port: int = 30010
    secrets_home: str = "/opt/mem20/secrets"
    default_level: str = "/Game/Levels/MainLevel"
    asset_root: str = "/Game/Assets"
    enable_blueprint_gen: bool = True
    enable_level_streaming: bool = True

    @classmethod
    def load(cls, path: Optional[str] = None) -> "AutoUEConfig":
        cfg = cls()
        if path and Path(path).exists():
            with open(path, "r") as f:
                data = yaml.safe_load(f) or {}
            for k, v in data.items():
                if hasattr(cfg, k):
                    setattr(cfg, k, v)
        return cfg

    def save(self, path: str) -> None:
        with open(path, "w") as f:
            yaml.safe_dump(self.__dict__, f)


DEFAULT_CONFIG = AutoUEConfig()