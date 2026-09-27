"""Brief to shipped asset, with a provenance record you can audit.

The point of this module is that a generated asset carries its own receipts.
Every op the engine applied — including the ones a language model invented on
its own, which never pass through the client as separate calls — is read back
from the engine's journal and written into a manifest beside the asset.

Nothing here invents a result. If the gate refuses an asset, `BuildResult.ok`
is False and the reasons are in the manifest.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from . import budgets as _budgets
from . import describe as _describe
from . import refine as _refine
from . import secrets as _secrets
from . import validate as _validate
from .errors import OpFailed
from .rpc import Kiln

MANIFEST_VERSION = 1


def sha256_file(path: str | Path) -> str:
    """Content hash of a file, or an empty string when it does not exist."""
    p = Path(path)
    if not p.is_file():
        return ""
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class BuildRequest:
    """One asset request."""

    brief: str
    out_dir: Path
    name: str | None = None
    family: str | None = None
    preview: bool = True
    samples: int = 2
    gate: bool = True
    require_prefix: bool = False
    lod: int = 0
    #: The bar to judge against. `standard` is the roadmap's authored budget;
    #: `blockout` accepts primitive-assembly output. The manifest records what
    #: was achieved regardless of what was asked for.
    tier: str = "standard"
    #: Attempt real-geometry refinement before judging the asset. On by default,
    #: because a standard-tier request that ships a blockout is the failure this
    #: pipeline exists to avoid. Set False to record the raw model output.
    auto_refine: bool = True
    refine_max_steps: int = 6


@dataclass
class BuildResult:
    """What actually happened, including when it did not work."""

    ok: bool
    brief: str
    name: str
    glb: str = ""
    glb_bytes: int = 0
    glb_sha256: str = ""
    png: str = ""
    png_bytes: int = 0
    manifest: str = ""
    engine_message: str = ""
    triangles: int = 0
    op_count: int = 0
    failed_ops: int = 0
    gate_ok: bool | None = None
    gate_findings: list[dict] = field(default_factory=list)
    requested_tier: str = "standard"
    achieved_tier: str = "none"
    refine: dict | None = None
    #: Plain-English description, so a text-only agent can read what it built.
    description: dict | None = None
    #: True when the brief failed partway but left usable geometry behind.
    partial: bool = False
    error: str = ""
    provider: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def _journal_summary(entries: list[dict]) -> dict:
    """Reduce a journal to the facts a manifest needs, plus the ops themselves."""
    kinds: dict[str, int] = {}
    failed: list[dict] = []
    for entry in entries:
        op = entry.get("op") or {}
        kind = op.get("op", "?") if isinstance(op, dict) else "?"
        kinds[kind] = kinds.get(kind, 0) + 1
        if not entry.get("ok", True):
            failed.append({"op": kind, "message": entry.get("message", "")})
    return {
        "count": len(entries),
        "failed": len(failed),
        "by_kind": dict(sorted(kinds.items(), key=lambda kv: (-kv[1], kv[0]))),
        "failures": failed,
    }


def build(request: BuildRequest, kiln: Kiln | None = None) -> BuildResult:
    """Build one asset. Reuses `kiln` if given, otherwise opens a session.

    The gate is applied to the exported file, not to an in-memory claim, so a
    manifest can never disagree with the bytes on disk.
    """
    out_dir = Path(request.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = request.name or "asset"
    glb_path = out_dir / f"{name}.glb"
    png_path = out_dir / f"{name}.png"
    manifest_path = out_dir / f"{name}.manifest.json"

    provider = _secrets.llm_config().get("_provider", "")
    session = kiln is not None
    k = kiln or Kiln(env=_secrets.engine_env())
    result = BuildResult(ok=False, brief=request.brief, name=name, provider=provider,
                         requested_tier=request.tier)
    try:
        k.reset()
        # Clear the journal so it describes this build and nothing earlier.
        k.call("journal", {"clear": True})

        try:
            reply = k.command(request.brief)
        except OpFailed as exc:
            # A brief can fail partway through and still have changed the scene.
            # Discarding that work would throw away real geometry, so measure
            # what exists before deciding this build failed.
            result.error = exc.message
            result.partial = True
        result.engine_message = str(reply.get("message", "")) if "reply" in dir() else result.error

        # The early-return paths below write a manifest, so the journal has to
        # exist from here even though the full read happens later.
        entries: list[dict] = []
        family = request.family or _budgets.infer_family(name)
        # Counted here so refine knows the brief produced something. The full
        # journal is read again at the end, after refine, so the manifest
        # describes the whole build.
        brief_ops = k.call("journal", {}).get("total", 0)

        # Refine before exporting, so the export is the refined asset and the
        # gate judges what actually ships. Only ops that add real geometry.
        if request.auto_refine and request.tier != "blockout" and brief_ops > 0:
            report = _refine.refine(
                k, family=family, target_tier=request.tier,
                max_steps=request.refine_max_steps,
            )
            result.refine = report.as_dict()
            if report.triangles_after and not report.steps and not report.target_reached:
                # Nothing to refine, or the scene had no geometry; the gate
                # below still decides, so this is recorded, not fatal.
                pass

        # Measure into a scratch file first. Exporting straight to the final
        # path would leave a valid but geometry-free GLB on disk for every
        # failed brief, which is litter that looks like a deliverable.
        probe_path = out_dir / f".{name}.measure.glb"
        k.export(str(probe_path))
        probe_bytes = probe_path.stat().st_size if probe_path.is_file() else 0
        structure = _validate.validate(probe_path) if probe_bytes else None
        if structure is not None:
            result.triangles = structure.total_triangles
        probe_path.unlink(missing_ok=True)

        if probe_bytes and not result.triangles:
            result.error = (
                "engine produced no geometry"
                + (f" (message: {result.engine_message})" if result.engine_message else "")
            )
            _write_manifest(manifest_path, request, result, entries)
            result.manifest = str(manifest_path)
            return result

        # The journal is read only now, after refine has run. Reading it earlier
        # recorded just the brief's ops, so a manifest described the blockout
        # while the shipped file was the refined asset -- replay then rebuilt 24
        # vertices where the original had 5,952, and the hashes did not match.
        journal = k.call("journal", {})
        entries = journal.get("entries", [])
        summary = _journal_summary(entries)
        result.op_count = summary["count"]
        result.failed_ops = summary["failed"]

        # Geometry confirmed, so the artifact is real and may be written.
        k.export(str(glb_path))
        result.glb = str(glb_path)
        result.glb_bytes = glb_path.stat().st_size if glb_path.is_file() else 0
        result.glb_sha256 = sha256_file(glb_path)

        if request.preview and result.glb_bytes:
            k.render(str(png_path), samples=request.samples)
            if png_path.is_file():
                result.png = str(png_path)
                result.png_bytes = png_path.stat().st_size

        if result.glb_bytes:
            # Measured from the file, never from the request: this is the tier
            # the asset actually reached, not the tier that was asked for.
            result.achieved_tier = _budgets.achieved_tier(family, result.triangles)

        # Describe the bytes that shipped, not the scene that produced them, so
        # the words cannot describe something the file does not contain.
        if result.glb_bytes:
            result.description = _describe.describe(glb_path).as_dict()

        if request.gate and result.glb_bytes:
            report = _validate.gate(
                glb_path,
                family=request.family or _budgets.infer_family(name),
                require_prefix=request.require_prefix,
                lod=request.lod,
                tier=request.tier,
            )
            result.gate_ok = report.gate_ok
            result.gate_findings = [f.as_dict() for f in report.findings]
            result.triangles = report.total_triangles
            result.ok = report.gate_ok
        else:
            result.ok = result.glb_bytes > 0

        _write_manifest(manifest_path, request, result, entries)
        result.manifest = str(manifest_path)
        return result
    finally:
        if not session:
            k.close()


def _write_manifest(path: Path, request: BuildRequest, result: BuildResult,
                    entries: list[dict]) -> None:
    """Write the receipts. Written even on failure, so a refusal is auditable."""
    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "request": {
            "brief": request.brief,
            "name": result.name,
            "family": request.family,
            "preview": request.preview,
            "samples": request.samples,
            "gate": request.gate,
            "lod": request.lod,
            "tier": request.tier,
            "auto_refine": request.auto_refine,
        },
        "brief_sha256": sha256_text(request.brief),
        "provider": result.provider,
        "result": {
            "ok": result.ok,
            "error": result.error,
            "engine_message": result.engine_message,
            "triangles": result.triangles,
            "partial": result.partial,
            "requested_tier": result.requested_tier,
            "achieved_tier": result.achieved_tier,
            "tier_met": (result.achieved_tier == result.requested_tier
                         if result.gate_ok else None),
        },
        "artifacts": {
            "glb": {
                "path": result.glb,
                "bytes": result.glb_bytes,
                "sha256": result.glb_sha256,
            },
            "png": {"path": result.png, "bytes": result.png_bytes} if result.png else None,
        },
        "gate": {
            "applied": request.gate,
            "ok": result.gate_ok,
            "tier": request.tier,
            "findings": result.gate_findings,
        },
        "refine": result.refine,
        "description": result.description,
        "journal": {
            "count": result.op_count,
            "failed": result.failed_ops,
            "entries": entries,
        },
    }
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def verify(manifest_path: str | Path) -> dict:
    """Re-check a manifest against the files it claims.

    Returns a report rather than raising, so a caller can gate on it. A manifest
    whose artifact hash no longer matches is a stale manifest, and says so.
    """
    path = Path(manifest_path)
    if not path.is_file():
        return {"ok": False, "reason": f"no manifest at {path}"}
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "reason": f"unreadable manifest: {exc}"}

    problems: list[str] = []
    glb = (manifest.get("artifacts") or {}).get("glb") or {}
    glb_path = glb.get("path", "")
    if glb_path:
        if not Path(glb_path).is_file():
            problems.append(f"glb missing: {glb_path}")
        else:
            actual = sha256_file(glb_path)
            if glb.get("sha256") and actual != glb["sha256"]:
                problems.append(
                    f"glb changed since the manifest was written "
                    f"(recorded {glb['sha256'][:12]}, actual {actual[:12]})"
                )
    else:
        problems.append("manifest records no glb")

    expected = manifest.get("brief_sha256", "")
    actual_brief = sha256_text(str((manifest.get("request") or {}).get("brief", "")))
    if expected and actual_brief != expected:
        problems.append("brief hash does not match the recorded brief")

    return {
        "ok": not problems,
        "manifest": str(path),
        "brief": (manifest.get("request") or {}).get("brief", ""),
        "glb": glb_path,
        "glb_sha256": glb.get("sha256", ""),
        "gate_ok": (manifest.get("gate") or {}).get("ok"),
        "journal_count": (manifest.get("journal") or {}).get("count", 0),
        "problems": problems,
    }


def build_many(briefs: list[str], out_dir: Path, **kwargs: Any) -> list[dict]:
    """Build several assets in one engine session.

    One session, because starting the kernel per brief dominates the cost. Each
    asset still gets its own manifest and its own journal window.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    with Kiln(env=_secrets.engine_env()) as k:
        for i, brief in enumerate(briefs):
            request = BuildRequest(brief=brief, out_dir=out_dir, name=f"asset_{i:03d}", **kwargs)
            entry = build(request, kiln=k).as_dict()
            entry["name"] = request.name
            results.append(entry)
    return results
