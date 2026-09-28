"""Braid integration: every iteration becomes a content-addressed node.

Two things this deliberately does NOT do:

* It does not promote anything into grounded memory. Braid is provenance - a
  signed, provable record that something happened. The simulated/grounded
  partition is where *belief* lives, and committing a dream to braid does not
  move it across that line. Promotion remains a separate, explicit gate.
* It does not fail quietly. If the ledger is unavailable the commit is recorded
  as NOT made, with the reason. A lineage that silently stops being
  content-addressed would look identical to one that is.

The node's ``prev`` pointer is braid's own global chain, so a lineage's
iterations are interleaved with everything else written to the ledger. The
lineage therefore keeps its own ordered list of cids, which is what makes any
iteration rewindable by reading one cid.
"""

from __future__ import annotations

import sys
from typing import Any

sys.path.insert(0, "/opt/mem20")

CAP = "agent:write:dream"


def available() -> bool:
    try:
        import braid_bridge

        return bool(braid_bridge.available())
    except Exception:  # noqa: BLE001 - absence is the answer, not a crash
        return False


def _payload(
    dream_id: str,
    iteration_n: int,
    artifact: str,
    fidelity: dict[str, Any],
    omission: dict[str, Any],
    forecast: dict[str, Any],
    inventions: list[dict[str, Any]],
    dreamer: dict[str, Any],
    selection: dict[str, Any],
    seed: str,
    foundation: str,
) -> dict[str, Any]:
    """The node body. Deliberately small-ish but complete enough to be re-read."""
    return {
        "dream_id": dream_id,
        "iteration": iteration_n,
        "kind": "dream_iteration",
        "seed": seed[:2000],
        "foundation": foundation[:2000],
        "artifact": artifact,
        "artifact_chars": len(artifact),
        "fidelity": fidelity,
        "omission": omission,
        "forecast": forecast,
        "inventions": inventions,
        "dreamer": dreamer,
        "selection": selection,
    }


def commit_iteration(lineage: Any, iteration: Any) -> dict[str, Any]:
    """Commit one iteration. Always returns a record; never raises into the loop.

    A dream that cannot be written to the ledger is still a dream that happened,
    so the failure is reported and stored rather than aborting the run.
    """
    try:
        import braid_bridge
    except Exception as exc:  # noqa: BLE001
        return {"committed": False, "reason": f"braid_bridge unavailable: {type(exc).__name__}: {exc}"}

    try:
        if not braid_bridge.available():
            return {"committed": False, "reason": "braid reports unavailable"}
    except Exception as exc:  # noqa: BLE001
        return {"committed": False, "reason": f"braid availability check failed: {exc}"}

    body = _payload(
        dream_id=lineage.dream_id,
        iteration_n=iteration.n,
        artifact=iteration.artifact,
        fidelity=iteration.fidelity,
        omission=iteration.omission,
        forecast=iteration.forecast,
        inventions=lineage.inventions.as_list(),
        dreamer=lineage.dreamer.as_dict(),
        selection=iteration.selection,
        seed=lineage.seed,
        foundation=lineage.foundation,
    )

    try:
        receipt = braid_bridge.commit(
            "write:dream_iteration", f"dream:{lineage.dream_id}", body, cap=CAP
        )
    except (braid_bridge.BraidUnavailable, braid_bridge.BraidWriteError) as exc:
        return {"committed": False, "reason": f"{type(exc).__name__}: {exc}"}
    except Exception as exc:  # noqa: BLE001
        return {"committed": False, "reason": f"{type(exc).__name__}: {exc}"}

    if not isinstance(receipt, dict) or not receipt.get("ok"):
        return {"committed": False, "reason": f"commit not acknowledged: {receipt}"}

    # Verify the write, but do NOT call this durability. braid acknowledged the
    # commit and precommit-verified it, yet four dream nodes written that way
    # later failed to prove - while an identical payload re-committed proves
    # fine. So an in-process check is evidence the write landed, not evidence
    # it will still verify. Durability is checked by `verify_chain`.
    cid = str(receipt.get("cid", ""))
    try:
        proven_now = bool(braid_bridge.prove(cid))
    except Exception as exc:  # noqa: BLE001
        proven_now = False
        receipt = {**receipt, "prove_error": f"{type(exc).__name__}: {exc}"}

    return {
        "committed": True,
        "cid": cid,
        "depth": receipt.get("depth"),
        "proof_hops": receipt.get("proof_hops"),
        "precommit_verified": receipt.get("precommit_verified"),
        "proven_at_commit": proven_now,
        "durability": "unverified - re-check with `mem20-dream verify`",
        "cap": CAP,
        "target": f"dream:{lineage.dream_id}",
    }


