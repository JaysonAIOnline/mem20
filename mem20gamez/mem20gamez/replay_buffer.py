"""Replay Buffer — native absorption of OpenGame replay buffer.

A real prioritized experience replay (PER, Schaul et al. 2015):
  - ring-buffer storage of normalized ``Experience`` records,
  - proportional prioritization sampling,
  - importance-sampling (IS) weights with annealed beta,
  - priority updates keyed by the sampled indices,
  - guaranteed batch shapes for downstream torch learning.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class Experience:
    """Single experience (s, a, r, s', done[, info])."""

    state: np.ndarray
    action: int
    reward: float
    next_state: np.ndarray
    done: bool
    info: dict = field(default_factory=dict)
    priority: float = 1.0
    truncated: bool = False


def stack_batch(batch: list[Experience]) -> dict[str, np.ndarray]:
    """Stack a batch of Experience records into arrays with guaranteed shapes."""
    if not batch:
        raise ValueError("cannot stack an empty batch")
    state_shape = np.shape(batch[0].state)
    if state_shape == ():
        raise ValueError("state shape must include at least one dimension")
    for experience in batch:
        if np.shape(experience.state) != state_shape or np.shape(experience.next_state) != state_shape:
            raise ValueError("state and next_state shapes must match across the batch")
    states = np.stack([np.asarray(item.state, dtype=np.float32) for item in batch])
    next_states = np.stack([np.asarray(item.next_state, dtype=np.float32) for item in batch])
    actions = np.asarray([item.action for item in batch], dtype=np.int64)
    rewards = np.asarray([item.reward for item in batch], dtype=np.float32)
    dones = np.asarray([item.done for item in batch], dtype=np.float32)
    truncateds = np.asarray([item.truncated for item in batch], dtype=np.float32)
    return {
        "states": states,
        "actions": actions,
        "rewards": rewards,
        "next_states": next_states,
        "dones": dones,
        "truncateds": truncateds,
    }


class ReplayBuffer:
    """Prioritized experience replay with a strict ring buffer."""

    def __init__(
        self,
        capacity: int = 100000,
        alpha: float = 0.6,  # Prioritization exponent
        beta: float = 0.4,   # Importance sampling exponent
        beta_increment: float = 0.001,
        seed: int | None = None,
    ):
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        if not 0.0 <= alpha <= 1.0:
            raise ValueError("alpha must be in [0, 1]")
        if not 0.0 <= beta <= 1.0:
            raise ValueError("beta must be in [0, 1]")
        if beta_increment < 0.0:
            raise ValueError("beta_increment must be non-negative")
        self.capacity = capacity
        self.alpha = alpha
        self.beta = beta
        self.beta_increment = beta_increment
        self.max_priority = 1.0

        self.buffer: deque = deque(maxlen=capacity)
        self.priorities = np.zeros(capacity, dtype=np.float32)
        self.pos = 0
        self._rng = np.random.default_rng(seed)

    @staticmethod
    def normalize(experience: Any) -> Experience:
        """Coerce dict / tuple / Experience into a normalized Experience."""
        if isinstance(experience, Experience):
            return experience
        if isinstance(experience, dict):
            done = bool(experience.get("done", experience.get("terminated", False)))
            return Experience(
                state=np.asarray(experience["state"], dtype=np.float32),
                action=int(experience["action"]),
                reward=float(experience["reward"]),
                next_state=np.asarray(experience["next_state"], dtype=np.float32),
                done=done,
                info=dict(experience.get("info", {})),
                truncated=bool(experience.get("truncated", False)),
            )
        if isinstance(experience, (tuple, list)):
            n = len(experience)
            if n < 5:
                raise ValueError(f"experience tuple needs >= 5 fields, got {n}")
            info = dict(experience[5]) if n > 5 and isinstance(experience[5], dict) else {}
            return Experience(
                state=np.asarray(experience[0], dtype=np.float32),
                action=int(experience[1]),
                reward=float(experience[2]),
                next_state=np.asarray(experience[3], dtype=np.float32),
                done=bool(experience[4]),
                info=info,
                truncated=bool(experience[6]) if n > 6 else False,
            )
        raise TypeError(f"unsupported experience type: {type(experience)}")

    def add(self, experience: Any) -> None:
        """Add a normalized experience to the ring buffer."""
        exp = self.normalize(experience)

        if len(self.buffer) < self.capacity:
            self.buffer.append(exp)
        else:
            self.buffer[self.pos] = exp

        self.priorities[self.pos] = self.max_priority
        self.pos = (self.pos + 1) % self.capacity

    def sample(self, batch_size: int) -> tuple[list[Experience], np.ndarray, np.ndarray]:
        """Sample exactly ``batch_size`` transitions using proportional prioritization."""
        if batch_size <= 0:
            raise ValueError("requested batch size must be positive")
        n = len(self.buffer)
        if n < batch_size:
            raise ValueError(f"requested batch size {batch_size} exceeds available experiences {n}")
        priorities = self.priorities[:n] if n < self.capacity else self.priorities
        probs = np.maximum(priorities, 1e-8) ** self.alpha
        probs = probs / probs.sum()
        indices = self._rng.choice(n, size=batch_size, replace=False, p=probs)
        weights = (n * probs[indices]) ** (-self.beta)
        weights /= float(weights.max())
        batch = [self.buffer[int(index)] for index in indices]
        self.beta = min(1.0, self.beta + self.beta_increment)
        return batch, indices.astype(np.int64), weights.astype(np.float32)

    def update_priorities(self, indices: list[int], priorities: np.ndarray) -> None:
        """Update priorities for the exact indices returned by sample."""
        values = np.atleast_1d(np.asarray(priorities, dtype=np.float32))
        index_array = np.asarray(indices, dtype=np.int64)
        if index_array.ndim != 1 or len(index_array) != len(values):
            raise ValueError("indices and priorities must have matching one-dimensional lengths")
        n = len(self.buffer)
        if np.any(index_array < 0) or np.any(index_array >= n):
            raise IndexError("replay priority index is outside the live buffer")
        absolute = np.abs(values)
        self.priorities[index_array] = absolute + 1e-6
        if len(absolute):
            self.max_priority = max(self.max_priority, float(absolute.max()))

    def batch_to_arrays(self, batch: list[Experience]) -> dict[str, np.ndarray]:
        """Assemble a batch into stacked numpy arrays (guaranteed shapes).

        Kept as a convenience method; see the module-level ``stack_batch``.
        """
        return stack_batch(batch)

    def __len__(self) -> int:
        return len(self.buffer)

    def __iter__(self) -> Iterator[Experience]:
        if len(self.buffer) < self.capacity:
            yield from self.buffer
            return
        for index in range(self.pos, self.capacity):
            yield self.buffer[index]
        for index in range(self.pos):
            yield self.buffer[index]

    def clear(self) -> None:
        """Clear buffer."""
        self.buffer.clear()
        self.priorities.fill(0)
        self.pos = 0
        self.max_priority = 1.0


class EpisodeBuffer:
    """Deterministic bounded storage for complete episodes."""

    def __init__(self, capacity: int = 1000, seed: int | None = None):
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self.capacity = capacity
        self.episodes: list[list[dict]] = []
        self._rng = np.random.default_rng(seed)

    def add_episode(self, episode: list[dict]) -> None:
        """Add complete episode."""
        if len(self.episodes) >= self.capacity:
            self.episodes.pop(0)
        self.episodes.append(episode)

    def sample_episode(self) -> list[dict]:
        """Sample random episode."""
        if not self.episodes:
            return []
        return self.episodes[int(self._rng.integers(len(self.episodes)))]

    def get_recent(self, n: int) -> list[list[dict]]:
        """Get n most recent episodes."""
        return self.episodes[-n:] if n else []

    def get_total_transitions(self) -> int:
        return sum(len(ep) for ep in self.episodes)

    def __len__(self) -> int:
        return len(self.episodes)