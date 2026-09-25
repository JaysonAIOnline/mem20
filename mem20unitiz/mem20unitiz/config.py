"""YAML-backed training defaults for mem20unitiz."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import yaml


@dataclass
class MLConfig:
    default_trainer: str = "ppo"
    max_steps: int = 20000
    batch_size: int = 64
    buffer_size: int = 4096
    learning_rate: float = 0.01
    gamma: float = 0.99
    gae_lambda: float = 0.95
    num_epochs: int = 2
    save_freq: int = 1000
    log_freq: int = 100
    seed: int = 42
    hidden_units: int = 16
    num_layers: int = 1

    def __post_init__(self) -> None:
        if self.default_trainer not in {"ppo", "dqn", "sac", "poca"}:
            raise ValueError("default_trainer must be ppo, dqn, sac, or poca")
        for name in ("max_steps", "batch_size", "buffer_size", "num_epochs"):
            if int(getattr(self, name)) < 1:
                raise ValueError(f"{name} must be positive")
        if self.learning_rate <= 0 or not 0 <= self.gamma <= 1 or not 0 <= self.gae_lambda <= 1:
            raise ValueError("invalid learning_rate, gamma, or gae_lambda")

    @classmethod
    def load(cls, path: str | None = None) -> MLConfig:
        """Load a YAML mapping and reject unknown fields."""
        if path is None:
            return cls()
        source = Path(path)
        if not source.exists():
            raise FileNotFoundError(source)
        with source.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        if not isinstance(data, dict):
            raise TypeError("configuration root must be a mapping")
        valid = {field.name for field in cls.__dataclass_fields__.values()}
        unknown = set(data) - valid
        if unknown:
            raise ValueError(f"unknown configuration fields: {sorted(unknown)}")
        return cls(**data)

    def save(self, path: str) -> None:
        """Write the complete configuration as YAML."""
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(asdict(self), handle, sort_keys=False)


DEFAULT_CONFIG = MLConfig()
