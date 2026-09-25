#!/usr/bin/env python3
"""
braid_bridge — Pythonic facade over the braid_python Rust core.

Loads a single persistent BraidEngine (a content-addressed, signed, append-only
ledger), a genesis policy snapshot, and exposes high-level, honest operations:

  * identity / key management        -> BraidEngine.generate_signer(), engine.id_hex()
  * signed, proven writes            -> commit(op, target, payload, cap=...)
  * tamper-evident reads             -> read(cid), head(), prove(cid)
  * intent ledger                    -> intent_submit(...), intent_view(...)
  * content hashing                  -> hash_data(...), verify_signature(...)
  * fact-commitment helpers          -> commit_fact(topic, content, metadata)

The bridge is a singleton per (log_path, signer) so every subsystem that calls
braid shares ONE ledger and ONE signer thread-safely.  If braid_python is not
importable, BRAID_AVAILABLE is False and every call raises BraidUnavailable —
the bridge never fabricates receipts.
"""
from __future__ import annotations

import os
import json
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_LOG_DIR = os.environ.get(
    "MEM20_BRAID_DIR",
    os.environ.get("MEM20_STORE_PATH", "/opt/mem20/store/braid"),
)
DEFAULT_LOG_PATH = os.path.join(DEFAULT_LOG_DIR, "mem20.braid")
SIGNER_PATH = os.path.join(DEFAULT_LOG_DIR, "signer.hex")

# The genesis capability used for write paths when the caller does not pass one.
DEFAULT_CAP = "agent:write:*"

# Snapshot cids registered lazily (in-memory) when the engine is first started.
GENESIS_SNAPSHOT_CID = "snap-genesis-1"


class BraidUnavailable(RuntimeError):
    """Raised when braid_python is not importable or the engine is not started."""


class BraidWriteError(RuntimeError):
    """Raised when a braid write is denied or fails to commit."""


# ---------------------------------------------------------------------------
# Singleton state
# ---------------------------------------------------------------------------

_engine = None
_lock = threading.RLock()


def _resolve_signer(load: bool = True) -> str:
    """Return the persistent signer hex via the braid_keyz hardening layers.

    Priority (first artifact that exists and validates wins):
      1. bound seal   -> signer.sealed (env-bound + optional passphrase)
      2. threshold    -> keys/shares/  (K-of-N rejoin)
      3. legacy       -> signer.hex

    `load=False` reports which source would be used WITHOUT materializing a
    fresh key (used by `signer_hex()` so it never creates a key).
    """
    import braid_keyz

    sealed = os.environ.get("BRAID_KEYZ_SEALED_PATH") or os.path.join(
        DEFAULT_LOG_DIR, "signer.sealed"
    )
    if os.path.exists(sealed):
        passphrase = os.environ.get("BRAID_KEYZ_PASSPHRASE")
        return braid_keyz.unseal_signer(
            path=sealed, passphrase=passphrase or None
        )

    share_dir = os.environ.get("BRAID_KEYZ_SHARE_DIR") or os.path.join(
        DEFAULT_LOG_DIR, "keys", "shares"
    )
    share_files = braid_keyz.read_threshold_shares(share_dir)
    if share_files:
        k = int(os.environ.get("BRAID_KEYZ_K", "0")) or None
        seed = braid_keyz.recover_from_files(k=k, path=share_dir)
        signer = seed.hex()
        if load:
            # re-cache into the legacy path so non-keyz subsystems see it
            os.makedirs(DEFAULT_LOG_DIR, exist_ok=True)
            with open(SIGNER_PATH, "w", encoding="utf-8") as f:
                f.write(signer)
        return signer

    # legacy/plain path
    if os.path.exists(SIGNER_PATH):
        with open(SIGNER_PATH, "r", encoding="utf-8") as f:
            signer = f.read().strip()
        if signer:
            return signer
    if not load:
        raise BraidUnavailable("no signer materialized yet (load=False)")
    return _create_signer()


def _create_signer() -> str:
    import braid_python

    signer = braid_python.PyBraidEngine.generate_signer()
    os.makedirs(DEFAULT_LOG_DIR, exist_ok=True)
    with open(SIGNER_PATH, "w", encoding="utf-8") as f:
        f.write(signer)
    return signer


def _load_or_create_signer() -> str:
    """Materialize the persistent signer (create once on first use)."""
    try:
        import braid_python
    except ImportError:
        raise BraidUnavailable(
            "braid_python is not installed. Run: /opt/mem20/.venv/bin/maturin develop --release"
        )
    return _resolve_signer(load=True)


