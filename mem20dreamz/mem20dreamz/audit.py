"""Find dream iterations that recorded a failed call instead of real work.

A provider outage used to produce an "iteration" with zero critiques and zero
inventions: the engine stored the error honestly but still committed the node.
Those nodes are validly signed and sit in the ledger looking like dreams, which
is the worst kind of wrong — a reader cannot tell a real dream from a dead one.

Braid is append-only, so the honest repair is not deletion. It is:

  * mark the lineage locally, so nothing presents it as a real dream, and
  * commit one braid record naming every affected lineage and why, so the
    ledger itself carries the correction.

This module is read-only unless you ask it to record. `find_hollow` never writes.
"""

from __future__ import annotations

import time
from typing import Any

from . import ledger
from .lineage import Lineage, list_lineages

#: An iteration counts as hollow when it recorded provider errors and produced no
#: critique at all. One error alongside real work is not hollow; it is a partial.
MARKER_OP = "write:dream_quarantine"


def _is_hollow(iteration: Any) -> tuple[bool, str]:
    critiques = iteration.critiques or []
    errors = [c for c in critiques if c.get("kind") == "errors"]
    real = [c for c in critiques if c.get("kind") in {"critique", "skeptic"}]
    if real or not errors:
        return False, ""
    reason = (errors[0].get("text") or "").strip()
    return True, reason[:300]


def find_hollow() -> list[dict[str, Any]]:
    """Every lineage holding an iteration that was a failed call, not a dream."""
    found: list[dict[str, Any]] = []
    for row in list_lineages():
        lineage = Lineage.load(row["dream_id"])
        if lineage is None:
            continue
        hollow_iters = []
        for iteration in lineage.iterations:
            hollow, reason = _is_hollow(iteration)
            if hollow:
                hollow_iters.append(
                    {
                        "n": iteration.n,
                        "reason": reason,
                        "artifact_chars": len(iteration.artifact or ""),
                        "inventions": len(iteration.inventions_added),
                    }
                )
        if hollow_iters:
            found.append(
                {
                    "dream_id": lineage.dream_id,
                    "kind": lineage.kind,
                    "hollow_iterations": hollow_iters,
                    "braid_cids": list(lineage.braid_cids),
                    "total_inventions": len(lineage.inventions.entries),
                    "already_marked": lineage.hollow is not None,
                }
            )
    return found


def mark_local(entries: list[dict[str, Any]]) -> int:
    """Stamp the lineages on disk. Returns how many were newly marked."""
    newly = 0
    for entry in entries:
        lineage = Lineage.load(entry["dream_id"])
        if lineage is None or lineage.hollow is not None:
            continue
        first = entry["hollow_iterations"][0]
        lineage.hollow = {
            "marked_at": time.time(),
            "why": "iteration recorded provider errors instead of a panel result",
            "iterations": [i["n"] for i in entry["hollow_iterations"]],
            "first_reason": first["reason"],
            "real_dream": False,
        }
        lineage.save()
        newly += 1
    return newly


def commit_record(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Write the correction into braid, so the ledger carries it too."""
    if not entries:
        return {"committed": False, "reason": "nothing to record"}
    body = {
        "audit": "hollow_iterations",
        "count": len(entries),
        "why": (
            "iterations that recorded provider errors instead of a panel result; "
            "the nodes are validly signed and left in place because the ledger is "
            "append-only, but they are not dreams"
        ),
        "lineages": [
            {
                "dream_id": e["dream_id"],
                "kind": e["kind"],
                "hollow_iterations": e["hollow_iterations"],
                "braid_cids": e["braid_cids"],
            }
            for e in entries
        ],
        "recorded_at": time.time(),
    }
    return ledger.commit_raw(MARKER_OP, "dream:_audit", body)


def quarantine(commit: bool = True) -> dict[str, Any]:
    """Mark locally, and (by default) record the correction in braid."""
    entries = find_hollow()
    newly = mark_local(entries)
    receipt: dict[str, Any] = {"committed": False, "reason": "recording not requested"}
    if commit and entries:
        receipt = commit_record(entries)
    return {
        "hollow_lineages": len(entries),
        "newly_marked": newly,
        "hollow_iterations": sum(len(e["hollow_iterations"]) for e in entries),
        "inventions_lost": sum(e["total_inventions"] for e in entries),
        "braid": receipt,
        "entries": entries,
    }
