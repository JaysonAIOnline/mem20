"""Braid provenance hook for mem20cviz.

Mirrors inference results into the shared mem20 braid ledger as signed,
content-addressed nodes. Reuses the exact import pattern as mem20ucgz's hook:
walk up to find braid_bridge.py, import the facade lazily, and NEVER fabricate a
receipt. If braid is unavailable, journal_inference raises BraidUnavailable.
"""
from __future__ import annotations

import os
import sys
from typing import Any, Optional


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
_braid_module = None
if _REPO_ROOT and _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
try:
    import importlib
    _braid_module = importlib.import_module("braid_bridge")
except Exception:  # pragma: no cover - depends on external ledger
    _braid_module = None


class BraidUnavailable(RuntimeError):
    pass


def braid_ok() -> bool:
    try:
        if _braid_module is None:
            return False
        _braid_module.status()
        return True
    except Exception:  # noqa: BLE001
        return False


def journal_inference(result: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    """Commit one inference result to the braid ledger.

    Returns the receipt {cid, depth, proof_hops, ok} or raises BraidUnavailable.
    """
    if _braid_module is None or not braid_ok():
        raise BraidUnavailable("braid ledger unavailable")
    sim = bool((result.get("metadata") or {}).get("simulated"))
    body = {
        "kind": "cv.infer.result",
        "capability": "cv.infer",
        "simulated": sim,
        "engine": (result.get("metadata") or {}).get("engine"),
        "n_objects": len(result.get("objects", [])),
        "input_mode": request.get("mode", "real"),
        "has_embedding": bool(result.get("embedding")),
        "result_digest": result.get("metadata", {}).get("contract_hash"),
    }
    return _braid_module.commit("write:fact", "capability:cv.infer", body)


def prove_cid(cid: str) -> bool:
    if _braid_module is None or not braid_ok():
        raise BraidUnavailable("braid ledger unavailable")
    return bool(_braid_module.prove(cid))