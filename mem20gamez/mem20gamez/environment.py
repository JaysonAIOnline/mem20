"""Environment — native absorption of OpenGame environment.

Contains a real, in-package learnable gridworld (``TinyGridWorld``) and a
strict optional Gymnasium wrapper. Unknown or unavailable environments fail
explicitly rather than falling back to synthetic behavior.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

import numpy as np

try:
    import gymnasium as gym

    GYM_AVAILABLE = True
except ImportError:
    gym = None
    GYM_AVAILABLE = False


def decode_grid_obs(obs: np.ndarray) -> tuple[int, int, int, int] | None:
    """Decode a TinyGridWorld observation to (row, col, canvas, grid_size).

    Returns None when the observation is not a grid-world one (e.g. a
    gymnasium vector), so callers can fall back cleanly.
    """
    flat = np.asarray(obs, dtype=np.float32).reshape(-1)
    n = int(flat.shape[0])
    if n < 5:
        return None
    canvas = round((n - 1) ** 0.5)
    if canvas * canvas != n - 1:
        return None
    idx = int(np.argmax(flat[:-1]))
    row, col = divmod(idx, canvas)
    difficulty = float(flat[-1])
    grid = round(difficulty * canvas)
    grid = max(2, min(canvas, grid))
    return row, col, canvas, grid


@dataclass
class EnvConfig:
    """Environment configuration."""

    env_id: str = "TinyGridWorld-v0"
    max_episode_steps: int = 100
    render_mode: str | None = None
    seed: int = 0
    # TinyGridWorld knobs
    grid_size: int = 4  # active sub-grid side (the task's difficulty)
    max_grid_size: int = 4  # fixed canvas side; obs dim = max_grid_size**2 + 1
    goal_reward: float = 10.0
    step_penalty: float = -0.01
    wall_penalty: float = -0.1
    wind_prob: float = 0.0

    def __post_init__(self) -> None:
        if not self.env_id:
            raise ValueError("env_id must not be empty")
        if self.max_episode_steps <= 0:
            raise ValueError("max_episode_steps must be positive")
        if self.grid_size < 2 or self.max_grid_size < 2:
            raise ValueError("grid sizes must be at least 2")
        if self.grid_size > self.max_grid_size:
            raise ValueError("grid_size cannot exceed max_grid_size")
        if not 0.0 <= self.wind_prob <= 1.0:
            raise ValueError("wind_prob must be in [0, 1]")


@dataclass
class StepResult:
    """Environment step result."""

    observation: np.ndarray
    reward: float
    terminated: bool
    truncated: bool
    info: dict[str, Any] = field(default_factory=dict)


class Environment(ABC):
    """Base environment."""

    def __init__(self, config: EnvConfig):
        self.config = config
        self.step_count = 0
        self.episode_count = 0

    @property
    @abstractmethod
    def obs_shape(self) -> tuple[int, ...]:
        raise NotImplementedError

    @property
    @abstractmethod
    def action_size(self) -> int:
        raise NotImplementedError

    @abstractmethod
    def reset(self, seed: int | None = None) -> tuple[np.ndarray, dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def step(self, action: int) -> StepResult:
        raise NotImplementedError

    @abstractmethod
    def render(self) -> np.ndarray | None:
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        raise NotImplementedError


class TinyGridWorld(Environment):
    """A real, small discrete gridworld that is learnable in seconds.

    The observation is a *fixed-size* one-hot state that never changes length
    across curriculum stages:

        obs = [ one-hot(row * grid_size + col) on an N x N canvas ] + [ difficulty ]

    where N = max_grid_size and `difficulty` = active grid_size / N. The
    active sub-grid is the top-left grid_size x grid_size area of the canvas,
    so a larger active grid is literally a harder task with the same action
    space and the same observation dimensionality. This keeps a single fixed
    network (and a single replay buffer) compatible with a curriculum that
    graduates the grid size over time, and it makes every state unambiguous.

    State  : fixed-canvas one-hot position + difficulty channel
    Action : 0=up, 1=down, 2=left, 3=right (with optional wind noise)
    Reward : +goal_reward on reaching the goal cell, step_penalty each step,
             wall_penalty when bumping a wall.
    Done   : reaching the goal, or episode step budget exhausted (truncated).
    """

    UP, DOWN, LEFT, RIGHT = 0, 1, 2, 3
    ACTIONS = (UP, DOWN, LEFT, RIGHT)
    DELTAS: ClassVar[dict[int, tuple[int, int]]] = {
        UP: (-1, 0),
        DOWN: (1, 0),
        LEFT: (0, -1),
        RIGHT: (0, 1),
    }

    def __init__(self, config: EnvConfig):
        super().__init__(config)
        self._canvas = int(config.max_grid_size)
        self._obs_shape = (int(self._canvas**2) + 1,)
        self._action_size = 4
        self.pos = (0, 0)
        self.rng = np.random.default_rng(config.seed)

    @property
    def goal_pos(self) -> tuple[int, int]:
        """Goal cell tracks the *active* grid size (may change per episode)."""
        g = int(self.config.grid_size)
        return (g - 1, g - 1)

    @property
    def obs_shape(self) -> tuple[int, ...]:
        return self._obs_shape

    @property
    def action_size(self) -> int:
        return self._action_size

    @property
    def grid_size(self) -> int:
        return self.config.grid_size

    @property
    def canvas(self) -> int:
        return self._canvas

    def _difficulty(self) -> float:
        """Difficulty channel: active grid fraction of the canvas."""
        return float(int(self.config.grid_size) / self._canvas)

    def _encode(self, row: int, col: int) -> np.ndarray:
        flat = row * self._canvas + col
        obs = np.zeros(self._obs_shape, dtype=np.float32)
        obs[flat] = 1.0
        obs[-1] = self._difficulty()
        return obs

    def reset(self, seed: int | None = None) -> tuple[np.ndarray, dict[str, Any]]:
        if seed is not None:
            self.rng = np.random.default_rng(seed)
        self.step_count = 0
        self.pos = (0, 0)
        return self._encode(*self.pos), {"pos": self.pos, "grid_size": self.config.grid_size}

    def _decode(self, obs: np.ndarray) -> tuple[int, int]:
        """Decode a canvas one-hot observation back to its position."""
        n = int(obs.shape[-1])
        canvas = round((n - 1) ** 0.5)
        idx = int(np.argmax(obs[:-1]))
        return divmod(idx, canvas)

    def step(self, action: int) -> StepResult:
        action = int(action)
        if action not in self.ACTIONS:
            raise ValueError(f"action {action} not in {self.ACTIONS}")
        self.step_count += 1

        # Optional stochasticity: a random action replaces the requested one.
        if self.config.wind_prob > 0.0 and self.rng.random() < self.config.wind_prob:
            action = int(self.rng.integers(self._action_size))

        dr, dc = self.DELTAS[action]
        tr = self.pos[0] + dr
        tc = self.pos[1] + dc
        size = int(self.config.grid_size)

        if 0 <= tr < size and 0 <= tc < size:
            self.pos = (tr, tc)
            reward = self.config.step_penalty
            hit_wall = False
        else:
            reward = self.config.wall_penalty
            hit_wall = True

        goal = self.pos == self.goal_pos
        terminated = bool(goal)
        truncated = self.step_count >= self.config.max_episode_steps
        info = {
            "pos": self.pos,
            "grid_size": int(self.config.grid_size),
            "goal_reached": goal,
            "hit_wall": hit_wall,
        }

        if goal:
            reward += self.config.goal_reward
        if terminated or truncated:
            self.episode_count += 1

        return StepResult(
            observation=self._encode(*self.pos),
            reward=float(reward),
            terminated=terminated,
            truncated=bool(truncated),
            info=info,
        )

    def render(self) -> np.ndarray | None:
        grid = np.full((self._canvas, self._canvas), 0, dtype=np.int8)
        grid[self.goal_pos] = 2
        grid[self.pos] = 1
        return grid.copy()

    def close(self) -> None:
        return None


class GymnasiumEnvironment(Environment):
    """Real gymnasium environment wrapper."""

    def __init__(self, config: EnvConfig):
        if gym is None:
            raise RuntimeError("gymnasium not available")
        super().__init__(config)
        self.env = gym.make(config.env_id, render_mode=config.render_mode)
        self.env.reset(seed=config.seed)
        self._obs_shape = tuple(int(s) for s in self.env.observation_space.shape)
        self._action_size = int(self.env.action_space.n)

    @property
    def obs_shape(self) -> tuple[int, ...]:
        return self._obs_shape

    @property
    def action_size(self) -> int:
        return self._action_size

    def reset(self, seed: int | None = None) -> tuple[np.ndarray, dict[str, Any]]:
        self.step_count = 0
        obs, info = self.env.reset(seed=seed)
        return np.asarray(obs, dtype=np.float32), info

    def step(self, action: int) -> StepResult:
        self.step_count += 1
        obs, reward, terminated, truncated, info = self.env.step(int(action))
        if terminated or truncated:
            self.episode_count += 1
        return StepResult(
            observation=np.asarray(obs, dtype=np.float32),
            reward=float(reward),
            terminated=bool(terminated),
            truncated=bool(truncated),
            info=dict(info),
        )

    def render(self) -> np.ndarray | None:
        return self.env.render()

    def close(self) -> None:
        self.env.close()


def create_environment(config: EnvConfig) -> Environment:
    """Create the requested environment or fail with an actionable error."""
    if config.env_id == "TinyGridWorld-v0":
        return TinyGridWorld(config)
    if not GYM_AVAILABLE:
        raise RuntimeError(
            f"environment {config.env_id!r} requires the optional gymnasium dependency"
        )
    try:
        return GymnasiumEnvironment(config)
    except Exception as exc:
        raise RuntimeError(f"could not create environment {config.env_id!r}: {exc}") from exc
