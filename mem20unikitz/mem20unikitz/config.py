"""Configuration for mem20unikitz."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, Any

import yaml


@dataclass
class UniKitConfig:
    """Native UniKit AI configuration."""
    host: str = "0.0.0.0"
    port: int = 8008
    gateway_url: str = "http://127.0.0.1:4000"
    secrets_home: str = "/opt/mem20/secrets"
    default_bt_path: str = "/opt/mem20/unikitz/behavior_trees"
    default_goap_path: str = "/opt/mem20/unikitz/goap"
    blackboard_path: str = "/opt/mem20/unikitz/blackboard"
    enable_bt: bool = True
    enable_goap: bool = True
    enable_utility: bool = True
    enable_navigation: bool = True
    enable_perception: bool = True

    @classmethod
    def load(cls, path: Optional[str] = None) -> "UniKitConfig":
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


DEFAULT_CONFIG = UniKitConfig()