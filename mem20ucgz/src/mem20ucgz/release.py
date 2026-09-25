from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def build_manifest(root: str | Path) -> dict:
    root = Path(root)
    files = []
    for p in sorted(root.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts and p.name != "RELEASE-MANIFEST.json":
            files.append({"path": str(p.relative_to(root)), "sha256": sha256(p), "bytes": p.stat().st_size})
    return {"format": 1, "roadmap": "RM-001", "files": files}


def write_manifest(root: str | Path) -> Path:
    root = Path(root)
    out = root / "RELEASE-MANIFEST.json"
    out.write_text(json.dumps(build_manifest(root), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out


def rollback_safe_install(source: str | Path, target: str | Path) -> dict:
    source, target = Path(source), Path(target)
    backup = target.with_name(target.name + ".rollback")
    if backup.exists(): shutil.rmtree(backup)
    if target.exists(): target.rename(backup)
    try:
        shutil.copytree(source, target)
        return {"installed": str(target), "rollback": str(backup) if backup.exists() else None}
    except Exception:
        if target.exists(): shutil.rmtree(target)
        if backup.exists(): backup.rename(target)
        raise
