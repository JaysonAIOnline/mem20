"""Data-integrity round-trip.

The invariant: what a caller stores is what comes back, byte for byte. Secret
and PII detection may *report*; it must never rewrite stored content.

Every payload here is chosen to include strings a naive scanner mistakes for
credentials (a 40-hex git SHA-1, a 64-hex content hash, a 64-char CID) because
those are exactly the shapes that were being corrupted in production.
"""

from __future__ import annotations

import contextlib
import io
import os
import tempfile
from dataclasses import dataclass, field

GIT_SHA1 = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
CONTENT_HASH = "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"
BRAID_CID = ("br25166abf9a68c78abb8545dacb65dbcedbcb1f69ec0b02be4c1e4a"
             "4f48fec32c")
UUID = "550e8400-e29b-41d4-a716-446655440000"

PAYLOADS = {
    "git_sha": f"deployed commit {GIT_SHA1} to production",
    "content_hash": f"artifact digest {CONTENT_HASH} verified",
    "braid_cid": f"ledger node {BRAID_CID} committed and proven",
    "uuid": f"request id {UUID} completed",
    "mixed": (f"commit {GIT_SHA1} node {BRAID_CID} uuid {UUID} "
              f"digest {CONTENT_HASH} all present"),
    "unicode": "unicode intact — em dash, ümläut, 日本語, emoji \U0001f9ea",
    "multiline": "line one\nline two\n\ttabbed\n  spaced  \n",
    "quotes": "he said \"double\" and 'single' and `backtick`",
    "empty": "",
    "whitespace_only": "   \n\t  \n",
    "long": "x" * 20000,
}


@dataclass
class IntegrityResult:
    engine: str = ""
    checked: int = 0
    roundtrip_ok: int = 0
    failures: list[dict] = field(default_factory=list)
    false_positive_detections: list[dict] = field(default_factory=list)
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error and not self.failures and not self.false_positive_detections

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "engine": self.engine,
            "checked": self.checked,
            "roundtrip_ok": self.roundtrip_ok,
            "failures": self.failures,
            "false_positive_detections": self.false_positive_detections,
            "error": self.error,
        }


def _load_engine(engine_dir: str):
    import sys
    if engine_dir not in sys.path:
        sys.path.insert(0, engine_dir)
    try:
        import memory  # type: ignore
    except ImportError as exc:
        raise RuntimeError(f"memory_engine not importable: {exc}") from exc
    return memory


def check(engine_dir: str = "/opt/mem20/memory_engine") -> IntegrityResult:
    result = IntegrityResult(engine=engine_dir)
    try:
        memory = _load_engine(engine_dir)
    except RuntimeError as exc:
        result.error = str(exc)
        return result

    if not hasattr(memory, "remember"):
        result.error = "memory_engine has no remember(); cannot verify"
        return result

    originals = (memory.ENTRIES, memory.LEDGER)
    workdir = tempfile.mkdtemp(prefix="mem20verify-integrity-")
    memory.ENTRIES = os.path.join(workdir, "entries")
    memory.LEDGER = os.path.join(workdir, "ledger.jsonl")

    # never let a stray warning corrupt stdout-based reporting
    with contextlib.redirect_stderr(io.StringIO()):
        try:
            for name, payload in PAYLOADS.items():
                result.checked += 1
                memory.remember(topic=f"integrity-{name}", content=payload)
                rows = [r for r in _read_ledger(memory.LEDGER)
                        if r.get("topic") == f"integrity-{name}"]
                if not rows:
                    result.failures.append({
                        "payload": name,
                        "reason": "no ledger row written",
                    })
                    continue
                stored = rows[-1].get("content", "")
                if stored == payload:
                    result.roundtrip_ok += 1
                else:
                    result.failures.append({
                        "payload": name,
                        "reason": "stored content differs from input",
                        "expected_len": len(payload),
                        "stored_len": len(stored),
                        "expected_sha": _sha(payload),
                        "stored_sha": _sha(stored),
                    })

            # detection must not fire on non-secret technical strings
            detect = getattr(memory, "detect_secrets", None)
            if callable(detect):
                for name in ("git_sha", "content_hash", "braid_cid", "uuid", "mixed"):
                    hits = detect(PAYLOADS[name])
                    if hits:
                        result.false_positive_detections.append({
                            "payload": name,
                            "labels": sorted({h.label for h in hits}),
                        })
            else:
                result.error = "memory_engine exposes no detect_secrets()"
        finally:
            memory.ENTRIES, memory.LEDGER = originals

    return result


def _read_ledger(path: str) -> list[dict]:
    import json
    rows: list[dict] = []
    if not os.path.exists(path):
        return rows
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    return rows


def _sha(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
