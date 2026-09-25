"""workflow_twin — Personal Workflow Twin (RM-140/141, RM-008).

Reads the live Pickle self-model (topic=self_model in the mem20 memory store)
and recent memory threads to produce a personal workflow digest: identity
snapshot, active threads, recommendations. All inputs are read from the real
estate — never hardcoded. Hermetic in tests via injected rows.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Any

MEM20_STORE = os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store"))


def _load_memory_module():
    if MEM20_STORE not in sys.path:
        sys.path.insert(0, MEM20_STORE)
    from memory import recall

    return recall


@dataclass
class WorkflowDigest:
    identity: str
    active_threads: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity,
            "active_threads": self.active_threads,
            "recommendations": self.recommendations,
        }


class WorkflowTwin:
    def __init__(self, self_model_rows: list[dict[str, Any]] | None = None,
                 memory_rows: list[dict[str, Any]] | None = None) -> None:
        self._self_model_rows = self_model_rows
        self._memory_rows = memory_rows

    def _live_rows(self, topic: str) -> list[dict[str, Any]]:
        recall = _load_memory_module()
        try:
            return recall(topic=topic, k=3)
        except Exception:
            return []

    def digest(self) -> WorkflowDigest:
        if self._self_model_rows is not None:
            sm_rows = self._self_model_rows
        else:
            sm_rows = self._live_rows("self_model")
        identity = "Pickle agent"
        smats = sm_rows[0].get("content", "") if sm_rows else ""
        if "Self-Model:" in smats:
            identity = smats.split("Self-Model:", 1)[1][:300]
        elif smats:
            identity = smats[:300]
        if self._memory_rows is not None:
            mem_rows = self._memory_rows
        else:
            mem_rows = self._live_rows(None)
        threads = [r.get("content", "")[:160] for r in mem_rows[:5]]
        rec = []
        for t in threads:
            rec.append(f"follow up on: {t[:70]}")
        rec.append("export verified results to braid + CONFWORK.md before claiming done")
        return WorkflowDigest(identity=identity, active_threads=threads, recommendations=rec)