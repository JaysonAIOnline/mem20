"""Braid provenance hook for mem20ucgz (RM-001 Universal Capability Graph).

Mirrors capability/edge events from the SQLite event plane into the shared
mem20 braid ledger as signed, content-addressed nodes. Reuses the exact import
pattern the MCP server uses (repo root on sys.path, `braid_bridge` facade,
single persistent engine).

Honesty contract: this hook NEVER fabricates a receipt. If braid is not
importable or the engine cannot start, `available` is False and journal writes
raise BraidUnavailable. The local SQLite event plane still records the event;
the caller decides policy when the ledger is down.
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict, Optional

def _discover_repo_root() -> str:
    """Walk up from this file until a directory containing braid_bridge.py is found."""
    here = os.path.dirname(os.path.abspath(__file__))
    while True:
        if os.path.exists(os.path.join(here, "braid_bridge.py")):
            return here
        parent = os.path.dirname(here)
        if parent == here:
            return ""
        here = parent


_REPO_ROOT = _discover_repo_root()
if _REPO_ROOT and _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

BRAID_AVAILABLE = False
try:
    from braid_bridge import commit, prove, status as _braid_status  # type: ignore
    _braid_status()
    BRAID_AVAILABLE = True
except Exception:  # pragma: no cover - depends on external ledger
    BRAID_AVAILABLE = False


class BraidUnavailable(RuntimeError):
    """Raised when the braid ledger is not reachable and a journal write is requested."""


def braid_ok() -> bool:
    """True when the braid façade imports and its engine answers."""
    return BRAID_AVAILABLE


def journal_event(kind: str, entity_id: Optional[str], payload: Dict[str, Any]) -> Dict[str, Any]:
    """Commit an event node to braid. Returns the receipt dict {cid, depth, proof_hops, ok}.

    op = `write:capability` for capability/edge events, `write:fact` otherwise.
    target = `capability:<entity_id>` (or `event:<kind>` when no entity).
    """
    if not BRAID_AVAILABLE:
        raise BraidUnavailable("braid ledger unavailable (braid_bridge not importable / engine down)")
    op = "write:capability" if kind in ("capability.upserted", "capability.deleted", "edge.upserted") else "write:fact"
    target = f"capability:{entity_id}" if entity_id else f"event:{kind}"
    body = {"kind": kind, "entity_id": entity_id, "payload": payload}
    receipt = commit(op, target, body)
    if not receipt.get("ok"):
        raise BraidUnavailable(f"braid write denied for {op} {target}")
    return receipt


def prove_cid(cid: str) -> bool:
    """Tamper-evidence check: True iff cid resolves and precommit chain verifies."""
    if not BRAID_AVAILABLE:
        raise BraidUnavailable("braid ledger unavailable")
    return bool(prove(cid))