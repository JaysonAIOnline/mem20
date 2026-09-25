"""Configuration for mem20agentz_sdk."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class AgentSDKConfig:
    """Native agent SDK configuration."""
    host: str = "0.0.0.0"
    port: int = 8001
    gateway_url: str = "http://127.0.0.1:4000"
    secrets_home: str = "/opt/mem20/secrets"
    max_turns: int = 10
    default_model: str = "fast"
    enable_tracing: bool = True
    enable_guardrails: bool = True
    enable_computer: bool = False
    enable_web_search: bool = False
    enable_file_search: bool = False

    @classmethod
    def load(cls, path: Optional[str] = None) -> "AgentSDKConfig":
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


DEFAULT_CONFIG = AgentSDKConfig()