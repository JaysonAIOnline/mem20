"""Braid provenance hook for mem20sensez (mem30 Phase 1 sense-organs).

Mirrors the mem20ucgz pattern: walk up to the repo root, import the braid
facade, journal events as signed content-addressed nodes. Honesty contract:
never fabricate a receipt — if the ledger is down, raise BraidUnavailable.
"""
from __future__ import annotations

import os
import sys
from typing import Any


def _discover_repo_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    while True:
        if os.path.exists(os.path.join(here, "braid_bridge.py")):
            return here
        parent = os.path.dirname(here)
        if parent == here:
            return ""
        here = parent


_REPO_ROOT = _discover_repo_root()
_ADDED_REPO_ROOT = False
if _REPO_ROOT and _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
    _ADDED_REPO_ROOT = True

BRAID_AVAILABLE = False
try:
    from braid_bridge import commit, head, prove, read  # type: ignore
    from braid_bridge import status as _braid_status

    _braid_status()
    BRAID_AVAILABLE = True
except Exception:  # pragma: no cover - depends on external ledger
    BRAID_AVAILABLE = False
finally:
    # Do not keep the repo root on sys.path after importing braid_bridge:
    # /opt/mem20 contains namespace-style package directories (mem20langz/,
    # mem20orcaz/...) that would shadow the venv editable installs and break
    # `from mem20langz import ...` downstream.
    if _ADDED_REPO_ROOT and _REPO_ROOT in sys.path:
        try:
            sys.path.remove(_REPO_ROOT)
        except ValueError:  # pragma: no cover
            pass


class BraidUnavailable(RuntimeError):
    """Raised when the braid ledger is not reachable and a journal write is requested."""


def braid_ok() -> bool:
    return BRAID_AVAILABLE


def journal(kind: str, entity_id: str | None, payload: dict[str, Any]) -> dict[str, Any]:
    """Commit a sense-organ event node to braid. Returns {cid, depth, proof_hops, ok}."""
    if not BRAID_AVAILABLE:
        raise BraidUnavailable("braid ledger unavailable (braid_bridge not importable / engine down)")
    op = "write:capability" if kind in ("capability.upserted", "capability.deleted", "edge.upserted") else "write:fact"
    target = f"sense:{entity_id}" if entity_id else f"event:{kind}"
    body = {"kind": kind, "entity_id": entity_id, "payload": payload}
    receipt = commit(op, target, body)
    if not receipt.get("ok"):
        raise BraidUnavailable(f"braid write denied for {op} {target}")
    return receipt


def prove_cid(cid: str) -> bool:
    if not BRAID_AVAILABLE:
        raise BraidUnavailable("braid ledger unavailable")
    return bool(prove(cid))


def lookup(cid: str) -> dict[str, Any]:
    """Read a braid node by cid through the real ledger. Raises BraidUnavailable
    if the ledger is down or the cid is unknown (never a fabricated receipt)."""
    if not BRAID_AVAILABLE:
        raise BraidUnavailable("braid ledger unavailable")
    node = read(cid)
    if node is None:
        raise BraidUnavailable(f"no node with cid {cid!r} in the braid ledger")
    return node


def head_node() -> dict[str, Any]:
    """Return the head of the real braid ledger, or raise BraidUnavailable."""
    if not BRAID_AVAILABLE:
        raise BraidUnavailable("braid ledger unavailable")
    node = head()
    if node is None:
        raise BraidUnavailable("braid ledger is empty")
    return node