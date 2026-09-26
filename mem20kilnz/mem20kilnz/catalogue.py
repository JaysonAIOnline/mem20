"""An index over generated assets, built from their own manifests.

The catalogue never inspects geometry itself. It reads the manifests the
pipeline already wrote, so an entry cannot claim something the build did not
actually produce. A GLB with no manifest is reported as untracked rather than
quietly described from its filename.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MANIFEST_SUFFIX = ".manifest.json"


@dataclass
class Entry:
    """One asset as the manifest recorded it."""

    name: str
    manifest: str
    glb: str
    glb_bytes: int
    triangles: int
    ok: bool
    gate_ok: bool | None
    provider: str
    brief: str
    family: str
    op_count: int
    failed_ops: int
    glb_sha256: str
    error: str = ""
    problems: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "manifest": self.manifest,
            "glb": self.glb,
            "glb_bytes": self.glb_bytes,
            "triangles": self.triangles,
            "ok": self.ok,
            "gate_ok": self.gate_ok,
            "provider": self.provider,
            "brief": self.brief,
            "family": self.family,
            "op_count": self.op_count,
            "failed_ops": self.failed_ops,
            "glb_sha256": self.glb_sha256,
            "error": self.error,
            "problems": self.problems,
        }


def _entry_from_manifest(path: Path) -> Entry | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    request = data.get("request") or {}
    result = data.get("result") or {}
    gate = data.get("gate") or {}
    journal = data.get("journal") or {}
    artifacts = data.get("artifacts") or {}
    glb = artifacts.get("glb") or {}
    problems: list[str] = []
    glb_path = glb.get("path", "")
    if not glb_path or not Path(glb_path).is_file():
        problems.append("glb missing")
    return Entry(
        name=str(request.get("name") or path.name[: -len(MANIFEST_SUFFIX)]),
        manifest=str(path),
        glb=glb_path,
        glb_bytes=int(glb.get("bytes", 0)),
        triangles=int(result.get("triangles", 0)),
        ok=bool(result.get("ok", False)),
        gate_ok=gate.get("ok"),
        provider=str(data.get("provider", "")),
        brief=str(request.get("brief", "")),
        family=str(request.get("family") or ""),
        op_count=int(journal.get("count", 0)),
        failed_ops=int(journal.get("failed", 0)),
        glb_sha256=str(glb.get("sha256", "")),
        error=str(result.get("error", "")),
        problems=problems,
    )


class Catalogue:
    """A read-only view over a directory of built assets."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.entries: list[Entry] = []
        self.untracked: list[str] = []
        self.unreadable: list[str] = []
        self._load()

    def _load(self) -> None:
        if not self.root.is_dir():
            return
        for path in sorted(self.root.rglob("*" + MANIFEST_SUFFIX)):
            entry = _entry_from_manifest(path)
            if entry is None:
                self.unreadable.append(str(path))
            else:
                self.entries.append(entry)
        for path in sorted(self.root.rglob("*.glb")):
            if not any(e.glb == str(path) for e in self.entries):
                self.untracked.append(str(path))

    def __len__(self) -> int:
        return len(self.entries)

    def find(
        self,
        name: str | None = None,
        family: str | None = None,
        provider: str | None = None,
        gate_ok: bool | None = None,
        min_triangles: int | None = None,
        max_triangles: int | None = None,
        contains: str | None = None,
    ) -> list[Entry]:
        """Filter entries. Every criterion is optional and they combine as AND."""
        out = []
        for e in self.entries:
            if name is not None and e.name != name:
                continue
            if family is not None and e.family != family:
                continue
            if provider is not None and e.provider != provider:
                continue
            if gate_ok is not None and e.gate_ok is not gate_ok:
                continue
            if min_triangles is not None and e.triangles < min_triangles:
                continue
            if max_triangles is not None and e.triangles > max_triangles:
                continue
            if contains is not None and contains.lower() not in e.brief.lower():
                continue
            out.append(e)
        return out

    def passing(self) -> list[Entry]:
        """Assets that both built and passed the gate, with no missing artifact."""
        return [e for e in self.entries if e.ok and e.gate_ok is True and not e.problems]

    def summary(self) -> dict[str, Any]:
        by_provider: dict[str, int] = {}
        for e in self.entries:
            by_provider[e.provider or "none"] = by_provider.get(e.provider or "none", 0) + 1
        return {
            "root": str(self.root),
            "tracked": len(self.entries),
            "passing": len(self.passing()),
            "refused": sum(1 for e in self.entries if e.gate_ok is False),
            "errored": sum(1 for e in self.entries if e.error),
            "with_problems": sum(1 for e in self.entries if e.problems),
            "untracked_glb": len(self.untracked),
            "unreadable_manifests": len(self.unreadable),
            "total_triangles": sum(e.triangles for e in self.entries),
            "by_provider": dict(sorted(by_provider.items())),
        }
