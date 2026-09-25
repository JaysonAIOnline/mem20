"""Reward Shaper — native absorption of OpenGame reward shaping.

``PotentialBasedShaper`` implements the Ng et al. (1999) result exactly:

    F(s, a, s') = scale * (gamma * PHI(s') - PHI(s))
    r_shaped      = r + F

A state s' that terminates the episode has PHI(s') := 0, so the shaping at a
terminal transition is -PHI(s). Because the shaping function telescopes over
episodes, the optimal policy is invariant under shaping (Ng et al. 1999 Thm. 1)
and every episode's total discounted shaping equals
``scale * (gamma^T * PHI(s_T) - PHI(s_0))`` for a terminal final state.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np


@dataclass
class RewardConfig:
    """Reward shaping configuration."""

    shaping_type: str = "potential"
    gamma: float = 0.99
    scale: float = 1.0
    clip: tuple[float, float] | None = None

    def __post_init__(self) -> None:
        valid_types = {"potential", "curriculum", "intrinsic", "shaped"}
        if self.shaping_type not in valid_types:
            raise ValueError(f"unknown shaping_type: {self.shaping_type}")
        if not 0.0 <= self.gamma <= 1.0:
            raise ValueError("gamma must be in [0, 1]")
        if not np.isfinite(self.scale):
            raise ValueError("scale must be finite")
        if self.clip is not None:
            lower, upper = self.clip
            if not np.isfinite(lower) or not np.isfinite(upper) or lower > upper:
                raise ValueError("clip must be a finite ordered pair")


def _apply_scale_clip(value: float, config: RewardConfig) -> float:
    value = config.scale * value
    if config.clip is not None:
        lo, hi = config.clip
        value = min(max(value, lo), hi)
    return value


class RewardShaper(ABC):
    """Base reward shaper."""

    def __init__(self, config: RewardConfig):
        self.config = config

    @abstractmethod
    def shape(
        self,
        reward: float,
        state: np.ndarray,
        action: int,
        next_state: np.ndarray,
        done: bool,
        info: dict,
    ) -> float:
        raise NotImplementedError

    def reset(self) -> None:
        """Reset any internal state (per episode)."""


class PotentialBasedShaper(RewardShaper):
    """Ng et al. (1999) potential-based reward shaping.

    F = gamma * PHI(s') - PHI(s), with PHI(s') = 0 on terminal states.
    """

    def __init__(self, config: RewardConfig, potential_fn: Callable):
        if config.clip is not None:
            raise ValueError("clip is incompatible with potential-based reward shaping")
        if not callable(potential_fn):
            raise TypeError("potential_fn must be callable")
        super().__init__(config)
        self.potential_fn = potential_fn

    def shape(
        self,
        reward: float,
        state: np.ndarray,
        action: int,
        next_state: np.ndarray,
        done: bool,
        info: dict,
    ) -> float:
        current_potential = float(self.potential_fn(state))
        next_potential = 0.0 if done else float(self.potential_fn(next_state))
        bonus = self.config.scale * (self.config.gamma * next_potential - current_potential)
        return float(reward + bonus)


class CurriculumShaper(RewardShaper):
    """Curriculum-based reward shaping (weighted by curriculum schedule)."""

    def __init__(self, config: RewardConfig, curriculum_fn: Callable):
        super().__init__(config)
        self.curriculum_fn = curriculum_fn
        self.step = 0

    def shape(
        self,
        reward: float,
        state: np.ndarray,
        action: int,
        next_state: np.ndarray,
        done: bool,
        info: dict,
    ) -> float:
        self.step += 1
        weight = self.curriculum_fn(self.step)
        return _apply_scale_clip(reward * weight, self.config)

    def reset(self) -> None:
        self.step = 0


class IntrinsicRewardShaper(RewardShaper):
    """Intrinsic reward shaping (curiosity, entropy, etc.)."""

    def __init__(self, config: RewardConfig, intrinsic_fn: Callable):
        super().__init__(config)
        self.intrinsic_fn = intrinsic_fn

    def shape(
        self,
        reward: float,
        state: np.ndarray,
        action: int,
        next_state: np.ndarray,
        done: bool,
        info: dict,
    ) -> float:
        intrinsic = float(self.intrinsic_fn(state, action, next_state))
        weight = float(info.get("intrinsic_weight", 0.1))
        return _apply_scale_clip(reward + weight * intrinsic, self.config)


class ShapedRewardShaper(RewardShaper):
    """Manual reward shaping with custom rules."""

    def __init__(self, config: RewardConfig, rules: list[dict]):
        super().__init__(config)
        self.rules = rules

    def shape(
        self,
        reward: float,
        state: np.ndarray,
        action: int,
        next_state: np.ndarray,
        done: bool,
        info: dict,
    ) -> float:
        shaped = reward
        for rule in self.rules:
            condition = rule.get("condition", lambda s, a, ns: True)
            bonus = rule.get("bonus", 0.0)
            if condition(state, action, next_state):
                shaped += rule.get("scale", 1.0) * bonus
        return _apply_scale_clip(shaped, self.config)


def create_shaper(config: RewardConfig, **kwargs) -> RewardShaper:
    """Factory to create reward shaper."""
    if config.shaping_type == "potential":
        return PotentialBasedShaper(config, kwargs["potential_fn"])
    elif config.shaping_type == "curriculum":
        return CurriculumShaper(config, kwargs.get("curriculum_fn", lambda step: 1.0))
    elif config.shaping_type == "intrinsic":
        return IntrinsicRewardShaper(config, kwargs["intrinsic_fn"])
    elif config.shaping_type == "shaped":
        return ShapedRewardShaper(config, kwargs.get("rules", []))
    raise ValueError(f"unknown shaping_type: {config.shaping_type}")