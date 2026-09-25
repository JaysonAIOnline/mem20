"""Config + foreign-setup migration (mem20agentz sub-phase 2.10).

Two honest migration paths:
  * `config()`  — bring the runtime config up to the current schema by adding
    default sections for gateway/office (etc.) that older configs lack, and
    report exactly what changed. Never guesses: each step only adds known
    defaults deterministically and rewrites the yaml unchanged otherwise.
  * `claw()`    — import an mem20 claw plugin memory export (a documented `{memories:
    [{content, tags}]}` JSON) into the ledger through the same
    `namespace_ensure` + `remember` seams, preserving each fact's tags and
    epistemic status.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from typing import Any, Optional

from .config import load_config
from .profiles import namespace_for

# Migrations run in order; each takes the config dict and returns (changed:list).
CONFIG_MIGRATIONS: list[dict[str, Any]] = [
    {
        "id": "gateway.office-port",
        "apply": lambda cfg: _ensure(cfg, ["gateway", "office"], {"port": 18785}),
    },
    {
        "id": "logging.file",
        "apply": lambda cfg: _ensure(cfg, ["logging"],
                                     {"file": "runtime/mem20agentz.log"}),
    },
]


def _ensure(cfg: dict, path: list[str], defaults: dict) -> dict:
    changed: list[str] = []
    node: Any = cfg
    for part in path:
        if not isinstance(node, dict):
            node = {}  # repair non-dict section
        node = node.setdefault(part, {})
    for key, value in defaults.items():
        if key not in node:
            node[key] = value
            changed.append(".".join(path + [key]))
    return {"changed": changed, "cfg": cfg}


def _manifest_digest(entries: list[dict]) -> str:
    body = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(body).hexdigest()


class Migrator:
    def __init__(self, backend=None) -> None:
        self.backend = backend

    def config(self) -> dict:
        cfg = load_config()
        all_changed: list[str] = []
        for step in CONFIG_MIGRATIONS:
            result = step["apply"](cfg.data)
            all_changed.extend(result.get("changed", []))
            cfg.data = result["cfg"]
        if all_changed:
            cfg.update_file(cfg.data)
        return {"ok": True, "applied": [s["id"] for s in CONFIG_MIGRATIONS],
                "changed": sorted(set(all_changed))}

    def claw(self, manifest: str, profile: str = "mem20") -> dict:
        p = pathlib.Path(manifest)
        if not p.exists():
            return {"ok": False, "error": f"no such manifest: {manifest}"}
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except ValueError as exc:
            return {"ok": False, "error": f"invalid json: {exc}"}
        entries = data.get("memories", data) if isinstance(data, dict) else data
        if not isinstance(entries, list):
            return {"ok": False, "error": "manifest has no memories list"}
        ns = namespace_for(profile)
        if self.backend is None:
            return {"ok": False, "error": "no backend to migrate into"}
        self.backend.namespace_ensure(namespace=ns)
        imported = 0
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            content = entry.get("content") or entry.get("text") or ""
            if not content:
                continue
            tags = list(entry.get("tags") or []) + ["mem20agentz", "migrated",
                                                    "claw"]
            self.backend.remember(
                topic=entry.get("topic") or f"claw:{profile}",
                content=content,
                tags=tags,
                actor=profile,
                epistemic_status=entry.get("epistemic_status") or "observed")
            imported += 1
        return {"ok": True, "source": "claw", "profile": profile,
                "imported": imported, "sha256": _manifest_digest(entries)}