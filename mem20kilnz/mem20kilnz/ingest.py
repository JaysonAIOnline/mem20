"""Ingest a mesh that some other tool produced.

Two jobs, kept separate on purpose:

* **probe** reads a file and reports what is actually in it — structure, real
  geometry counts, and how far it sits from the budget. Read-only, so it is
  safe to point at a large unknown asset.
* **convert** pushes a file through the engine and writes a manifest marked as
  an external source, so a later reader can tell generated work from imported
  work. It does not claim the result is good; the gate still decides that.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import budgets as _budgets
from . import secrets as _secrets
from . import validate as _validate
from .errors import KilnError
from .pipeline import sha256_file, sha256_text
from .rpc import Kiln

INGEST_MANIFEST_VERSION = 1

#: Extensions the engine's importer is known to read. Anything else is refused
#: by name rather than handed to the engine to fail obscurely.
SUPPORTED_SUFFIXES = (".glb", ".gltf", ".obj")
SUPPORTED_FORMATS = {
    ".glb": "glTF binary",
    ".gltf": "glTF 2.0",
    ".obj": "Wavefront OBJ",
}


@dataclass
class Probe:
    """What a file actually contains."""

    path: str
    ok: bool
    format: str = ""
    recognised: bool = False
    reason: str = ""
    glb_bytes: int = 0
    sha256: str = ""
    meshes: int = 0
    vertices: int = 0
    triangles: int = 0
    has_normals: bool = False
    has_uvs: bool = False
    family: str = ""
    tier: str = "standard"
    budget: dict[str, Any] = field(default_factory=dict)
    gate_ok: bool | None = None
    findings: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        from dataclasses import asdict

        return asdict(self)


def probe(path: str | Path, family: str | None = None, lod: int = 0,
          tier: str = "standard") -> Probe:
    """Measure a file without modifying it.

    `tier` is the bar to judge against and defaults to `standard`, the roadmap's
    authored budget. Pass `blockout` to accept primitive-assembly output.
    """
    p = Path(path)
    suffix = p.suffix.lower()
    result = Probe(path=str(p), ok=False, format=SUPPORTED_FORMATS.get(suffix, ""),
                   tier=tier)

    if not p.is_file():
        result.reason = f"no file at {p}"
        return result
    result.glb_bytes = p.stat().st_size
    result.sha256 = sha256_file(p)

    if suffix not in SUPPORTED_SUFFIXES:
        result.reason = (
            f"unsupported extension {suffix or '(none)'}; the importer reads "
            + ", ".join(SUPPORTED_SUFFIXES)
        )
        return result
    result.recognised = True

    if suffix == ".obj":
        # OBJ has no single-file structure this validator can assert against, so
        # report the size honestly and say the geometry was not measured.
        result.reason = "OBJ accepted for conversion; geometry not measured by this probe"
        result.ok = True
        result.family = family or _budgets.infer_family(p.stem)
        return result

    report = _validate.validate(p)
    result.meshes = len(report.meshes)
    result.vertices = sum(m.vertices for m in report.meshes)
    result.triangles = report.total_triangles
    result.has_normals = any(m.has_normals for m in report.meshes)
    result.has_uvs = any(m.has_uvs for m in report.meshes)
    result.family = family or _budgets.infer_family(p.stem)
    result.ok = report.ok
    if not report.ok:
        result.reason = "; ".join(f.message for f in report.errors)
        return result

    gated = _validate.gate(p, family=result.family, lod=lod, tier=tier)
    result.gate_ok = gated.gate_ok
    result.findings = [f.as_dict() for f in gated.findings]
    verdict = _budgets.check_triangles(result.family, result.triangles, lod, tier=tier)
    result.budget = {
        "family": result.family,
        "tier": tier,
        "lod": lod,
        "triangles": result.triangles,
        "lod0_min": verdict.lod0_min,
        "lod0_max": verdict.lod0_max,
        "ok": verdict.ok,
        "reason": verdict.reason,
    }
    return result


def convert(
    paths: list[str | Path],
    out_dir: str | Path,
    family: str | None = None,
    gate: bool = True,
    lod: int = 0,
    tier: str = "standard",
) -> list[dict]:
    """Import external meshes and record where each one came from.

    The manifest says `source: external` and carries the original file's hash,
    so an imported asset is never mistaken for a generated one.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []
    with Kiln(env=_secrets.engine_env()) as k:
        for raw in paths:
            src = Path(raw)
            record = probe(src, family=family, lod=lod, tier=tier)
            entry: dict[str, Any] = {
                "source": "external",
                "input": str(src),
                "input_bytes": record.glb_bytes,
                "input_sha256": record.sha256,
                "probe": record.as_dict(),
                "converted": False,
                "glb": "",
                "glb_bytes": 0,
                "glb_sha256": "",
                "manifest": "",
                "error": "",
            }
            if not record.recognised:
                entry["error"] = record.reason
                records.append(entry)
                continue

            k.reset()
            k.call("journal", {"clear": True})
            try:
                k.command(f"import {src}")
            except KilnError as exc:
                entry["error"] = getattr(exc, "message", str(exc))
                records.append(entry)
                continue

            journal = k.call("journal", {})
            glb_path = out / f"{src.stem}.glb"
            k.export(str(glb_path))
            entry["converted"] = True
            entry["glb"] = str(glb_path)
            entry["glb_bytes"] = glb_path.stat().st_size if glb_path.is_file() else 0
            entry["glb_sha256"] = sha256_file(glb_path)
            entry["journal"] = journal.get("entries", [])
            entry["journal_count"] = journal.get("total", 0)
            entry["imported_triangles"] = entry["glb_bytes"] and _triangles_of(glb_path)

            if gate and entry["glb_bytes"]:
                gated = _validate.gate(glb_path, family=family, lod=lod, tier=tier)
                entry["gate_ok"] = gated.gate_ok
                entry["gate_findings"] = [f.as_dict() for f in gated.findings]

            manifest_path = out / f"{src.stem}.ingest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "manifest_version": INGEST_MANIFEST_VERSION,
                        "kind": "ingest",
                        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "source": "external",
                        "input": {
                            "path": str(src),
                            "bytes": entry["input_bytes"],
                            "sha256": entry["input_sha256"],
                            "format": record.format,
                        },
                        "brief_sha256": sha256_text(str(src)),
                        "output": {
                            "glb": entry["glb"],
                            "bytes": entry["glb_bytes"],
                            "sha256": entry["glb_sha256"],
                        },
                        "probe": record.as_dict(),
                        "gate": {
                            "applied": gate,
                            "ok": entry.get("gate_ok"),
                            "findings": entry.get("gate_findings", []),
                        },
                        "journal": entry.get("journal", []),
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            entry["manifest"] = str(manifest_path)
            records.append(entry)
    return records


def _triangles_of(path: str | Path) -> int:
    report = _validate.validate(path)
    return report.total_triangles
