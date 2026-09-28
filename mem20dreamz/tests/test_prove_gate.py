"""End-to-end guard on braid_bridge.prove() — the gate every Python caller trusts.

This is a *Python-surface* test, not a unit test of the underlying gate. The Rust
tests in braid_python/tests/prove_gate.rs cover `node_is_proven` itself; they pass
whether or not the binding is wired to it. Only this test fails if
`PyBraidEngine::prove` goes back to the weaker content-hash-only check.

The real gap being guarded: `prove()` used to call `BraidLog::verify`, which only
re-derives the CID from the body. A node with a correct content hash but a forged,
replaced or stripped signature would have reported as "proven" here — and
`prove()` is what the dream engine's durability checks, promotion's integrity
gate, and every other Python caller rely on.

Runs against a throwaway ledger via MEM20_BRAID_DIR, in a subprocess, so the
signature tamper is read back cold the way a real verification would be.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap

import pytest

BRIDGE_DIR = "/opt/mem20"


def _run(ledger_dir: str, body: str) -> tuple[int, str, str]:
    """Run a snippet in a cold interpreter with braid_bridge on `ledger_dir`."""
    env = dict(os.environ, MEM20_BRAID_DIR=ledger_dir, PYTHONPATH=BRIDGE_DIR)
    # Generous: these tests spawn a cold interpreter that loads braid's Rust
    # extension. Under a full 40-package sweep the machine is saturated and a short
    # timeout turns into a spurious failure that looks like a broken gate.
    try:
        proc = subprocess.run(
            [sys.executable, "-c", textwrap.dedent(body)],
            capture_output=True,
            text=True,
            env=env,
            timeout=600,
            check=False,
        )
    except subprocess.TimeoutExpired:  # pragma: no cover - load-dependent
        return 124, "", "TIMEOUT: the cold interpreter did not finish in 600s"
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


WRITE_ONE = """
    import braid_bridge as b
    r = b.commit("write:fact", "test:target", {"n": 1, "note": "hello"})
    print(r["cid"])
"""


@pytest.fixture
def ledger(tmp_path):
    d = tmp_path / "braid"
    d.mkdir()
    code, out, err = _run(str(d), WRITE_ONE)
    assert code == 0, f"could not seed the ledger: {err}"
    return d, out


def _tamper_signature(ledger_dir, cid: str) -> None:
    path = ledger_dir / "mem20.braid"
    lines = []
    for raw in path.read_text().splitlines():
        if not raw.strip():
            continue
        node = json.loads(raw)
        if node.get("cid") == cid:
            audit = node.get("audit") or {}
            # A well-formed but wrong signature: the content hash is untouched,
            # so a content-only check would still call this node proven.
            audit["signature"] = "42" + audit.get("signature", "00" * 64)[2:]
            node["audit"] = audit
        lines.append(json.dumps(node, separators=(",", ":"), sort_keys=False))
    path.write_text("\n".join(lines) + "\n")


def test_honest_node_verifies(ledger):
    d, cid = ledger
    code, out, err = _run(
        str(d), f"import braid_bridge as b; print(b.prove({cid!r}))"
    )
    assert code == 0, err
    assert out == "True", "an untampered node must verify"


def test_forged_signature_does_not_verify(ledger):
    """The regression this file exists for."""
    d, cid = ledger
    _tamper_signature(d, cid)
    code, out, err = _run(
        str(d), f"import braid_bridge as b; print(b.prove({cid!r}))"
    )
    assert code == 0, err
    assert out == "False", (
        f"prove() accepted a node whose signature was forged - the Python gate is "
        f"not checking the signature (rc={code}, out={out!r}, err={err[:300]!r})"
    )


def test_stripped_audit_does_not_verify(ledger):
    d, cid = ledger
    path = d / "mem20.braid"
    kept = []
    for raw in path.read_text().splitlines():
        if not raw.strip():
            continue
        node = json.loads(raw)
        if node.get("cid") == cid:
            node.pop("audit", None)
        kept.append(json.dumps(node, separators=(",", ":")))
    path.write_text("\n".join(kept) + "\n")
    code, out, err = _run(
        str(d), f"import braid_bridge as b; print(b.prove({cid!r}))"
    )
    assert code == 0, err
    assert out == "False", "a node with no audit strand must not verify"


def test_tampered_payload_does_not_verify(ledger):
    d, cid = ledger
    path = d / "mem20.braid"
    kept = []
    for raw in path.read_text().splitlines():
        if not raw.strip():
            continue
        node = json.loads(raw)
        if node.get("cid") == cid:
            node["payload"] = {"n": 1, "note": "TAMPERED"}
        kept.append(json.dumps(node, separators=(",", ":")))
    path.write_text("\n".join(kept) + "\n")
    code, out, err = _run(
        str(d), f"import braid_bridge as b; print(b.prove({cid!r}))"
    )
    assert code == 0, err
    assert out == "False", "changed content must not verify"
