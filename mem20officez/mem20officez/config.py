"""Configuration for mem20officez native office."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

HERE = Path(__file__).parent.parent
HARVEST = HERE / "src_harvest"
BUILD_DIR = HERE / "build"
STATIC_DIR = BUILD_DIR / ".next" / "server" / "app" if (BUILD_DIR / ".next").exists() else HARVEST / ".next" / "server" / "app"
PUBLIC_DIR = HARVEST / "public"


@dataclass
class OfficeConfig:
    """Native office configuration."""
    host: str = "0.0.0.0"
    port: int = 3000
    gateway_url: str = "http://127.0.0.1:4000"
    secrets_home: str = "/opt/mem20/secrets"
    harvest_root: Path = HARVEST
    build_dir: Path = BUILD_DIR
    static_dirs: list[Path] = field(default_factory=lambda: [PUBLIC_DIR])
    enable_phaser: bool = True
    enable_wellness: bool = True
    enable_dashboard: bool = True

    @classmethod
    def load(cls, path: Optional[str] = None) -> "OfficeConfig":
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


DEFAULT_CONFIG = OfficeConfig()