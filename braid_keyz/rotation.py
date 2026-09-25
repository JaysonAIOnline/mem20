"""Chain-anchored key rotation for the braid signer.

Rotation is committed as on-chain `key:rotate` nodes, authored by an ALREADY
authorized signer and naming the newly authorized public-key hex.  Authorship
of a rotation is proven by the braid itself (the Rust engine signs every node
with the authoring key).  Authorized-signer lineage is walked from genesis:

    authorized[0] = genesis signer (the node with prev == None)
    for node in nodes (depth order, then file order):
        if node.op == KEY_ROTATION_OP and node.signer in authorized:
            authorized.add(node.target)   # payload names the new key

The bridge gate (bridge.py) calls is_authorized_signer() before every write;
a key that was rotated *away from* stops being accepted the moment a chain
crosses to its successor — copies of the old key go stale by author's decree,
and prove() shows the chain.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Set

DEFAULT_LOG_PATH = os.path.join(
    os.environ.get("MEM20_BRAID_DIR", "/opt/mem20/store/braid"), "mem20.braid"
)
ROTATION_OP = "key:rotate"


class RotationError(RuntimeError):
    """Raised when a rotation cannot be committed or the lineage is violated."""


def _load_nodes(log_path: str) -> List[Dict]:
    """Load all nodes from the braid log file, in file order (append order)."""
    p = Path(log_path)
    if not p.exists():
        return []
    nodes: List[Dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            node = json.loads(line)
        except ValueError:
            continue
        nodes.append(node)
    return nodes


def _node_keyed(node: Dict) -> Dict:
    """Flatten a stored node into a comparable dict (prev/op/target/payload)."""
    payload = node.get("payload") or {}
    return {
        "cid": node.get("cid"),
        "prev": node.get("prev"),
        "op": node.get("op"),
        "target": node.get("target"),
        "signer": node.get("signer"),
        "depth": node.get("depth", 0),
        "payload": payload,
    }


def _genesis_signer(nodes: List[Dict]) -> Optional[str]:
    """The signer of the genesis node (prev == None)."""
    for node in nodes:
        if node.get("prev") is None:
            return node.get("signer")
    return None


def authorized_signer_set(log_path: str = DEFAULT_LOG_PATH) -> Set[str]:
    """Walk the chain from genesis and return every currently-authorized signer.

    A signer is added to the authorized set ONLY via a `key:rotate` node whose
    author is itself already authorized.  Nothing else grants authority.
    """
    nodes = _load_nodes(log_path)
    genesis = _genesis_signer(nodes)
    if genesis is None:
        # Empty or unreadable log: no lineage can be established.  Callers must
        # decide (bridge treats this as "not yet rotated" and defers to policy).
        return set()
    authorized: Set[str] = {genesis}

    # Process in depth order (stable: genesis first, then by depth, then cid)
    for node in nodes:
        if node.get("prev") is None:
            continue
        if node.get("op") != ROTATION_OP:
            continue
        author = node.get("signer")
        target = node.get("target")
        if not author or not target:
            continue
        if author in authorized:
            authorized.add(target)
    return authorized


def is_authorized_signer(signer: str, log_path: str = DEFAULT_LOG_PATH) -> bool:
    """True if `signer` is currently in the rotation lineage."""
    authorized = authorized_signer_set(log_path)
    if not authorized:
        # No genesis yet: nothing has ever been authorized.  Honest answer: no.
        return False
    return signer in authorized


def commit_rotation(
    new_signer_hex: str,
    commit,
    reason: str = "",
    op: str = ROTATION_OP,
) -> Dict:
    """Author `new_signer_hex` into the lineage by committing a rotation node.

    `commit(op, target, payload)` must be the bridge's real commit() so the
    node is signed AND appended by the authorized authoring engine.  Falls back
    to using the bridge module if `commit` is not supplied.
    """
    if not new_signer_hex or not isinstance(new_signer_hex, str):
        raise RotationError("new_signer_hex must be a non-empty hex string")
    if commit is None:
        import sys

        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        import braid_bridge

        commit = braid_bridge.commit
    payload = {
        "authorized_signer": new_signer_hex,
        "reason": reason,
        "rotated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    }
    return commit(op, new_signer_hex, payload)


def rotation_history(log_path: str = DEFAULT_LOG_PATH) -> List[Dict]:
    """Return the ordered list of rotation events (chain of authority)."""
    nodes = _load_nodes(log_path)
    return [
        {
            "cid": node.get("cid"),
            "prev": node.get("prev"),
            "signer": node.get("signer"),
            "target": node.get("target"),
            "depth": node.get("depth"),
            "payload": node.get("payload", {}),
        }
        for node in nodes
        if node.get("op") == ROTATION_OP
    ]