"""gapper — Capability Gap Mapper (RM-200).

Given a human goal, tokenize it and score every registered UCG capability for
coverage of that goal's vocabulary. The result is:
  - matched: capabilities whose outputs/tags cover the goal tokens
  - missing: goal tokens no capability covers (the honest capability gap)
This is REAL matching over the live UCG — no fabricated capability sets.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .ucg_client import UcgClient, tokenize


@dataclass
class GapReport:
    goal: str
    matched: list[dict[str, Any]] = field(default_factory=list)
    missing_tokens: list[str] = field(default_factory=list)
    uncovered_outputs: list[str] = field(default_factory=list)
    coverage_ratio: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "matched": self.matched,
            "missing_tokens": self.missing_tokens,
            "uncovered_outputs": self.uncovered_outputs,
            "coverage_ratio": round(self.coverage_ratio, 4),
        }


def _haystack(cap: dict[str, Any]) -> str:
    tags = cap.get("metadata", {}).get("tags", []) or []
    inputs = cap.get("inputs", []) or []
    outputs = cap.get("outputs", []) or []
    parts = [
        cap.get("id", ""),
        cap.get("name", ""),
        cap.get("provider", ""),
    ]
    parts.extend(tags)
    parts.extend(inputs)
    parts.extend(outputs)
    return " ".join(parts).lower().replace("-", " ").replace("/", " ").replace(".", " ")


class GapMapper:
    def __init__(self, client: UcgClient) -> None:
        self.client = client

    def map(self, goal: str) -> GapReport:
        tokens = [t for t in tokenize(goal) if t]
        if not tokens:
            return GapReport(goal=goal, coverage_ratio=0.0)
        caps = self.client.all(active_only=True)
        covered: set[str] = set()
        matched: list[dict[str, Any]] = []
        for cap in caps:
            hay = _haystack(cap)
            hit_tokens = [t for t in tokens if t in hay]
            if hit_tokens:
                matched.append({**cap, "_hit_tokens": hit_tokens})
                covered.update(hit_tokens)
        missing = [t for t in tokens if t not in covered]
        uncovered_outputs: list[str] = []
        for t in missing:
            # an output type may exist that no token names directly — surface it
            for cap in caps:
                for out in cap.get("outputs", []):
                    if t in out.lower().replace("-", " ").replace("/", " "):
                        uncovered_outputs.append(out)
        ratio = len(covered) / len(tokens) if tokens else 0.0
        return GapReport(
            goal=goal,
            matched=matched,
            missing_tokens=missing,
            uncovered_outputs=sorted(set(uncovered_outputs)),
            coverage_ratio=ratio,
        )