"""Configuration for mem20gamez."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class GameConfig:
    """Native game AI configuration."""
    host: str = "0.0.0.0"
    port: int = 8007
    gateway_url: str = "http://127.0.0.1:4000"
    secrets_home: str = "/opt/mem20/secrets"
    default_env: str = "CartPole-v1"
    max_episode_steps: int = 1000
    replay_buffer_size: int = 100000
    batch_size: int = 64
    gamma: float = 0.99
    lr: float = 3e-4

    def __post_init__(self) -> None:
        if not self.host:
            raise ValueError("host must not be empty")
        if not 1 <= self.port <= 65535:
            raise ValueError("port must be in [1, 65535]")
        if self.max_episode_steps <= 0 or self.replay_buffer_size <= 0 or self.batch_size <= 0:
            raise ValueError("episode, replay, and batch sizes must be positive")
        if self.batch_size > self.replay_buffer_size:
            raise ValueError("batch_size cannot exceed replay_buffer_size")
        if not 0.0 <= self.gamma <= 1.0:
            raise ValueError("gamma must be in [0, 1]")
        if self.lr <= 0.0:
            raise ValueError("lr must be positive")

    @classmethod
    def load(cls, path: str | None = None) -> GameConfig:
        if path is None:
            return cls()
        config_path = Path(path)
        if not config_path.is_file():
            raise FileNotFoundError(config_path)
        with config_path.open("r", encoding="utf-8") as stream:
            data = yaml.safe_load(stream) or {}
        if not isinstance(data, dict):
            raise TypeError("configuration root must be a mapping")
        known_fields = {field.name for field in cls.__dataclass_fields__.values()}
        unknown = sorted(set(data) - known_fields)
        if unknown:
            raise ValueError(f"unknown configuration fields: {', '.join(unknown)}")
        return cls(**data)

    def save(self, path: str) -> None:
        with open(path, "w") as f:
            yaml.safe_dump(self.__dict__, f)


DEFAULT_CONFIG = GameConfig()