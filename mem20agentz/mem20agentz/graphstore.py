"""OREO graph store on the mem20 substrate (phase 03 sub-phase 3.2).

Graphs (GIR or architecture) are serialized to JSON via the OREO Graph
`to_dict`/`from_dict` contract and persisted as substrate facts tagged
``mem20agentz`` + ``oreo_graph`` — the same seams `backup export` already
reads, so stored graphs round-trip in a backup without a new export path.
All followers of the phase discipline: the backend seam is injectable so
tests stay hermetic (sealed backend + hooks like every other module).
"""

from __future__ import annotations

import json
from typing import Any, Optional

TOPIC_PREFIX = "oreo:graph:"
TAGS = ["mem20agentz", "oreo_graph"]


class GraphStore:
    def __init__(self, backend=None) -> None:
        self.backend = backend

    # ------------------------------------------------------------ helpers
    def _topic(self, name: str) -> str:
        return f"{TOPIC_PREFIX}{name}"

    def _require_backend(self):
        if self.backend is None:
            raise RuntimeError("no substrate backend (GraphStore.backend)")
        return self.backend

    def _payload_for(self, graph, kind: str, meta: Optional[dict] = None) -> str:
        doc = graph.to_dict() if hasattr(graph, "to_dict") else graph
        if isinstance(doc, dict):
            name = doc.get("name", "")
        else:
            name = getattr(doc, "name", "")
        return json.dumps({
            "kind": kind,
            "name": name,
            "meta": meta or {},
            "graph": doc,
        }, sort_keys=True, default=str)

    # ------------------------------------------------------------ persist
    def save(self, name: str, graph, kind: str = "gir",
             meta: Optional[dict] = None, actor: str = "agent") -> dict:
        backend = self._require_backend()
        result = backend.remember(
            topic=self._topic(name),
            content=self._payload_for(graph, kind, meta),
            tags=TAGS + [kind],
            actor=actor,
            epistemic_status="observed")
        return {"ok": True, "name": name, "kind": kind,
                "remember": result.get("ok", True)}

    def get(self, name: str) -> Optional[dict]:
        backend = self._require_backend()
        hits = backend.recall(topic=self._topic(name), tags=TAGS, k=5)
        if not hits:
            return None
        latest = hits[0]
        try:
            payload = json.loads(latest.get("content") or latest.get("text") or "{}")
        except ValueError:
            return {"name": name, "error": "stored graph is corrupt JSON"}
        return payload

    def list(self, kind: Optional[str] = None) -> list[dict]:
        backend = self._require_backend()
        tags = TAGS + ([kind] if kind else [])
        hits = backend.recall(topic=TOPIC_PREFIX, tags=tags, k=200)
        names: dict[str, dict] = {}
        for h in hits:
            topic = h.get("topic", "")
            if not topic.startswith(TOPIC_PREFIX):
                continue
            name = topic[len(TOPIC_PREFIX):]
            if name not in names:
                names[name] = {
                    "name": name,
                    "kind": "gir",
                    "stored_at": h.get("created_at") or h.get("timestamp"),
                }
        return sorted(names.values(), key=lambda r: r["name"])

    def delete(self, name: str) -> dict:
        return {"ok": False, "error": "delete not implemented on substrate "
                                      "facts (no destructive seam)"}