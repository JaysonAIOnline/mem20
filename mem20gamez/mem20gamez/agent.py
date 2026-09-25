"""Game Agent — native absorption of OpenGame agent.

Base classes, configuration, non-learning agents and the agent factory.
All learning agents (DQN / REINFORCE / PPO / SAC) live in ``mem20gamez.agents``
and are real torch implementations.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any

import numpy as np


class AgentType(str, Enum):
    """Agent type."""

    DQN = "dqn"
    REINFORCE = "reinforce"
    PPO = "ppo"
    SAC = "sac"
    RANDOM = "random"
    RULE_BASED = "rule_based"


@dataclass
class AgentConfig:
    """Configuration shared by every agent."""

    agent_type: AgentType = AgentType.DQN
    obs_shape: tuple[int, ...] = (4,)
    action_size: int = 2
    hidden_size: int = 128
    num_layers: int = 2
    learning_rate: float = 3e-4
    gamma: float = 0.99
    tau: float = 0.005  # Polyak soft-update coefficient (1.0 = hard sync)
    epsilon: float = 1.0
    epsilon_min: float = 0.01
    epsilon_decay: float = 0.995
    buffer_size: int = 100000
    batch_size: int = 64
    target_update: int = 1000  # steps between hard target syncs
    dueling: bool = False  # use a dueling Q head (DQN only)
    seed: int = 0
    # policy-gradient knobs (REINFORCE / PPO / SAC)
    entropy_coef: float = 0.01
    clip_ratio: float = 0.2
    train_epochs: int = 4
    minibatch_size: int = 512
    vf_coef: float = 0.5
    max_grad_norm: float = 10.0
    # SAC temperature
    alpha: float = 0.2
    target_entropy: float | None = None

    def __post_init__(self) -> None:
        if not self.obs_shape or any(int(size) <= 0 for size in self.obs_shape):
            raise ValueError("obs_shape must contain positive dimensions")
        if self.action_size <= 0:
            raise ValueError("action_size must be positive")
        if self.hidden_size <= 0 or self.num_layers <= 0:
            raise ValueError("hidden_size and num_layers must be positive")
        if self.learning_rate <= 0.0:
            raise ValueError("learning_rate must be positive")
        if not 0.0 <= self.gamma <= 1.0:
            raise ValueError("gamma must be in [0, 1]")
        if not 0.0 <= self.tau <= 1.0:
            raise ValueError("tau must be in [0, 1]")
        if not 0.0 <= self.epsilon_min <= self.epsilon <= 1.0:
            raise ValueError("epsilon must satisfy 0 <= epsilon_min <= epsilon <= 1")
        if not 0.0 < self.epsilon_decay <= 1.0:
            raise ValueError("epsilon_decay must be in (0, 1]")
        if self.buffer_size <= 0 or self.batch_size <= 0:
            raise ValueError("buffer_size and batch_size must be positive")
        if self.batch_size > self.buffer_size:
            raise ValueError("batch_size cannot exceed buffer_size")
        if self.target_update <= 0:
            raise ValueError("target_update must be positive")

    @property
    def input_dim(self) -> int:
        return int(np.prod(self.obs_shape))


class GameAgent(ABC):
    """Base game agent."""

    buffer = None  # replay buffer for DQN/SAC-style agents; see agents.py

    def __init__(self, config: AgentConfig):
        self.config = config
        self.step_count = 0
        self.episode_count = 0

    @abstractmethod
    def act(self, obs: np.ndarray, training: bool = True) -> int:
        raise NotImplementedError

    @abstractmethod
    def learn(self, experiences: list | None = None) -> dict[str, float]:
        raise NotImplementedError

    @abstractmethod
    def replay(self) -> dict[str, float] | None:
        raise NotImplementedError

    @abstractmethod
    def remember(self, experience: Any) -> None:
        raise NotImplementedError

    @abstractmethod
    def end_episode(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def save(self, path: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def load(self, path: str) -> bool:
        raise NotImplementedError


class RandomAgent(GameAgent):
    """Random agent — uniform action baseline."""

    def __init__(self, config: AgentConfig):
        super().__init__(config)
        self._rng = np.random.default_rng(config.seed)

    def act(self, obs: np.ndarray, training: bool = True) -> int:
        return int(self._rng.integers(self.config.action_size))

    def learn(self, experiences: list | None = None) -> dict[str, float]:
        return {}

    def replay(self) -> dict[str, float] | None:
        return None

    def remember(self, experience: Any) -> None:
        return None

    def end_episode(self) -> None:
        self.episode_count += 1

    def save(self, path: str) -> bool:
        raise NotImplementedError("RandomAgent has no trainable checkpoint")

    def load(self, path: str) -> bool:
        raise NotImplementedError("RandomAgent has no trainable checkpoint")


class RuleBasedAgent(GameAgent):
    """Deterministic heuristic agent.

    For one-hot gridworld observations it moves greedily toward the goal cell
    (bottom-right of the grid). For any other observation space it emits a
    fixed action 0. It is deliberately simple and never learns.
    """

    def __init__(self, config: AgentConfig):
        super().__init__(config)

    def _grid_target(self, obs: np.ndarray) -> int | None:
        """Greedy Manhattan moves toward the goal cell of the active sub-grid.

        Action map: 0=up, 1=down, 2=left, 3=right. The goal is the bottom-right
        corner of the *active* grid (read from the difficulty channel), so the
        rule still applies under a curriculum that grows the grid.
        """
        from .environment import decode_grid_obs

        decoded = decode_grid_obs(obs)
        if decoded is None:
            return None
        row, col, _canvas, grid = decoded
        goal_row, goal_col = grid - 1, grid - 1
        if col < goal_col:
            return 3  # right
        if row < goal_row:
            return 1  # down
        if col > goal_col:
            return 2  # left
        if row > goal_row:
            return 0  # up
        return 0  # already at goal — hold

    def act(self, obs: np.ndarray, training: bool = True) -> int:
        action = self._grid_target(obs)
        if action is None:
            return 0
        return min(action, self.config.action_size - 1)

    def learn(self, experiences: list | None = None) -> dict[str, float]:
        return {}

    def replay(self) -> dict[str, float] | None:
        return None

    def remember(self, experience: Any) -> None:
        return None

    def end_episode(self) -> None:
        self.episode_count += 1

    def save(self, path: str) -> bool:
        raise NotImplementedError("RuleBasedAgent has no trainable checkpoint")

    def load(self, path: str) -> bool:
        raise NotImplementedError("RuleBasedAgent has no trainable checkpoint")


def create_agent(config: AgentConfig) -> GameAgent:
    """Factory to create an agent."""
    from .agents import DQNAgent, PPOAgent, REINFORCEAgent, SACAgent

    if config.agent_type == AgentType.RANDOM:
        return RandomAgent(config)
    elif config.agent_type == AgentType.RULE_BASED:
        return RuleBasedAgent(config)
    elif config.agent_type == AgentType.DQN:
        return DQNAgent(config)
    elif config.agent_type == AgentType.REINFORCE:
        return REINFORCEAgent(config)
    elif config.agent_type == AgentType.PPO:
        return PPOAgent(config)
    elif config.agent_type == AgentType.SAC:
        return SACAgent(config)
    raise ValueError(f"unknown agent_type: {config.agent_type}")