def get_engine(braided: bool = True):
    """Return the process-wide BraidEngine singleton (creating + wiring it once)."""
    global _engine
    if _engine is not None:
        return _engine
    with _lock:
        if _engine is not None:
            return _engine
        if not braided:
            raise BraidUnavailable("braid is disabled (braided=False)")

        import braid_python

        signer = _load_or_create_signer()
        _rotation_gate(signer)
        os.makedirs(DEFAULT_LOG_DIR, exist_ok=True)
        engine = braid_python.PyBraidEngine(DEFAULT_LOG_PATH, signer)

        # Genesis policy snapshot — registers write:* rules so commits pass.
        snap = braid_python.PyPolicySnapshot(
            cid=GENESIS_SNAPSHOT_CID,
            rules=[
                braid_python.PyPolicyRule(True, "read:*:*"),
                braid_python.PyPolicyRule(True, "write:*:*"),
                braid_python.PyPolicyRule(True, "agent:write:*"),
                braid_python.PyPolicyRule(True, "agent:read:*"),
            ],
            signer=signer,
            default_deny=True,
            name="genesis",
            version=1,
        )
        engine.register_snapshot(snap)
        _engine = engine
        return engine


def reset_engine() -> None:
    """Drop the singleton (used by tests)."""
    global _engine
    with _lock:
        _engine = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def available() -> bool:
    """True only if the functional Rust API resolves (PyBraidEngine present).

    With the repo root on sys.path, `import braid_python` can resolve to the
    Rust *source* directory as an empty namespace package — import succeeds but
    the engine API is absent. Check the actual symbol so we never claim
    availability for a shell.
    """
    try:
        import braid_python
        return hasattr(braid_python, "PyBraidEngine") and hasattr(braid_python, "PyPolicySnapshot")
    except ImportError:
        return False


def engine_id() -> str:
    return get_engine().id_hex()


def signer_hex() -> str:
    """Resolve the current signer WITHOUT forcing key creation.

    Uses the hardening layers (bound seal / threshold rejoin / legacy hex).  If
    the legacy path is empty and nothing is materialized, raises BraidUnavailable
    instead of quietly minting a fresh key during a read/status call.
    """
    import braid_python

    try:
        return _resolve_signer(load=False)
    except (BraidUnavailable, ValueError, RuntimeError):
        # fall back to the older behavior only when legacy signer.hex exists
        if os.path.exists(SIGNER_PATH):
            with open(SIGNER_PATH, "r", encoding="utf-8") as f:
                signer = f.read().strip()
            if signer:
                return signer
        raise


def _rotation_gate(signer: str) -> None:
    """Enforce chain-anchored rotation lineage if the ledger is rotated.

    Policy:
      - If the log contains zero `key:rotate` nodes, the legacy single-key
        setup is untouched: the genesis author IS the authorized signer.
      - If ANY rotation node exists, the authoring key must be in the lineage
        walked from genesis.  A stale/misplaced key that was rotated away from
        is refused here.
    Toggle: BRAID_KEYZ_ROTATION_GATE=force enables the gate even on an
    unrotated log (author must equal genesis signer).
    """
    import braid_keyz

    force = os.environ.get("BRAID_KEYZ_ROTATION_GATE", "").strip() == "force"
    try:
        auth = braid_keyz.authorized_signer_set(DEFAULT_LOG_PATH)
    except Exception:
        if force:
            raise BraidWriteError("rotation gate unable to walk ledger (forced on)")
        return
    if not auth:
        return  # no genesis on disk yet; nothing to enforce
    rotations = braid_keyz.rotation_history(DEFAULT_LOG_PATH)
    if not rotations and not force:
        return  # unrotated ledger: legacy single-key semantics preserved
    if signer not in auth:
        raise BraidWriteError(
            f"rotation gate: signer {signer[:8]}... is NOT in the authorized "
            f"lineage {sorted(auth)}.  Key was rotated away or is misplaced."
        )


def hash_data(data: bytes) -> str:
    import braid_python
    if isinstance(data, str):
        data = data.encode("utf-8")
    return braid_python.hash_data(data)


def verify_signature(signer: str, message: bytes, signature: str) -> bool:
    import braid_python
    if isinstance(message, str):
        message = message.encode("utf-8")
    return braid_python.verify_signature(signer, message, signature)


