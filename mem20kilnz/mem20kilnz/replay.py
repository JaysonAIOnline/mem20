"""Reproduce an asset exactly, from the record of how it was made.

Model output is non-deterministic: the same brief yields different geometry each
run, so a manifest is only meaningful if the ops behind it can be replayed.
The engine's journal records every op that was applied, in order, including the
ones a language model invented internally and which never passed through the
client as separate calls. That journal is a complete record, so replaying it
into a fresh scene rebuilds the same asset.

This is the difference between a manifest that documents an asset and one that
reproduces it. `reproduce` re-runs the journal, exports, and compares the
SHA-256 of the result against the hash the manifest recorded. Equal hashes mean
the bytes are identical, not merely similar.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from . import secrets as _secrets
from .pipeline import sha256_file
from .rpc import Kiln

#: Ops that depend on something outside the journal, so a replay cannot be
#: guaranteed to match. Recorded rather than silently skipped.
EXTERNAL_OPS = ("import", "import_gltf", "import_fbx", "import_obj", "open")


@dataclass
class ReplayResult:
    """What replaying achieved, and whether it matched."""

    ok: bool = False
    applied: int = 0
    skipped: int = 0
    expected_sha256: str = ""
    actual_sha256: str = ""
    identical: bool | None = None
    glb: str = ""
    failures: list[dict] = field(default_factory=list)
    external: list[str] = field(default_factory=list)
    reason: str = ""

    def as_dict(self) -> dict:
        from dataclasses import asdict

        return asdict(self)


def replay(entries: list[dict], out_glb: str | Path,
           env: dict[str, str] | None = None) -> ReplayResult:
    """Apply a journal to a fresh scene and export it.

    Ops that failed when first recorded are skipped rather than re-raised: the
    original build survived them, so the replay must too. Each skip is reported.
    """
    out = Path(out_glb)
    out.parent.mkdir(parents=True, exist_ok=True)
    result = ReplayResult(glb=str(out))
    if not entries:
        result.reason = "the journal is empty"
        return result

    run_env = env if env is not None else _secrets.engine_env()
    with Kiln(env=run_env) as k:
        k.reset()
        for entry in entries:
            op = entry.get("op")
            if not isinstance(op, dict) or "op" not in op:
                result.skipped += 1
                result.failures.append({"op": "?", "reason": "journal entry has no op"})
                continue
            kind = str(op.get("op", "?"))
            if kind in EXTERNAL_OPS:
                result.external.append(kind)
            try:
                k.op(op)
                result.applied += 1
            except Exception as exc:  # the original run also failed this op
                result.skipped += 1
                result.failures.append({
                    "op": kind,
                    "reason": str(getattr(exc, "message", exc))[:120],
                })
        try:
            k.export(str(out))
        except Exception as exc:
            result.reason = f"export failed: {getattr(exc, 'message', exc)}"
            return result

    if not out.is_file():
        result.reason = "the replay produced no file"
        return result
    result.actual_sha256 = sha256_file(out)
    result.ok = True
    if result.external:
        result.reason = (
            "replayed, but the journal contains ops that read external files ("
            + ", ".join(sorted(set(result.external)))
            + "); the result matches only while those files are unchanged"
        )
    return result


def reproduce(manifest_path: str | Path,
              out_glb: str | Path | None = None) -> ReplayResult:
    """Replay a manifest's journal and check the bytes against its recorded hash.

    This is the determinism check. A matching SHA-256 means the replayed asset is
    byte-identical to the one the manifest describes.
    """
    path = Path(manifest_path)
    result = ReplayResult()
    if not path.is_file():
        result.reason = f"no manifest at {path}"
        return result
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        result.reason = f"unreadable manifest: {exc}"
        return result

    entries = (manifest.get("journal") or {}).get("entries") or []
    recorded = ((manifest.get("artifacts") or {}).get("glb") or {}).get("sha256", "")
    result.expected_sha256 = recorded

    if out_glb is None:
        base = path.name
        if base.endswith(".manifest.json"):
            base = base[: -len(".manifest.json")]
        out_glb = path.parent / f"{base}.replay.glb"
    else:
        out_glb = Path(out_glb)

    result = replay(entries, out_glb)
    result.expected_sha256 = recorded
    if not result.ok:
        return result
    if not recorded:
        result.identical = None
        result.reason = "the manifest records no glb hash to compare against"
        return result
    result.identical = result.actual_sha256 == recorded
    if not result.identical and not result.external:
        result.reason = (
            f"replay produced different bytes: recorded {recorded[:16]}, "
            f"got {result.actual_sha256[:16]}"
        )
    return result
