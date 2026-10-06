"""Verified facts.

Every claim that reaches a generated onboarding pack flows through a `Fact`.
A fact carries the source it came from and the time it was verified, so a later
`verify` run can tell truth from drift instead of trusting the document.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field, asdict
from typing import Any


def _utcnow() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class Fact:
    """A single verified claim about the host."""

    key: str
    value: Any
    kind: str
    source: str
    verified_at: str = field(default_factory=_utcnow)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict) -> "Fact":
        return cls(
            key=raw["key"],
            value=raw["value"],
            kind=raw["kind"],
            source=raw["source"],
            verified_at=raw["verified_at"],
        )

    def headline(self) -> str:
        """Single-line rendering used in the markdown tables."""
        if isinstance(self.value, list):
            return f"{len(self.value)} item(s)"
        return str(self.value)


@dataclass
class FactSet:
    """An ordered, de-duplicated collection of facts."""

    facts: list[Fact] = field(default_factory=list)

    def add(self, key: str, value: Any, kind: str, source: str) -> Fact:
        fact = Fact(key=key, value=value, kind=kind, source=source)
        self.facts.append(fact)
        return fact

    def get(self, key: str) -> Fact | None:
        for fact in self.facts:
            if fact.key == key:
                return fact
        return None

    def by_kind(self, kind: str) -> list[Fact]:
        return [f for f in self.facts if f.kind == kind]

    def to_list(self) -> list[dict]:
        return [f.to_dict() for f in self.facts]

    def __len__(self) -> int:
        return len(self.facts)

    def __iter__(self):
        return iter(self.facts)