def commit_raw(op: str, target: str, body: dict[str, Any]) -> dict[str, Any]:
    """Commit an arbitrary dream-related node, e.g. a promotion record.

    Goes through here rather than touching braid_bridge directly, so every write
    the dream engine makes reports its durability the same honest way: `ack` is
    proof at write time, and durability is `verify_chain`'s job, not this one's.
    """
    try:
        import braid_bridge
    except Exception as exc:  # noqa: BLE001
        return {
            "committed": False,
            "reason": f"braid_bridge unavailable: {type(exc).__name__}: {exc}",
        }

    try:
        receipt = braid_bridge.commit(op, target, body, cap=CAP)
    except (braid_bridge.BraidUnavailable, braid_bridge.BraidWriteError) as exc:
        return {"committed": False, "reason": f"{type(exc).__name__}: {exc}"}
    except Exception as exc:  # noqa: BLE001
        return {"committed": False, "reason": f"{type(exc).__name__}: {exc}"}

    if not isinstance(receipt, dict) or not receipt.get("ok"):
        return {"committed": False, "reason": f"commit not acknowledged: {receipt}"}

    cid = str(receipt.get("cid", ""))
    try:
        proven_now = bool(braid_bridge.prove(cid))
    except Exception as exc:  # noqa: BLE001
        proven_now = False
        receipt = {**receipt, "prove_error": f"{type(exc).__name__}: {exc}"}

    return {
        "committed": True,
        "cid": cid,
        "depth": receipt.get("depth"),
        "precommit_verified": receipt.get("precommit_verified"),
        "proven_at_commit": proven_now,
        "durability": "unverified - re-check with `mem20-dream verify`",
        "cap": CAP,
        "target": target,
    }


def verify_chain(cids: list[str]) -> dict[str, Any]:
    """Re-prove every node in a lineage. Catches silent ledger damage.

    Existence is not proof. A node can be present, correctly linked and
    readable while its signature no longer verifies - which is exactly what four
    dream iterations looked like. Anything reported here as broken is recorded,
    not smoothed over.
    """
    try:
        import braid_bridge
    except Exception as exc:  # noqa: BLE001
        return {"checked": 0, "verified": 0, "broken": [], "error": f"braid_bridge unavailable: {exc}"}

    verified = 0
    broken: list[dict[str, Any]] = []
    for cid in cids or []:
        try:
            node = braid_bridge.read(cid)
        except Exception as exc:  # noqa: BLE001
            broken.append({"cid": cid, "problem": f"read failed: {type(exc).__name__}: {exc}"})
            continue
        if node is None:
            broken.append({"cid": cid, "problem": "node not found in ledger"})
            continue
        try:
            ok = bool(braid_bridge.prove(cid))
        except Exception as exc:  # noqa: BLE001
            ok = False
            broken.append({"cid": cid, "problem": f"prove raised: {type(exc).__name__}: {exc}"})
            continue
        if ok:
            verified += 1
        else:
            broken.append(
                {
                    "cid": cid,
                    "depth": node.get("depth"),
                    "target": node.get("target"),
                    "problem": "present and readable but does not verify",
                }
            )
    return {
        "checked": len(cids or []),
        "verified": verified,
        "broken": broken,
        "healthy": not broken,
    }


def read_iteration(cid: str) -> dict[str, Any] | None:
    """Re-read a committed iteration, for rewinding or auditing."""
    try:
        import braid_bridge

        return braid_bridge.read(cid)
    except Exception:  # noqa: BLE001
        return None


def lineage_chain(lineage: Any) -> list[str]:
    return list(getattr(lineage, "braid_cids", []) or [])


def head() -> dict[str, Any]:
    try:
        import braid_bridge

        return braid_bridge.status()
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "error": str(exc)}
