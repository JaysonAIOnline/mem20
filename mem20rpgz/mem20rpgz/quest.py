"""Quests, objectives, rewards, quest log."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .inventory import Item


@dataclass
class QuestObjective:
    """Single tracked objective inside a quest."""

    kind: str  # collect | kill | reach | talk
    target: str
    amount: int = 1
    current: int = 0

    def to_dict(self) -> Dict:
        return {"kind": self.kind, "target": self.target, "amount": self.amount, "current": self.current}

    @classmethod
    def from_dict(cls, d: Dict) -> "QuestObjective":
        return cls(**d)


@dataclass
class Quest:
    """A quest with chained objectives and rewards."""

    title: str
    objectives: List[QuestObjective] = field(default_factory=list)
    rewards: Dict = field(default_factory=dict)  # {"gold": int, "xp": int, "items": [names]}
    giver: str = ""
    active: bool = True
    completed: bool = False

    def progress(self, kind: Optional[str] = None, target: Optional[str] = None, amount: int = 1) -> bool:
        """Advance matching objectives; returns True if quest is now complete."""
        if self.completed or not self.active:
            return self.completed
        for obj in self.objectives:
            if (kind is None or obj.kind == kind) and (target is None or obj.target == target):
                obj.current = min(obj.amount, obj.current + amount)
        if all(o.current >= o.amount for o in self.objectives):
            self.completed = True
            self.active = False
        return self.completed

    @property
    def progress_pct(self) -> float:
        if not self.objectives:
            return 0.0
        return sum(o.current for o in self.objectives) / sum(o.amount for o in self.objectives)

    def to_dict(self) -> Dict:
        return {
            "title": self.title,
            "objectives": [o.to_dict() for o in self.objectives],
            "rewards": self.rewards,
            "giver": self.giver,
            "active": self.active,
            "completed": self.completed,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "Quest":
        q = cls(
            d["title"],
            [QuestObjective.from_dict(o) for o in d.get("objectives", [])],
            d.get("rewards", {}),
            d.get("giver", ""),
            d.get("active", True),
            d.get("completed", False),
        )
        return q


class QuestLog:
    """Tracks active and completed quests for a party."""

    def __init__(self, capacity: int = 16):
        self.capacity = capacity
        self.quests: List[Quest] = []

    def accept(self, quest: Quest) -> bool:
        if len(self.quests) >= self.capacity:
            return False
        self.quests.append(quest)
        return True

    def active_quests(self) -> List[Quest]:
        return [q for q in self.quests if q.active and not q.completed]

    def completed_quests(self) -> List[Quest]:
        return [q for q in self.quests if q.completed]

    def by_title(self, title: str) -> Optional[Quest]:
        return next((q for q in self.quests if q.title == title), None)

    def grant_rewards(self, quest: Quest) -> Dict:
        """Materialize quest rewards as a summary dict."""
        return {
            "gold": quest.rewards.get("gold", 0),
            "xp": quest.rewards.get("xp", 0),
            "items": [Item(name=n, kind="quest", value=1) for n in quest.rewards.get("items", [])],
        }

    def to_dict(self) -> Dict:
        return {"capacity": self.capacity, "quests": [q.to_dict() for q in self.quests]}

    @classmethod
    def from_dict(cls, d: Dict) -> "QuestLog":
        log = cls(d.get("capacity", 16))
        log.quests = [Quest.from_dict(q) for q in d.get("quests", [])]
        return log