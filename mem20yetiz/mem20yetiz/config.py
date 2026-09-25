"""Configuration for mem20yetiz."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class YetiConfig:
    """Native Yeti Claw configuration."""
    host: str = "0.0.0.0"
    port: int = 8005
    gateway_url: str = "http://127.0.0.1:4000"
    secrets_home: str = "/opt/mem20/secrets"
    rig_root: str = "/opt/mem20/yetiz/rigs"
    animation_root: str = "/opt/mem20/yetiz/animations"
    export_formats: list = field(default_factory=lambda: ["gltf", "obj", "bvh", "c3d"])
    enable_retargeting: bool = True
    enable_mocap: bool = True

    @classmethod
    def load(cls, path: Optional[str] = None) -> "YetiConfig":
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


DEFAULT_CONFIG = YetiConfig()