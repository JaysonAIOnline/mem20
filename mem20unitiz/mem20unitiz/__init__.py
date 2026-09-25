"""mem20unitiz: a real reinforcement-learning toolkit.

The package provides trainable grid and cooperative environments, PPO, DQN,
SAC, cooperative PPO, explicit replay buffers, and checkpoint persistence.
It uses Torch when the runtime provides it and a real NumPy network otherwise.
It does not claim a Unity editor bridge or a long-lived server.
"""

from .buffer import Buffer, Experience, Trajectory
from .config import DEFAULT_CONFIG, MLConfig
from .environment import (
    ActionSpec,
    AgentInfo,
    BehaviorSpec,
    CooperativeGridWorld,
    Environment,
    GridWorld,
    ObservationSpec,
    ObservationType,
    SimpleEnvironment,
    StepOutput,
)
from .model_saver import ModelCheckpoint, ModelSaver
from .policy import (
    TORCH_AVAILABLE,
    NumPyPolicy,
    Policy,
    PolicyOutput,
    QNetwork,
    SACPolicy,
    create_policy,
)
from .settings import (
    DQNSettings,
    NetworkSettings,
    NetworkType,
    POCASettings,
    PPOSettings,
    SACSettings,
    TorchSettings,
    TrainerSettings,
    TrainerType,
    get_default_settings,
)
from .trainer import (
    DQNTrainer,
    POCATrainer,
    PPOTrainer,
    SACTrainer,
    Trainer,
    TrainingMetrics,
    create_trainer,
)

__version__ = "0.2.0"

__all__ = [
    "DEFAULT_CONFIG",
    "TORCH_AVAILABLE",
    "ActionSpec",
    "AgentInfo",
    "BehaviorSpec",
    "Buffer",
    "CooperativeGridWorld",
    "DQNSettings",
    "DQNTrainer",
    "Environment",
    "Experience",
    "GridWorld",
    "MLConfig",
    "ModelCheckpoint",
    "ModelSaver",
    "NetworkSettings",
    "NetworkType",
    "NumPyPolicy",
    "ObservationSpec",
    "ObservationType",
    "POCASettings",
    "POCATrainer",
    "PPOSettings",
    "PPOTrainer",
    "Policy",
    "PolicyOutput",
    "QNetwork",
    "SACPolicy",
    "SACSettings",
    "SACTrainer",
    "SimpleEnvironment",
    "StepOutput",
    "TorchSettings",
    "Trainer",
    "TrainerSettings",
    "TrainerType",
    "TrainingMetrics",
    "Trajectory",
    "create_policy",
    "create_trainer",
    "get_default_settings",
]

if TORCH_AVAILABLE:
    from .policy import TorchPolicy as TorchPolicy

    __all__.append("TorchPolicy")
