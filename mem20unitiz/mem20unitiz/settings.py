"""Trainer and network settings with explicit supported defaults."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class TrainerType(str, Enum):
    PPO = "ppo"
    DQN = "dqn"
    SAC = "sac"
    POCA = "poca"


class NetworkType(str, Enum):
    SIMPLE = "simple"


@dataclass
class NetworkSettings:
    network_type: NetworkType = NetworkType.SIMPLE
    hidden_units: int = 16
    num_layers: int = 1
    learning_rate: float = 0.01
    seed: int | None = None

    def __post_init__(self) -> None:
        if self.network_type != NetworkType.SIMPLE and self.network_type != "simple":
            raise ValueError("only the implemented simple network is supported")
        self.network_type = NetworkType.SIMPLE
        if self.hidden_units < 1 or self.num_layers < 1:
            raise ValueError("network dimensions must be positive")
        if self.learning_rate <= 0:
            raise ValueError("network learning_rate must be positive")


@dataclass
class TrainerSettings:
    trainer_type: TrainerType = TrainerType.PPO
    hyperparameters: dict = field(default_factory=dict)
    network_settings: NetworkSettings = field(default_factory=NetworkSettings)
    reward_signals: dict = field(default_factory=dict)
    max_steps: int = 20000
    batch_size: int = 64
    buffer_size: int = 4096
    learning_rate: float = 0.01
    gamma: float = 0.99
    gae_lambda: float = 0.95
    num_epochs: int = 2
    epsilon: float = 0.2
    save_freq: int = 1000
    log_freq: int = 100
    time_horizon: int = 64
    summary_freq: int = 1000
    threaded: bool = False
    init_path: str | None = None
    load: bool = False
    seed: int = 42

    def __post_init__(self) -> None:
        if self.trainer_type == "ppo":
            self.trainer_type = TrainerType.PPO
        elif self.trainer_type == "dqn":
            self.trainer_type = TrainerType.DQN
        elif self.trainer_type == "sac":
            self.trainer_type = TrainerType.SAC
        elif self.trainer_type == "poca":
            self.trainer_type = TrainerType.POCA
        if self.max_steps < 1 or self.batch_size < 1 or self.buffer_size < 1:
            raise ValueError("training sizes must be positive")
        if not 0 <= self.gamma <= 1 or not 0 <= self.gae_lambda <= 1:
            raise ValueError("gamma and gae_lambda must be in [0, 1]")
        if self.learning_rate <= 0 or self.num_epochs < 1:
            raise ValueError("learning_rate and num_epochs must be positive")


@dataclass
class PPOSettings(TrainerSettings):
    trainer_type: TrainerType = TrainerType.PPO
    beta: float = 0.01
    value_coefficient: float = 0.5
    clip_epsilon: float = 0.2
    clear_after_update: bool = True


@dataclass
class DQNSettings(TrainerSettings):
    trainer_type: TrainerType = TrainerType.DQN
    epsilon_init: float = 1.0
    epsilon_min: float = 0.05
    epsilon_decay: float = 0.99
    target_update_freq: int = 100
    tau: float = 1.0
    buffer_alpha: float = 0.6
    buffer_beta: float = 0.4
    prioritized: bool = True


@dataclass
class SACSettings(TrainerSettings):
    trainer_type: TrainerType = TrainerType.SAC
    tau: float = 0.01
    init_entcoef: float = 1.0
    target_entropy: float | None = None
    update_after: int = 32


@dataclass
class POCASettings(TrainerSettings):
    trainer_type: TrainerType = TrainerType.POCA
    learning_rate: float = 0.001
    beta: float = 0.01
    value_coefficient: float = 0.5
    clip_epsilon: float = 0.2
    hidden_units: int = 16
    clear_after_update: bool = True


@dataclass
class TorchSettings:
    """Compatibility settings for callers that inspect runtime capabilities."""

    device: str = "cpu"
    dtype: str = "float32"
    seed: int = 42
    num_threads: int = 1


def get_default_settings(trainer_type: TrainerType | str) -> TrainerSettings:
    """Return a fresh settings object for one implemented trainer."""
    if isinstance(trainer_type, str):
        try:
            trainer_type = TrainerType(trainer_type)
        except ValueError as error:
            raise ValueError(f"unknown trainer type: {trainer_type}") from error
    settings = {
        TrainerType.PPO: PPOSettings,
        TrainerType.DQN: DQNSettings,
        TrainerType.SAC: SACSettings,
        TrainerType.POCA: POCASettings,
    }.get(trainer_type)
    if settings is None:
        raise ValueError(f"unknown trainer type: {trainer_type}")
    return settings()
