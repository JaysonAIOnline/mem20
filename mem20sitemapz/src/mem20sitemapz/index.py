"""Single-pass scanner that turns the monorepo into a machine-readable index."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from .policy import (
    DOC_NAMES,
    SCHEMA,
    UNPREFIXED_SERVICES,
    is_skipped_dir,
    is_skipped_file,
    is_source_file,
    language_of,
)

LINE_COUNT_MAX_BYTES = 2_000_000


def _read_text(path: Path, limit: int = 400_000) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            return handle.read(limit)
    except OSError:
        return ""


def _load_pyproject(subsystem_dir: Path) -> dict[str, Any]:
    pyproject = subsystem_dir / "pyproject.toml"
    if not pyproject.is_file():
        return {}
    try:
        import tomllib

        with pyproject.open("rb") as handle:
            data = tomllib.load(handle)
    except Exception:
        return {}
    project = data.get("project") or {}
    scripts = project.get("scripts") or {}
    tool = data.get("tool") or {}
    setuptools_cfg = tool.get("setuptools") or {}
    packages = setuptools_cfg.get("packages") or []
    return {
        "name": project.get("name"),
        "version": project.get("version"),
        "description": project.get("description"),
        "keywords": list(project.get("keywords") or []),
        "requires_python": project.get("requires-python"),
        "license": (project.get("license") or {}).get("text")
        if isinstance(project.get("license"), dict)
        else project.get("license"),
        "dependencies": list(project.get("dependencies") or []),
        "entry_points": {str(k): str(v) for k, v in scripts.items()},
        "packages": [str(p) for p in packages],
    }


def _readme_head(subsystem_dir: Path) -> str:
    for name in DOC_NAMES:
        candidate = subsystem_dir / name
        if candidate.is_file():
            for line in _read_text(candidate, 4000).splitlines():
                stripped = line.strip().lstrip("#").strip()
                if stripped and not stripped.startswith(("!", "[", "<")):
                    return stripped[:300]
    return ""


def _classify(name: str) -> str:
    if name.startswith("mem20") and name.endswith("z"):
        return "organ"
    if name in UNPREFIXED_SERVICES:
        return "service"
    if name.startswith("mem20") or name.startswith("mem20-"):
        return "organ"
    return "other"


def _count_lines(path: Path, size: int) -> int:
    if size > LINE_COUNT_MAX_BYTES:
        return 0
    try:
        with path.open("rb") as handle:
            return sum(1 for line in handle if line.strip())
    except OSError:
        return 0


def _new_bucket() -> dict[str, Any]:
    return {
        "files": 0,
        "bytes": 0,
        "lines": 0,
        "languages": {},
        "test_files": 0,
        "docs": [],
        "modules": [],
        "top_level_dirs": [],
    }


def scan(root: Path, max_depth: int = 2) -> dict[str, Any]:
    root = root.resolve()
    buckets: dict[str, dict[str, Any]] = {}
    root_files: list[str] = []
    started = time.time()

    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        current = Path(dirpath)
        rel = current.relative_to(root)
        depth = 0 if rel == Path(".") else len(rel.parts)

        dirnames[:] = sorted(
            d for d in dirnames if not is_skipped_dir(d) and not d.startswith(".sitemap")
        )
        if depth >= max_depth:
            dirnames[:] = []

        top = rel.parts[0] if rel.parts else None

        if top is None:
            root_files = sorted(filenames)
            for name in filenames:
                path = current / name
                if is_skipped_file(path) or not is_source_file(path):
                    continue
                bucket = buckets.setdefault("<root>", _new_bucket())
                _accumulate(bucket, path, current, root)
            continue

        if not is_source_file(current) and depth == 1 and not filenames and not dirnames:
            continue

        bucket = buckets.setdefault(top, _new_bucket())
        if depth == 1:
            bucket["top_level_dirs"] = sorted(dirnames)
            if len(rel.parts) == 1:
                bucket["path"] = top

        for name in filenames:
            path = current / name
            if is_skipped_file(path) or not is_source_file(path):
                continue
            _accumulate(bucket, path, current, root)

    subsystems: list[dict[str, Any]] = []
    for name in sorted(buckets):
        if name == "<root>":
            continue
        bucket = buckets[name]
        entry = _entry_for(root, name, bucket)
        if entry is not None:
            subsystems.append(entry)

    root_bucket = buckets.get("<root>", _new_bucket())
    totals = {
        "subsystems": len(subsystems),
        "files": sum(s["file_count"] for s in subsystems) + root_bucket["files"],
        "lines": sum(s["line_count"] for s in subsystems) + root_bucket["lines"],
        "languages": _merge_languages([s["languages"] for s in subsystems]),
        "categories": _count_by(subsystems, "category"),
    }

    return {
        "schema": SCHEMA,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "root": str(root),
        "scan_seconds": round(time.time() - started, 2),
        "totals": totals,
        "root_files": root_files,
        "root_languages": root_bucket["languages"],
        "subsystems": subsystems,
    }


def _accumulate(bucket: dict[str, Any], path: Path, current: Path, root: Path) -> None:
    try:
        size = path.stat().st_size
    except OSError:
        size = 0
    language = language_of(path)
    bucket["files"] += 1
    bucket["bytes"] += size
    bucket["lines"] += _count_lines(path, size)
    bucket["languages"][language] = bucket["languages"].get(language, 0) + 1
    if path.name in DOC_NAMES:
        bucket["docs"].append(str(path.relative_to(root)))
    if path.name.startswith("test_") and path.suffix == ".py":
        bucket["test_files"] += 1
    if path.suffix == ".py" and len(current.relative_to(root).parts) <= 2:
        module = str(path.relative_to(current))[:-3]
        if module not in bucket["modules"]:
            bucket["modules"].append(module)


def _entry_for(root: Path, name: str, bucket: dict[str, Any]) -> dict[str, Any] | None:
    subsystem_dir = root / name
    meta = _load_pyproject(subsystem_dir)
    entry: dict[str, Any] = {
        "name": meta.get("name") or name,
        "dir": name,
        "category": _classify(name),
        "description": meta.get("description") or "",
        "readme_summary": _readme_head(subsystem_dir),
        "keywords": meta.get("keywords") or [],
        "version": meta.get("version"),
        "license": meta.get("license"),
        "requires_python": meta.get("requires_python"),
        "dependencies": meta.get("dependencies") or [],
        "entry_points": meta.get("entry_points") or {},
        "packaged": bool(meta),
        "file_count": bucket["files"],
        "line_count": bucket["lines"],
        "bytes": bucket["bytes"],
        "languages": dict(sorted(bucket["languages"].items(), key=lambda kv: -kv[1])),
        "test_files": bucket["test_files"],
        "docs": sorted(bucket["docs"]),
        "modules": sorted(bucket["modules"])[:40],
        "subdirs": bucket["top_level_dirs"][:20],
    }
    if not entry["file_count"] and not entry["packaged"]:
        return None
    return entry


def _merge_languages(dicts: list[dict[str, int]]) -> dict[str, int]:
    merged: dict[str, int] = {}
    for item in dicts:
        for key, value in item.items():
            merged[key] = merged.get(key, 0) + value
    return dict(sorted(merged.items(), key=lambda kv: -kv[1]))


def _count_by(entries: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry[key]] = counts.get(entry[key], 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))
