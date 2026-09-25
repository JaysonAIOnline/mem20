"""Replay and trajectory storage with real shape and boundary semantics."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class Experience:
    """One transition stored in a replay buffer."""

    observation: np.ndarray
    action: np.ndarray
    reward: float
    next_observation: np.ndarray
    done: bool
    log_prob: float = 0.0
    value: float = 0.0
    advantage: float = 0.0
    return_: float = 0.0
    team_observation: np.ndarray | None = None
    priority: float = 1.0


class Buffer:
    """A fixed-capacity ring buffer with uniform and prioritized sampling."""

    def __init__(
        self,
        buffer_size: int = 10240,
        observation_shape: tuple[int, ...] = (),
        action_shape: tuple[int, ...] = (),
        team_observation_shape: tuple[int, ...] | None = None,
        seed: int | None = None,
    ) -> None:
        if int(buffer_size) < 1:
            raise ValueError("buffer_size must be positive")
        self.buffer_size = int(buffer_size)
        self.observation_shape = tuple(int(value) for value in observation_shape)
        self.action_shape = tuple(int(value) for value in action_shape)
        self.team_observation_shape = (
            None if team_observation_shape is None else tuple(int(value) for value in team_observation_shape)
        )
        self._rng = np.random.default_rng(seed)
        self.reset()

    def reset(self) -> None:
        """Remove all transitions while retaining the allocated storage."""
        self.observations = np.zeros((self.buffer_size,) + self.observation_shape, dtype=np.float32)
        self.actions = np.zeros((self.buffer_size,) + self.action_shape, dtype=np.float32)
        self.rewards = np.zeros(self.buffer_size, dtype=np.float32)
        self.next_observations = np.zeros((self.buffer_size,) + self.observation_shape, dtype=np.float32)
        self.dones = np.zeros(self.buffer_size, dtype=bool)
        self.log_probs = np.zeros(self.buffer_size, dtype=np.float32)
        self.values = np.zeros(self.buffer_size, dtype=np.float32)
        self.advantages = np.zeros(self.buffer_size, dtype=np.float32)
        self.returns = np.zeros(self.buffer_size, dtype=np.float32)
        self.priorities = np.ones(self.buffer_size, dtype=np.float32)
        self.sequence_ids = np.full(self.buffer_size, -1, dtype=np.int64)
        self.team_observations = (
            None
            if self.team_observation_shape is None
            else np.zeros((self.buffer_size,) + self.team_observation_shape, dtype=np.float32)
        )
        self.ptr = 0
        self.size = 0
        self._next_sequence_id = 0

    def clear(self) -> None:
        """Alias for :meth:`reset` used by on-policy trainers."""
        self.reset()

    def __len__(self) -> int:
        return self.size

    @staticmethod
    def _field(experience: Any, name: str, default: Any = None) -> Any:
        if isinstance(experience, dict):
            return experience.get(name, default)
        return getattr(experience, name, default)

    def _coerce(self, value: Any, shape: tuple[int, ...], name: str) -> np.ndarray:
        array = np.asarray(value, dtype=np.float32)
        if array.ndim == 0 and shape:
            array = array.reshape(shape)
        if array.shape != shape:
            raise ValueError(f"{name} shape {array.shape} != expected {shape}")
        if not np.all(np.isfinite(array)):
            raise ValueError(f"{name} contains non-finite values")
        return array

    def add(self, experience: Any) -> bool:
        """Insert a transition and return whether the ring is now full."""
        observation = self._coerce(
            self._field(experience, "observation"), self.observation_shape, "observation"
        )
        action = self._coerce(self._field(experience, "action"), self.action_shape, "action")
        next_observation = self._coerce(
            self._field(experience, "next_observation"),
            self.observation_shape,
            "next_observation",
        )
        if self.team_observations is not None:
            team_observation = self._field(experience, "team_observation")
            if team_observation is None:
                raise ValueError("team_observation is required by this buffer")
            team_array = self._coerce(
                team_observation, self.team_observation_shape, "team_observation"
            )
        else:
            team_array = None
        reward = float(self._field(experience, "reward", 0.0))
        done = bool(self._field(experience, "done", False))
        if not np.isfinite(reward):
            raise ValueError("reward must be finite")
        index = self.ptr
        self.observations[index] = observation
        self.actions[index] = action
        self.rewards[index] = reward
        self.next_observations[index] = next_observation
        self.dones[index] = done
        self.log_probs[index] = float(self._field(experience, "log_prob", 0.0))
        self.values[index] = float(self._field(experience, "value", 0.0))
        self.advantages[index] = float(self._field(experience, "advantage", 0.0))
        self.returns[index] = float(self._field(experience, "return_", 0.0))
        priority = float(self._field(experience, "priority", 1.0))
        self.priorities[index] = max(priority, 1e-6)
        if self.team_observations is not None and team_array is not None:
            self.team_observations[index] = team_array
        self.sequence_ids[index] = self._next_sequence_id
        self._next_sequence_id += 1
        self.ptr = (self.ptr + 1) % self.buffer_size
        self.size = min(self.size + 1, self.buffer_size)
        return self.size == self.buffer_size

    def _gather(self, indices: np.ndarray) -> dict[str, np.ndarray]:
        indices = np.asarray(indices, dtype=np.int64)
        batch: dict[str, np.ndarray] = {
            "observations": self.observations[indices].copy(),
            "actions": self.actions[indices].copy(),
            "rewards": self.rewards[indices].copy(),
            "next_observations": self.next_observations[indices].copy(),
            "dones": self.dones[indices].copy(),
            "log_probs": self.log_probs[indices].copy(),
            "values": self.values[indices].copy(),
            "advantages": self.advantages[indices].copy(),
            "returns": self.returns[indices].copy(),
            "priorities": self.priorities[indices].copy(),
        }
        if self.team_observations is not None:
            batch["team_observations"] = self.team_observations[indices].copy()
        return batch

    def get_batch(self, batch_size: int) -> dict[str, np.ndarray]:
        """Sample a uniform batch without replacement."""
        if self.size == 0:
            raise ValueError("cannot sample from an empty buffer")
        if int(batch_size) < 1:
            raise ValueError("batch_size must be positive")
        count = min(int(batch_size), self.size)
        indices = self._rng.choice(self.size, size=count, replace=False)
        return self._gather(indices)

    def sample_prioritized(
        self, batch_size: int, alpha: float = 0.6, beta: float = 0.4
    ) -> tuple[dict[str, np.ndarray], np.ndarray, np.ndarray]:
        """Sample proportional to priority and return importance weights."""
        if self.size == 0:
            raise ValueError("cannot sample from an empty buffer")
        if alpha < 0 or beta < 0:
            raise ValueError("priority sampling exponents must be non-negative")
        count = min(int(batch_size), self.size)
        probabilities = self.priorities[: self.size].astype(np.float64) ** float(alpha)
        probabilities = np.maximum(probabilities, 1e-12)
        probabilities /= probabilities.sum()
        indices = self._rng.choice(self.size, size=count, replace=False, p=probabilities)
        weights = (self.size * probabilities[indices]) ** (-float(beta))
        weights /= weights.max()
        return self._gather(indices), indices, weights.astype(np.float32)

    def update_priorities(self, indices: np.ndarray, td_errors: np.ndarray) -> None:
        """Replace priorities with absolute TD errors plus a numerical floor."""
        indices = np.asarray(indices, dtype=np.int64).reshape(-1)
        errors = np.asarray(td_errors, dtype=np.float64).reshape(-1)
        if len(indices) != len(errors):
            raise ValueError("priority indices and errors must have the same length")
        if len(indices) and (np.any(indices < 0) or np.any(indices >= self.size)):
            raise ValueError("priority index is outside the populated buffer")
        self.priorities[indices] = np.maximum(np.abs(errors) + 1e-6, 1e-6).astype(np.float32)

    def compute_advantages(
        self,
        gamma: float = 0.99,
        gae_lambda: float = 0.95,
        next_values: np.ndarray | None = None,
        bootstrap_value: float = 0.0,
    ) -> None:
        """Compute GAE in insertion order and stop propagation at done flags."""
        if self.size == 0:
            return
        if gamma < 0 or gae_lambda < 0:
            raise ValueError("gamma and gae_lambda must be non-negative")
        indices = np.argsort(self.sequence_ids[: self.size])
        rewards = self.rewards[indices].astype(np.float64)
        values = self.values[indices].astype(np.float64)
        dones = self.dones[indices].astype(bool)
        if next_values is None:
            next = np.zeros_like(values)
            if len(values) > 1:
                next[:-1] = values[1:]
        else:
            next = np.asarray(next_values, dtype=np.float64).reshape(-1)
            if len(next) != len(values):
                raise ValueError("next_values must match populated transitions")
        next[-1] = float(bootstrap_value)
        next = next * (~dones)
        advantages = np.zeros_like(values)
        running = 0.0
        for index in range(len(values) - 1, -1, -1):
            delta = rewards[index] + gamma * next[index] - values[index]
            running = delta + gamma * gae_lambda * (0.0 if dones[index] else running)
            advantages[index] = running
        self.advantages[indices] = advantages.astype(np.float32)
        self.returns[indices] = (advantages + values).astype(np.float32)

    def compute_returns(self, gamma: float = 0.99) -> None:
        """Compute discounted returns for the current insertion order."""
        if self.size == 0:
            return
        indices = np.argsort(self.sequence_ids[: self.size])
        rewards = self.rewards[indices].astype(np.float64)
        dones = self.dones[indices].astype(bool)
        returns = np.zeros_like(rewards)
        running = 0.0
        for index in range(len(rewards) - 1, -1, -1):
            running = rewards[index] + (0.0 if dones[index] else gamma * running)
            returns[index] = running
        self.returns[indices] = returns.astype(np.float32)


@dataclass
class Trajectory:
    """A single agent's synchronized trajectory."""

    agent_id: str
    observations: list[np.ndarray] = field(default_factory=list)
    actions: list[np.ndarray] = field(default_factory=list)
    rewards: list[float] = field(default_factory=list)
    log_probs: list[float] = field(default_factory=list)
    values: list[float] = field(default_factory=list)
    dones: list[bool] = field(default_factory=list)
    infos: list[dict] = field(default_factory=list)
    next_observations: list[np.ndarray] = field(default_factory=list)
    bootstrap_values: list[float] = field(default_factory=list)

    def add_step(
        self,
        obs: np.ndarray,
        action: np.ndarray,
        reward: float,
        log_prob: float,
        value: float,
        done: bool,
        info: dict | None = None,
        next_observation: np.ndarray | None = None,
        bootstrap_value: float = 0.0,
    ) -> None:
        """Append one transition and its next-state information."""
        observation = np.asarray(obs, dtype=np.float32)
        self.observations.append(observation)
        self.actions.append(np.asarray(action, dtype=np.float32))
        self.rewards.append(float(reward))
        self.log_probs.append(float(log_prob))
        self.values.append(float(value))
        self.dones.append(bool(done))
        self.infos.append(dict(info) if info is not None else {})
        self.next_observations.append(
            observation.copy() if next_observation is None else np.asarray(next_observation, dtype=np.float32)
        )
        self.bootstrap_values.append(float(bootstrap_value))

    def length(self) -> int:
        return len(self.rewards)

    def __len__(self) -> int:
        return self.length()

    def compute_returns(self, gamma: float = 0.99, bootstrap_value: float | None = None) -> np.ndarray:
        """Compute returns with terminal resets and optional truncation bootstrap."""
        returns = np.zeros(len(self.rewards), dtype=np.float64)
        running = 0.0
        for index in range(len(self.rewards) - 1, -1, -1):
            if self.dones[index]:
                continuation = 0.0
            elif index + 1 < len(self.rewards):
                continuation = running
            else:
                continuation = self.bootstrap_values[index] if bootstrap_value is None else float(bootstrap_value)
            running = self.rewards[index] + gamma * continuation
            returns[index] = running
        return returns.astype(np.float32)

    def compute_advantages(
        self,
        gamma: float = 0.99,
        gae_lambda: float = 0.95,
        next_values: np.ndarray | None = None,
        bootstrap_value: float | None = None,
    ) -> np.ndarray:
        """Compute trajectory GAE with explicit episode and bootstrap boundaries."""
        if not self.values:
            return np.zeros(0, dtype=np.float32)
        values = np.asarray(self.values, dtype=np.float64)
        rewards = np.asarray(self.rewards, dtype=np.float64)
        dones = np.asarray(self.dones, dtype=bool)
        if next_values is None:
            next_values = np.asarray(self.bootstrap_values, dtype=np.float64)
        else:
            next_values = np.asarray(next_values, dtype=np.float64).reshape(-1)
        if len(next_values) != len(values):
            raise ValueError("next_values must match trajectory length")
        if bootstrap_value is not None:
            next_values = next_values.copy()
            next_values[-1] = float(bootstrap_value)
        advantages = np.zeros(len(values), dtype=np.float64)
        running = 0.0
        for index in range(len(values) - 1, -1, -1):
            if index + 1 < len(values) and not dones[index]:
                next_value = values[index + 1]
            else:
                next_value = next_values[index]
            if dones[index]:
                next_value = 0.0
            delta = rewards[index] + gamma * next_value - values[index]
            running = delta + gamma * gae_lambda * (0.0 if dones[index] else running)
            advantages[index] = running
        return advantages.astype(np.float32)

    def final_observation(self) -> np.ndarray:
        if not self.observations:
            raise ValueError("trajectory has no observations")
        if self.next_observations:
            return self.next_observations[-1].copy()
        return self.observations[-1].copy()
