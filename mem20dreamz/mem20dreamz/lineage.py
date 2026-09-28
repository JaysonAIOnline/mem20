"""Dream lineage: the state a dream accumulates across iterations.

The defect this replaces: the old loop set ``seed = out[:300]``, so iteration N
read a 300-character tail of iteration N-1. That is condense-and-resample, not
iteration - early structure cannot survive, and there is no state to improve.

A lineage keeps:

* ``artifact`` - the current best, in full, never truncated
* ``changelog`` - what each iteration changed and why
* ``inventions`` - first-class entries for things imagined that do not exist yet
* ``dreamer`` - this lineage's own config, which evolves (panel roster, rubrics,
  a technique library). Per lineage, never global: a global update would leak one
  dream's voice into every other dream.
* ``iterations`` - every version retained, so any point is rewindable
* ``score_history`` - the falsifiable record that iteration 30 beat iteration 5

Panelists with smaller context windows get a *fitted* digest rather than a
truncated one, so a 8k-context panelist is not handed something it cannot hold.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any

STORE = os.environ.get("MEM20DREAM_STORE", "/opt/mem20/store/dreams")

MAX_ITERATIONS_KEPT = 500


@dataclass
class Inventions:
    """Things imagined that do not exist yet, kept separate from the artifact.

    Kept as first-class entries rather than blended into prose, so a promotion
    pack can name a capability that was invented rather than one that was merely
    described.
    """

    entries: list[dict[str, Any]] = field(default_factory=list)

    def add(self, name: str, description: str, smallest_real_version: str, source_iteration: int) -> None:
        entry = {
            "name": name,
            "description": description,
            "smallest_real_version": smallest_real_version,
            "source_iteration": source_iteration,
            "found_at": time.time(),
        }
        if not any(e["name"].lower() == name.lower() for e in self.entries):
            self.entries.append(entry)

    def as_list(self) -> list[dict[str, Any]]:
        return list(self.entries)


@dataclass
class DreamerConfig:
    """The dreamer's own evolving configuration. This is the self-improvement."""

    #: What the dreamer has learned about how to dream *this* lineage.
    techniques: list[str] = field(default_factory=list)
    #: Panel-role focus overrides the dreamer has sharpened over iterations.
    focus_overrides: dict[str, str] = field(default_factory=dict)
    #: Free-form guidance carried forward, e.g. "stop rewriting the hero copy".
    guidance: list[str] = field(default_factory=list)
    evolved_at_iteration: int = 0

    def add_technique(self, text: str) -> None:
        if text.strip() and text.strip() not in self.techniques:
            self.techniques.append(text.strip())

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Iteration:
    n: int
    artifact: str
    fidelity: dict[str, Any]
    omission: dict[str, Any]
    forecast: dict[str, Any]
    critiques: list[dict[str, Any]]
    inventions_added: list[str]
    dreamer_evolved: bool
    accepted: bool
    rejection_reason: str = ""
    #: Every candidate considered, its scores, and why the winner won. Retained
    #: so a regression is visible in the record instead of hidden by the ratchet.
    selection: dict[str, Any] = field(default_factory=dict)
    at: float = field(default_factory=time.time)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Lineage:
    """One dream, from seed to wherever it has got to."""

    dream_id: str
    seed: str
    kind: str = "active"  # active | idle_prototype | idle_proposal | idle_idea
    artifact: str = ""
    foundation: str = ""  # the premise, amendable only by a foundation revision
    changelog: list[dict[str, Any]] = field(default_factory=list)
    inventions: Inventions = field(default_factory=Inventions)
    dreamer: DreamerConfig = field(default_factory=DreamerConfig)
    iterations: list[Iteration] = field(default_factory=list)
    score_history: list[dict[str, Any]] = field(default_factory=list)
    foundation_revisions: list[dict[str, Any]] = field(default_factory=list)
    #: One braid cid per iteration, in order. Braid's own chain is global and
    #: interleaved with every other write, so this list is what makes a specific
    #: iteration rewindable: read the cid, get the artifact back.
    braid_cids: list[str] = field(default_factory=list)
    #: Commits that did NOT happen, with reasons. Recorded so a lineage can never
    #: look fully content-addressed when it is not.
    uncommitted: list[dict[str, Any]] = field(default_factory=list)
    #: Set when an audit finds this lineage contains an iteration that recorded
    #: provider errors instead of real work. The node stays in braid — the
    #: ledger is append-only and the signature is valid — but it is marked here
    #: so nobody later mistakes a failed call for a dream that happened.
    hollow: dict[str, Any] | None = None
    paused: bool = False
    pause_reason: str = ""
    done: bool = False
    created_at: float = field(default_factory=time.time)

    # --- paths -------------------------------------------------------------

    @property
    def dir(self) -> str:
        return os.path.join(STORE, self.dream_id)

    @property
    def state_path(self) -> str:
        return os.path.join(self.dir, "lineage.json")

    # --- persistence -------------------------------------------------------

    def save(self) -> str:
        os.makedirs(self.dir, exist_ok=True)
        tmp = self.state_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(self.as_dict(), handle, indent=2)
        os.replace(tmp, self.state_path)
        return self.state_path

    @classmethod
    def load(cls, dream_id: str) -> Lineage | None:
        path = os.path.join(STORE, dream_id, "lineage.json")
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Lineage:
        lineage = cls(
            dream_id=data["dream_id"],
            seed=data.get("seed", ""),
            kind=data.get("kind", "active"),
            artifact=data.get("artifact", ""),
            foundation=data.get("foundation", ""),
            changelog=data.get("changelog", []),
            inventions=Inventions(entries=data.get("inventions", {}).get("entries", [])),
            dreamer=DreamerConfig(**data.get("dreamer", {})),
            score_history=data.get("score_history", []),
            foundation_revisions=data.get("foundation_revisions", []),
            braid_cids=data.get("braid_cids", []),
            uncommitted=data.get("uncommitted", []),
            hollow=data.get("hollow"),
            paused=data.get("paused", False),
            pause_reason=data.get("pause_reason", ""),
            done=data.get("done", False),
            created_at=data.get("created_at", time.time()),
        )
        for raw in data.get("iterations", []):
            lineage.iterations.append(Iteration(**raw))
        return lineage

    def as_dict(self) -> dict[str, Any]:
        return {
            "dream_id": self.dream_id,
            "seed": self.seed,
            "kind": self.kind,
            "artifact": self.artifact,
            "foundation": self.foundation,
            "changelog": self.changelog,
            "inventions": {"entries": self.inventions.as_list()},
            "dreamer": self.dreamer.as_dict(),
            "iterations": [i.as_dict() for i in self.iterations[-MAX_ITERATIONS_KEPT:]],
            "score_history": self.score_history,
            "foundation_revisions": self.foundation_revisions,
            "braid_cids": self.braid_cids,
            "uncommitted": self.uncommitted,
            "hollow": self.hollow,
            "paused": self.paused,
            "pause_reason": self.pause_reason,
            "done": self.done,
            "created_at": self.created_at,
        }

    # --- iteration bookkeeping --------------------------------------------

    @property
    def iteration_count(self) -> int:
        return len(self.iterations)

    def current_artifact(self) -> str:
        """Never a truncated tail. This is the whole point of the rewrite."""
        return self.artifact or self.seed

    def lineage_digest(self, budget: int) -> str:
        """A *fitted* digest of everything so far, sized to a panelist's context.

        Newest first, because recency is what matters for improvement, and
        truncated at whole-entry boundaries so an entry is never cut in half
        into something misleading.
        """
        lines = [f"LINEAGE DIGEST ({self.iteration_count} iterations so far)"]
        for entry in reversed(self.changelog[-40:]):
            lines.append(f"  iter {entry['n']}: {entry['change']}")
        if self.dreamer.guidance:
            lines.append("  dreamer guidance: " + "; ".join(self.dreamer.guidance[-6:]))
        if self.dreamer.techniques:
            lines.append("  techniques: " + "; ".join(self.dreamer.techniques[-6:]))
        text = "\n".join(lines)
        if len(text) <= budget:
            return text
        # `lines[1:]` is already newest-first (built with reversed() above), so
        # it is walked as-is. Reversing it again would silently order the digest
        # oldest-first, showing a panelist the least recent work.
        kept: list[str] = [lines[0] + f" (fitted to {budget} chars, showing the most recent)"]
        for line in lines[1:]:
            if sum(len(x) + 1 for x in kept) + len(line) > budget:
                break
            kept.append(line)
        return "\n".join(kept)

    def record(self, iteration: Iteration) -> None:
        self.iterations.append(iteration)
        self.score_history.append(
            {
                "n": iteration.n,
                "fidelity": iteration.fidelity.get("score"),
                "omission": iteration.omission.get("score"),
                "artifact_chars": len(iteration.artifact),
                "forecast": {k: v.get("score") for k, v in iteration.forecast.items()},
                "accepted": iteration.accepted,
                "at": iteration.at,
            }
        )
        self.changelog.append(
            {
                "n": iteration.n,
                "change": (iteration.omission.get("summary") or iteration.rejection_reason or "")[:300],
                "accepted": iteration.accepted,
                "at": iteration.at,
            }
        )

    def best(self) -> Iteration | None:
        accepted = [i for i in self.iterations if i.accepted]
        return accepted[-1] if accepted else None

    def status(self) -> dict[str, Any]:
        return {
            "dream_id": self.dream_id,
            "kind": self.kind,
            "iterations": self.iteration_count,
            "paused": self.paused,
            "pause_reason": self.pause_reason,
            "done": self.done,
            "inventions": len(self.inventions.entries),
            "techniques": len(self.dreamer.techniques),
            "foundation_revisions": len(self.foundation_revisions),
            "last_scores": self.score_history[-1] if self.score_history else None,
            "braid_committed": len(self.braid_cids),
            "braid_uncommitted": len(self.uncommitted),
        }


def list_lineages(kind: str = "") -> list[dict[str, Any]]:
    if not os.path.isdir(STORE):
        return []
    out: list[dict[str, Any]] = []
    for entry in sorted(os.listdir(STORE)):
        lineage = Lineage.load(entry)
        if lineage is None:
            continue
        if kind and lineage.kind != kind:
            continue
        out.append(lineage.status())
    return out
