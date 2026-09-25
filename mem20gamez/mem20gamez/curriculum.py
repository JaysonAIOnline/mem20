"""Curriculum — native absorption of OpenGame curriculum learning.

Real adaptive curriculum: difficulty advances only when the agent's real
recent performance clears a threshold over a sliding window of episodes, and
regresses when performance collapses below a lower bound. All schedules
(linear / exponential / step) are genuine deterministic functions of the
current step; adaptive/self-paced dynamics are driven by observed
performance, never by canned values.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

import numpy as np


class CurriculumType(str, Enum):
    """Curriculum type."""

    LINEAR = "linear"
    EXPONENTIAL = "exponential"
    STEP = "step"
    ADAPTIVE = "adaptive"
    SELF_PACED = "self_paced"


@dataclass
class CurriculumConfig:
    """Curriculum configuration."""

    curriculum_type: CurriculumType = CurriculumType.LINEAR
    total_steps: int = 1000000
    start_difficulty: float = 0.0
    end_difficulty: float = 1.0
    step_size: float = 0.01
    threshold: float = 0.8  # performance to advance
    regress_threshold: float = 0.3  # performance below this regresses difficulty
    window_size: int = 100  # episodes averaged for gating
    seed: int = 0

    def __post_init__(self) -> None:
        if not 0.0 <= self.start_difficulty <= 1.0:
            raise ValueError("start_difficulty must be in [0, 1]")
        if not 0.0 <= self.end_difficulty <= 1.0:
            raise ValueError("end_difficulty must be in [0, 1]")
        if self.end_difficulty < self.start_difficulty:
            raise ValueError("end_difficulty cannot be below start_difficulty")
        if self.step_size <= 0.0:
            raise ValueError("step_size must be positive")
        if self.total_steps <= 0:
            raise ValueError("total_steps must be positive")
        if not 0.0 <= self.regress_threshold <= self.threshold <= 1.0:
            raise ValueError("thresholds must satisfy 0 <= regress <= threshold <= 1")
        if self.window_size <= 0:
            raise ValueError("window_size must be positive")


class Curriculum(ABC):
    """Base curriculum."""

    def __init__(self, config: CurriculumConfig):
        self.config = config
        self.current_step = 0
        self.current_difficulty = float(config.start_difficulty)
        self.performance_history: list[float] = []

    @abstractmethod
    def get_difficulty(self) -> float:
        raise NotImplementedError

    @abstractmethod
    def update(self, performance: float) -> None:
        raise NotImplementedError

    def step(self) -> None:
        self.current_step += 1

    def record(self, performance: float) -> None:
        """Record one episode's real performance into the windowed history."""
        if not np.isfinite(performance):
            raise ValueError("performance must be finite")
        self.performance_history.append(float(performance))
        if len(self.performance_history) > self.config.window_size:
            self.performance_history.pop(0)

    def recent_average(self) -> float | None:
        """Mean performance over the current window (None until window full)."""
        if len(self.performance_history) < self.config.window_size:
            return None
        return float(np.mean(self.performance_history))

    def should_advance(self, recent_performance: float) -> bool:
        return float(recent_performance) >= self.config.threshold

    def should_regress(self, recent_performance: float) -> bool:
        return float(recent_performance) < self.config.regress_threshold


class LinearCurriculum(Curriculum):
    """Linear difficulty progression by step."""

    def get_difficulty(self) -> float:
        progress = min(self.current_step / max(self.config.total_steps, 1), 1.0)
        return self.config.start_difficulty + progress * (self.config.end_difficulty - self.config.start_difficulty)

    def update(self, performance: float) -> None:
        self.step()


class ExponentialCurriculum(Curriculum):
    """Exponential difficulty progression by step."""

    def get_difficulty(self) -> float:
        progress = min(self.current_step / max(self.config.total_steps, 1), 1.0)
        exp_progress = (np.exp(progress * 3) - 1) / (np.exp(3) - 1)
        return self.config.start_difficulty + exp_progress * (self.config.end_difficulty - self.config.start_difficulty)

    def update(self, performance: float) -> None:
        self.step()


class StepCurriculum(Curriculum):
    """Step-wise difficulty progression."""

    def __init__(self, config: CurriculumConfig, steps: list[int] | None = None):
        super().__init__(config)
        self.steps = sorted(steps or [250000, 500000, 750000])
        self.current_stage = 0

    def get_difficulty(self) -> float:
        if not self.steps:
            return self.config.end_difficulty
        stage_progress = min(self.current_stage / len(self.steps), 1.0)
        return self.config.start_difficulty + stage_progress * (self.config.end_difficulty - self.config.start_difficulty)

    def update(self, performance: float) -> None:
        self.step()
        while self.current_stage < len(self.steps) and self.current_step >= self.steps[self.current_stage]:
            self.current_stage += 1


class AdaptiveCurriculum(Curriculum):
    """Adaptive curriculum gated by real windowed performance.

    Advances by ``step_size`` when the window average >= threshold and the
    difficulty is below the ceiling; regresses when the window average drops
    below regress_threshold (performance collapse signals the task became too
    hard). Difficulty is always clamped to [start_difficulty, end_difficulty].
    """

    def get_difficulty(self) -> float:
        return self.current_difficulty

    def update(self, performance: float) -> None:
        self.step()
        self.record(performance)
        avg = self.recent_average()
        if avg is None or self.current_step % self.config.window_size != 0:
            return
        if self.should_advance(avg):
            self.current_difficulty = min(
                self.current_difficulty + self.config.step_size,
                self.config.end_difficulty,
            )
        elif self.should_regress(avg):
            self.current_difficulty = max(
                self.current_difficulty - self.config.step_size,
                self.config.start_difficulty,
            )


class SelfPacedCurriculum(Curriculum):
    """Self-paced curriculum learning (pace_function drives difficulty)."""

    def __init__(self, config: CurriculumConfig, pace_function: Callable | None = None):
        super().__init__(config)
        self.pace_function = pace_function or (lambda perf, diff: diff + 0.05 * (perf - 0.5))

    def get_difficulty(self) -> float:
        return self.current_difficulty

    def update(self, performance: float) -> None:
        self.step()
        self.record(performance)
        self.current_difficulty = float(
            np.clip(
                self.pace_function(float(performance), self.current_difficulty),
                self.config.start_difficulty,
                self.config.end_difficulty,
            )
        )


def create_curriculum(config: CurriculumConfig) -> Curriculum:
    """Factory to create curriculum."""
    if config.curriculum_type == CurriculumType.LINEAR:
        return LinearCurriculum(config)
    elif config.curriculum_type == CurriculumType.EXPONENTIAL:
        return ExponentialCurriculum(config)
    elif config.curriculum_type == CurriculumType.STEP:
        return StepCurriculum(config)
    elif config.curriculum_type == CurriculumType.ADAPTIVE:
        return AdaptiveCurriculum(config)
    elif config.curriculum_type == CurriculumType.SELF_PACED:
        return SelfPacedCurriculum(config)
    raise ValueError(f"unknown curriculum_type: {config.curriculum_type}")