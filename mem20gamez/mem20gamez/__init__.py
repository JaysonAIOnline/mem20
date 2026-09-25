"""mem20gamez — native OpenGame absorption.

Real implementations: game agents (DQN / REINFORCE / PPO / SAC), environments
(TinyGridWorld-v0, gymnasium wrappers), reward shaping (Ng potential-based),
adaptive curriculum, prioritized replay, single- and multi-agent trainers.
"""

from .agent import (
    AgentConfig,
    AgentType,
    GameAgent,
    RandomAgent,
    RuleBasedAgent,
    create_agent,
)
from .agents import DQNAgent, PPOAgent, REINFORCEAgent, SACAgent
from .config import DEFAULT_CONFIG, GameConfig
from .curriculum import (
    AdaptiveCurriculum,
    Curriculum,
    CurriculumConfig,
    CurriculumType,
    ExponentialCurriculum,
    LinearCurriculum,
    SelfPacedCurriculum,
    StepCurriculum,
    create_curriculum,
)
from .environment import (
    EnvConfig,
    Environment,
    GymnasiumEnvironment,
    StepResult,
    TinyGridWorld,
    create_environment,
)
from .networks import (
    DuelingQNetwork,
    PolicyNetwork,
    QNetwork,
    ValueNetwork,
    build_mlp,
)
from .replay_buffer import (
    EpisodeBuffer,
    Experience,
    ReplayBuffer,
    stack_batch,
)
from .reward_shaper import (
    CurriculumShaper,
    IntrinsicRewardShaper,
    PotentialBasedShaper,
    RewardConfig,
    RewardShaper,
    ShapedRewardShaper,
    create_shaper,
)
from .trainer import (
    DQNTrainer,
    MultiAgentTrainer,
    default_adaptive_curriculum,
    default_reward_shaper,
    normalize_grid_size,
)

__title__ = "mem20gamez"
__version__ = "0.1.0"

__all__ = [
    "DEFAULT_CONFIG",
    "AdaptiveCurriculum",
    "AgentConfig",
    "AgentType",
    "Curriculum",
    "CurriculumConfig",
    "CurriculumShaper",
    "CurriculumType",
    "DQNAgent",
    "DQNTrainer",
    "DuelingQNetwork",
    "EnvConfig",
    "Environment",
    "EpisodeBuffer",
    "Experience",
    "ExponentialCurriculum",
    "GameAgent",
    "GameConfig",
    "GymnasiumEnvironment",
    "IntrinsicRewardShaper",
    "LinearCurriculum",
    "MultiAgentTrainer",
    "PPOAgent",
    "PolicyNetwork",
    "PotentialBasedShaper",
    "QNetwork",
    "REINFORCEAgent",
    "RandomAgent",
    "ReplayBuffer",
    "RewardConfig",
    "RewardShaper",
    "RuleBasedAgent",
    "SACAgent",
    "SelfPacedCurriculum",
    "ShapedRewardShaper",
    "StepCurriculum",
    "StepResult",
    "TinyGridWorld",
    "ValueNetwork",
    "build_mlp",
    "create_agent",
    "create_curriculum",
    "create_environment",
    "create_shaper",
    "default_adaptive_curriculum",
    "default_reward_shaper",
    "normalize_grid_size",
    "stack_batch",
]