"""Utility AI — native absorption of UniKit utility AI."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple
import math
import uuid


@dataclass
class Consideration:
    """Single consideration for utility scoring."""
    name: str
    score_fn: Callable[[Dict], float]
    weight: float = 1.0
    curve: str = "linear"  # linear, exponential, logistic, step

    def evaluate(self, context: Dict) -> float:
        raw_score = self.score_fn(context)
        return self._apply_curve(raw_score) * self.weight

    def _apply_curve(self, score: float) -> float:
        if self.curve == "linear":
            return max(0.0, min(1.0, score))
        elif self.curve == "exponential":
            return max(0.0, min(1.0, score ** 2))
        elif self.curve == "logistic":
            return 1.0 / (1.0 + math.exp(-10 * (score - 0.5)))
        elif self.curve == "step":
            return 1.0 if score > 0.5 else 0.0
        return max(0.0, min(1.0, score))


@dataclass
class UtilityAction:
    """Action with utility considerations."""
    name: str
    considerations: List[Any] = field(default_factory=list)
    cooldown: float = 0.0
    last_used: float = 0.0

    def evaluate(self, context: Dict) -> float:
        if not self.considerations:
            return 0.0
        total = sum(c.evaluate(context) for c in self.considerations)
        return total / len(self.considerations)

    def is_on_cooldown(self, current_time: float) -> bool:
        return (current_time - self.last_used) < self.cooldown

    def use(self, current_time: float):
        self.last_used = current_time


class UtilityScorer:
    """Utility scorer — evaluates and selects best action."""

    def __init__(self):
        self.actions: Dict[str, Any] = {}

    def add_action(self, action: Any) -> None:
        self.actions[action.name] = action

    def score_all(self, context: Dict) -> Dict[str, float]:
        """Score all actions."""
        scores = {}
        for name, action in self.actions.items():
            scores[name] = action.evaluate(context)
        return scores

    def get_best_action(self, context: Dict, exclude: Set[str] = None) -> Optional[str]:
        """Get highest scoring action."""
        exclude = exclude or set()
        best_name = None
        best_score = -float('inf')
        for name, action in self.actions.items():
            if name in exclude:
                continue
            if action.is_on_cooldown(context.get("time", 0)):
                continue
            score = action.evaluate(context)
            if score > best_score:
                best_score = score
                best_name = name
        return best_name

    def get_ranked_actions(self, context: Dict) -> List[Tuple[str, float]]:
        """Get all actions ranked by score."""
        scores = self.score_all(context)
        return sorted(scores.items(), key=lambda x: x[1], reverse=True)


def create_consideration(
    name: str,
    score_fn: Callable[[Dict], float],
    weight: float = 1.0,
    curve: str = "linear",
) -> Any:
    """Factory to create consideration."""
    from types import SimpleNamespace
    c = SimpleNamespace()
    c.name = name
    c.score_fn = score_fn
    c.weight = weight
    c.curve = curve
    c.evaluate = lambda ctx: c._apply_curve(score_fn(ctx)) * weight
    c._apply_curve = lambda s: (
        max(0.0, min(1.0, s)) if "linear" == "linear" else
        max(0.0, min(1.0, s ** 2)) if "exponential" == "exponential" else
        1.0 / (1.0 + math.exp(-10 * (s - 0.5))) if "logistic" == "logistic" else
        1.0 if s > 0.5 else 0.0
    )
    return c


class UtilityReasoner:
    """Full utility reasoning system."""

    def __init__(self):
        self.scorer = UtilityScorer()
        self.blackboard: Dict[str, Any] = {}

    def add_action(self, name: str, considerations: List[Tuple[str, Callable, float]] = None):
        """Add action with considerations."""
        from types import SimpleNamespace
        action = SimpleNamespace()
        action.name = name
        action.considerations = []
        action.cooldown = 0.0
        action.last_used = 0.0
        action.evaluate = lambda ctx: sum(
            c["fn"](self.blackboard) * c["weight"] for c in action.considerations
        ) / max(len(action.considerations), 1)
        action.is_on_cooldown = lambda t: (t - action.last_used) < action.cooldown
        action.use = lambda t: setattr(action, "last_used", t)

        if considerations:
            for name, fn, weight in considerations:
                action.considerations.append({"name": name, "fn": fn, "weight": weight})

        self.scorer.add_action(action)

    def decide(self, context: Dict = None) -> Optional[str]:
        """Decide best action."""
        context = context or self.blackboard
        return self.scorer.get_best_action(context)

    def tick(self, dt: float = 1.0):
        """Update internal state."""
        pass