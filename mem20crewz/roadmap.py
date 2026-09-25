"""RoadmapRun — a Crew or Flow run IS a roadmap.

Persists each phase (task / flow step) as planned -> in_progress ->
completed|blocked to runtime/roadmaps/<name>.jsonl. The same file doubles as
the execution log / provenance: re-reading it shows exactly what ran and in
what order, which is the "crew run = roadmap" directive made real.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Optional

ROADMAP_DIR = os.path.join(os.path.dirname(__file__), "runtime", "roadmaps")

STATUS_PLANNED = "planned"
STATUS_IN_PROGRESS = "in_progress"
STATUS_COMPLETED = "completed"
STATUS_BLOCKED = "blocked"


@dataclass
class Roadmap:
    name: str
    root_dir: str = ROADMAP_DIR
    events: list = field(default_factory=list)

    @property
    def path(self) -> str:
        os.makedirs(self.root_dir, exist_ok=True)
        return os.path.join(self.root_dir, f"{self.name}.jsonl")

    def mark(self, phase: str, status: str, meta: Optional[dict] = None) -> dict:
        os.makedirs(self.root_dir, exist_ok=True)
        event = {
            "ts": time.time(),
            "phase": phase,
            "status": status,
            "meta": meta or {},
        }
        self.events.append(event)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")
        return event

    def running(self, phase: str) -> None:
        self.mark(phase, STATUS_IN_PROGRESS)

    def done(self, phase: str, **meta) -> dict:
        return self.mark(phase, STATUS_COMPLETED, meta=meta)

    def blocked(self, phase: str, reason: str = "") -> dict:
        return self.mark(phase, STATUS_BLOCKED, meta={"reason": reason})

    def view(self) -> list[dict]:
        path = self.path
        if not os.path.exists(path):
            return []
        out = []
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return out

    def phases_summary(self) -> dict:
        rows = self.view()
        summary: dict[str, dict] = {}
        for e in rows:
            summary[e["phase"]] = {"status": e["status"], "ts": e["ts"]}
        return summary

    def __enter__(self) -> "Roadmap":
        self.mark("__run__", STATUS_PLANNED)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        self.mark("__run__", STATUS_COMPLETED, meta={"error": str(exc) if exc else ""})