def commit(
    op: str,
    target: str,
    payload: Dict[str, Any],
    cap: str = DEFAULT_CAP,
    snapshot_cid: str = GENESIS_SNAPSHOT_CID,
    escalated: Optional[str] = None,
) -> Dict[str, Any]:
    """Commit a signed, proven node to the ledger. Returns a receipt dict.

    `escalated` is an OPTIONAL frozen-snapshot cid used to prove an escalation
    chain; pass it only when this write must carry a higher authority than the
    base capability alone provides (m4 semantics).
    """
    engine = get_engine()
    try:
        if escalated:
            receipt = engine.write_escalated(
                cap,
                snapshot_cid,
                cap,
                escalated,
                op,
                target,
                payload,
            )
        else:
            receipt = engine.write(cap, snapshot_cid, op, target, payload)
    except Exception as e:
        raise BraidWriteError(str(e))
    if not receipt.ok:
        raise BraidWriteError(
            f"write denied for op={op} target={target} cap={cap} (precommit_verified={getattr(receipt, 'precommit_verified', None)})"
        )
    return {
        "cid": receipt.cid,
        "depth": receipt.depth,
        "proof_hops": receipt.proof_hops,
        "escalated": receipt.escalated,
        "precommit_verified": receipt.precommit_verified,
        "ok": receipt.ok,
    }


def commit_fact(topic: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Commit a fact as a `write:fact` node. Content is stored in the ledger body."""
    payload = {
        "topic": topic,
        "content": content,
        "metadata": metadata or {},
        "committed_ts": datetime.now(timezone.utc).isoformat(),
    }
    return commit("write:fact", topic, payload)


def read(cid: str) -> Optional[Dict[str, Any]]:
    """Read a node by cid. Returns a plain dict or None."""
    node = get_engine().read(cid)
    if node is None:
        return None
    return node_to_dict(node)


def head() -> Optional[Dict[str, Any]]:
    node = get_engine().head()
    if node is None:
        return None
    return node_to_dict(node)


def prove(cid: str) -> bool:
    return get_engine().prove(cid)


def node_to_dict(node) -> Dict[str, Any]:
    return {
        "cid": node.cid,
        "depth": node.depth,
        "signer": node.signer,
        "op": node.op,
        "target": node.target,
        "payload": node.payload,
        "prev": node.prev,
        "is_proven": node.is_proven,
    }


def intent_submit(
    desire: str,
    target: str,
    context: Optional[Dict[str, Any]] = None,
    weight: int = 50,
    cap: str = DEFAULT_CAP,
) -> Dict[str, Any]:
    """Submit a `write:intent` node to the intent strand."""
    receipt = get_engine().intent_submit(
        cap,
        GENESIS_SNAPSHOT_CID,
        desire,
        target,
        context or {},
        int(weight),
    )
    return {
        "cid": receipt.cid,
        "depth": receipt.depth,
        "ok": receipt.ok,
        "target": target,
        "desire": desire,
    }


def intent_view() -> Dict[str, Any]:
    """Project the intent strand: submitted/open/resolved counts + intents."""
    view = get_engine().intent_view(DEFAULT_CAP, GENESIS_SNAPSHOT_CID)
    return {
        "submitted": view.submitted,
        "open": view.open,
        "resolved": view.resolved,
        "pending_count": view.pending_count,
        "intents": view.intents,
    }


def status() -> Dict[str, Any]:
    """Human/API-friendly status of the braid bridge."""
    try:
        eng = get_engine()
    except Exception as e:
        return {"available": False, "error": str(e)}
    head_node = head()
    return {
        "available": True,
        "engine_id": eng.id_hex(),
        "log_path": DEFAULT_LOG_PATH,
        "signer": signer_hex(),
        "head": head_node,
        "genesis_snapshot_cid": GENESIS_SNAPSHOT_CID,
    }


if __name__ == "__main__":
    import sys

    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "status":
        print(json.dumps(status(), indent=2, default=str))
    elif cmd == "commit":
        # python3 braid_bridge.py commit <op> <target> '<json-payload>'
        op = sys.argv[2]
        target = sys.argv[3]
        payload = json.loads(sys.argv[4]) if len(sys.argv) > 4 else {}
        print(json.dumps(commit(op, target, payload), indent=2))
    elif cmd == "intent":
        print(json.dumps(intent_view(), indent=2, default=str))
    elif cmd == "test":
        # Full self-test (no LLM, no external deps).
        signer = signer_hex()
        h = hash_data(b"hello braid")
        r = commit_fact("braid.self-test", "bridge smoke test")
        cid = r["cid"]
        n = read(cid)
        assert n is not None and n["is_proven"], "node not proven"
        assert prove(cid), "prove() returned False"
        print(json.dumps({
            "signer": signer[:16] + "...",
            "hash": h,
            "receipt": r,
            "read_ok": n is not None and n["op"] == "write:fact",
            "proved": prove(cid),
        }, indent=2))
        print("BRIDGE SELF-TEST PASSED")
    else:
        print("Usage: braid_bridge.py [status|commit|intent|test]")