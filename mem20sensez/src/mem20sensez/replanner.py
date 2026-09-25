"""replanner — Dynamic Phase Replanner (RM-199).

Given a goal, the current roadmap phases, and the live capability gaps from the
gap mapper, produce a re-planned phase graph:
  - every phase keeps its identity/rank,
  - matched capabilities are pinned as "covered" resources,
  - missing tokens become explicit "gap" nodes that must be resolved before
    the phase is considered executable,
  - a revised order is derived from gap dependencies (phases with fewer gaps
    first — a monotone refinement, not a random shuffle).

The re-plan is deterministic and braid-versioned: the caller receives a
`plan_id` (sha256 of the plan) plus a braid receipt when journaling is on.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from .gapper import GapReport


@dataclass
class ReplannedPhase:
    name: str
    status: str  # ready | needs-gap-fill
    captured: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)


@dataclass
class Replan:
    goal: str
    phases: list[ReplannedPhase]
    order: list[str]
    plan_id: str
    braid: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "phases": [p.__dict__ for p in self.phases],
            "order": self.order,
            "plan_id": self.plan_id,
            "braid": self.braid,
        }


class PhaseReplanner:
    def __init__(self, phases: list[str]) -> None:
        self.phases = phases

    def replan(self, report: GapReport, journal: bool = False) -> Replan:
        # Capture: tokens the goal covered map to capabilities; gaps stay gaps.
        replanned: list[ReplannedPhase] = []
        for _, name in enumerate(self.phases):
            gaps = [g for g in report.missing_tokens if g]
            captured = [c["id"] for c in report.matched]
            replanned.append(ReplannedPhase(name=name,
                                            status="needs-gap-fill" if gaps else "ready",
                                            captured=captured,
                                            gaps=gaps))
        # Revised order: phases with zero gaps first, then fewest gaps. Stable sort.
        ordered = sorted(replanned, key=lambda p: (0 if p.status == "ready" else 1, len(p.gaps)))
        order = [p.name for p in ordered]
        plan_id = hashlib.sha256(json.dumps({
            "goal": report.goal,
            "phases": [p.__dict__ for p in replanned],
        }, sort_keys=True).encode()).hexdigest()[:16]
        replan = Replan(goal=report.goal, phases=replanned, order=order, plan_id=plan_id)
        if journal:
            from .braid_hook import journal
            replan.braid = journal("phase.replan", plan_id, replan.to_dict())
        return replan