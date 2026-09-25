"""Ledger + config archive (mem20agentz sub-phase 2.10).

`Backup` snapshots the mem20-backed state through the same substrate seams
the platform itself uses — config (scrubbed), profiles, and the full
`mem20agentz` ledger — into a single gzipped JSON archive with a sha256
sidecar. `restore` verifies the digest then replays the fact set back through
`namespace_ensure` + `remember`, so a backup round-trips the real substrate
surface and never invents state.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import pathlib
import time
from typing import Any, Optional

from .config import config_dir, load_config
from .profiles import namespace_for

SCRUB_HINTS = ("key", "token", "secret", "password")
KIND = "mem20agentz-backup"
VERSION = 1
BATCH = 10000


def _make_dir(path: pathlib.Path) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def default_archive_path() -> pathlib.Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return _make_dir(config_dir() / "backups") / f"mem20agentz-{stamp}.json.gz"


def _scrub(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: ("<redacted>" if any(h in k.lower() for h in SCRUB_HINTS)
                    else _scrub(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    return value


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class Backup:
    def __init__(self, backend=None) -> None:
        self.backend = backend

    # ------------------------------------------------------------ export
    def export(self, out: Optional[str] = None) -> dict:
        doc = {
            "kind": KIND,
            "version": VERSION,
            "created": int(time.time()),
            "config": _scrub(dict(load_config().data)),
            "profiles": [],
            "facts": [],
            "graphs": [],
        }
        if self.backend is not None:
            try:
                doc["profiles"] = [
                    {"name": n} for n in _profile_list(self.backend)
                ]
            except Exception as exc:  # pragma: no cover - honest failure
                doc["profiles"] = [{"error": str(exc)}]
            try:
                doc["facts"] = self.backend.recall(
                    tags=["mem20agentz"], k=BATCH)
            except Exception as exc:
                doc["facts"] = [{"error": str(exc)}]
            try:
                from .graphstore import GraphStore
                doc["graphs"] = GraphStore(backend=self.backend).list()
            except Exception as exc:
                doc["graphs"] = [{"error": str(exc)}]
        payload = json.dumps(doc, sort_keys=True, separators=(",", ":"))
        p = pathlib.Path(out) if out else default_archive_path()
        _make_dir(p)
        with gzip.open(p, "wt", encoding="utf-8") as fh:
            fh.write(payload)
        digest = _digest(payload.encode("utf-8"))
        _make_dir(p).with_name(p.name + ".sha256").write_text(
            digest + "\n", encoding="utf-8")
        return {"ok": True, "path": str(p), "sha256": digest,
                "facts": len(doc["facts"]),
                "profiles": len(doc.get("profiles", [])),
                "graphs": len(doc.get("graphs", []))}

    # ----------------------------------------------------------- restore
    def restore(self, path: str, profile: Optional[str] = None) -> dict:
        p = pathlib.Path(path)
        if not p.exists():
            return {"ok": False, "error": f"no such archive: {path}"}
        try:
            with gzip.open(p, "rt", encoding="utf-8") as fh:
                payload = fh.read()
        except OSError as exc:
            return {"ok": False, "error": f"cannot read archive: {exc}"}
        digest = _digest(payload.encode("utf-8"))
        side = pathlib.Path(str(p) + ".sha256")
        if side.exists():
            recorded = side.read_text(encoding="utf-8").strip()
            if recorded and recorded != digest:
                return {"ok": False, "error": "sha256 mismatch "
                                              "(corrupt archive)"}
        try:
            doc = json.loads(payload)
        except ValueError as exc:
            return {"ok": False, "error": f"invalid json archive: {exc}"}
        if doc.get("kind") != KIND:
            return {"ok": False, "error": "not a mem20agentz backup"}
        target = profile or "mem20"
        if self.backend is None:
            return {"ok": False, "error": "no backend to restore into"}
        self.backend.namespace_ensure(namespace=namespace_for(target))
        restored = 0
        skipped = 0
        for fact in doc.get("facts", []):
            content = fact.get("content") or fact.get("text") or ""
            if not content:
                skipped += 1
                continue
            self.backend.remember(
                topic=fact.get("topic", "restore"),
                content=content,
                tags=(fact.get("tags") or []) + ["mem20agentz", "restored"],
                actor=fact.get("actor") or target,
                epistemic_status=fact.get("epistemic_status") or "observed")
            restored += 1
        return {"ok": True, "profile": target, "sha256": digest,
                "restored": restored, "skipped": skipped}


def _profile_list(backend) -> list[str]:
    """Best-effort profile list; degrades to [] for sealed/stub backends."""
    try:
        from .profiles import Profiles
        return Profiles(backend=backend).list()
    except Exception:  # pragma: no cover - honest, non-fatal
        return []