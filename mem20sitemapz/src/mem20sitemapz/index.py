"""Single-pass scanner that turns the monorepo into a machine-readable index."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from .policy import (
    CODE_LANGUAGES,
    DOC_NAMES,
    SCHEMA,
    UNPREFIXED_SERVICES,
    is_skipped_dir,
    is_skipped_file,
    is_source_file,
    language_of,
)

LINE_COUNT_MAX_BYTES = 2_000_000
DEFAULT_MAX_DEPTH = 14


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


README_TEXT_LIMIT = 8000


def _doc_files(subsystem_dir: Path) -> list[Path]:
    found = [subsystem_dir / name for name in DOC_NAMES if (subsystem_dir / name).is_file()]
    if not found:
        found = sorted(p for p in subsystem_dir.glob("*.md") if p.is_file())[:2]
    return found


def _readme_head(subsystem_dir: Path) -> str:
    for candidate in _doc_files(subsystem_dir):
        for line in _read_text(candidate, 4000).splitlines():
            stripped = line.strip().lstrip("#").strip()
            if stripped and not stripped.startswith(("!", "[", "<", "-", "|", "*")):
                return stripped[:300]
    return ""


def _readme_text(subsystem_dir: Path) -> str:
    chunks = []
    for candidate in _doc_files(subsystem_dir):
        chunks.append(_read_text(candidate, README_TEXT_LIMIT))
    return " ".join(chunks)[:README_TEXT_LIMIT].lower()


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
        "lines_by_language": {},
        "languages": {},
        "test_files": 0,
        "docs": [],
        "modules": [],
        "top_level_dirs": [],
    }


def scan(root: Path, max_depth: int = DEFAULT_MAX_DEPTH) -> dict[str, Any]:
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
        "code_lines": sum(s["code_lines"] for s in subsystems),
        "languages": _merge_languages([s["languages"] for s in subsystems]),
        "categories": _count_by(subsystems, "category"),
    }

    return {
        "schema": SCHEMA,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "root": str(root),
        "roots": [str(root)],
        "scan_seconds": round(time.time() - started, 2),
        "totals": totals,
        "root_files": root_files,
        "root_languages": root_bucket["languages"],
        "subsystems": subsystems,
    }


def _find_pyproject(root: Path, max_depth: int = 3) -> Path | None:
    """Find the package that defines an outside root, if there is one.

    An outside root is usually a whole project rather than a subsystem, so its
    pyproject sits a level or two down (``/sb/backend/pyproject.toml``) instead
    of at the root. Looking a few levels in is what makes entry points and
    keywords discoverable at all; a root with no pyproject still gets an entry,
    just a plainer one.
    """
    direct = root / "pyproject.toml"
    if direct.is_file():
        return direct
    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        current = Path(dirpath)
        depth = len(current.relative_to(root).parts)
        if depth > max_depth:
            dirnames[:] = []
            continue
        dirnames[:] = sorted(d for d in dirnames if not is_skipped_dir(d))
        if "pyproject.toml" in filenames:
            return current / "pyproject.toml"
    return None


def _indexed_subdirs(root: Path, max_depth: int) -> list[str]:
    """Top-level directories of an outside root that actually hold source.

    Listing every directory would advertise things that are not part of the
    project - a data/ directory holding only a database, a build/ or cache/
    directory. Only directories with at least one indexable file are named, so
    the list describes the project rather than its byproducts.
    """
    found: list[str] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir() or is_skipped_dir(child.name):
            continue
        for dirpath, dirnames, filenames in os.walk(child, topdown=True):
            current = Path(dirpath)
            if len(current.relative_to(root).parts) > max_depth:
                dirnames[:] = []
                continue
            dirnames[:] = sorted(d for d in dirnames if not is_skipped_dir(d))
            for name in filenames:
                path = current / name
                if not is_skipped_file(path) and is_source_file(path):
                    found.append(child.name)
                    break
            else:
                continue
            break
    return found


def scan_extra(extra_root: Path, max_depth: int = DEFAULT_MAX_DEPTH) -> list[dict[str, Any]]:
    """Index a root that lives outside the monorepo as a single subsystem.

    A few real tools deliberately do not live under /opt/mem20 - /sb is one -
    and the index is much less useful if it cannot describe them. Scanning such
    a root the ordinary way would emit one entry per top-level directory
    ("backend", "frontend", "data"), which tells a reader nothing. So the whole
    root becomes one entry, named after the package that defines it and carrying
    its real path, so nobody opens the wrong directory.
    """
    extra_root = extra_root.resolve()
    if not extra_root.is_dir():
        return []

    pyproject = _find_pyproject(extra_root)
    meta = _load_pyproject(pyproject.parent) if pyproject else {}
    bucket = _new_bucket()

    for dirpath, dirnames, filenames in os.walk(extra_root, topdown=True):
        current = Path(dirpath)
        rel = current.relative_to(extra_root)
        depth = 0 if rel == Path(".") else len(rel.parts)
        dirnames[:] = sorted(d for d in dirnames if not is_skipped_dir(d))
        if depth >= max_depth:
            dirnames[:] = []
        for name in sorted(filenames):
            path = current / name
            if is_skipped_file(path) or not is_source_file(path):
                continue
            _accumulate(bucket, path, current, extra_root)

    if not bucket["files"]:
        return []

    by_lang = bucket["lines_by_language"]
    code_lines = sum(value for lang, value in by_lang.items() if lang in CODE_LANGUAGES)
    subdirs = _indexed_subdirs(extra_root, max_depth)
    name = meta.get("name") or extra_root.name

    return [
        {
            "name": name,
            "dir": str(extra_root),
            "category": _classify(name),
            "description": meta.get("description") or "",
            "readme_summary": _readme_head(extra_root),
            "readme_text": _readme_text(extra_root),
            "keywords": meta.get("keywords") or [],
            "version": meta.get("version"),
            "license": meta.get("license"),
            "requires_python": meta.get("requires_python"),
            "dependencies": meta.get("dependencies") or [],
            "entry_points": meta.get("entry_points") or {},
            "packaged": bool(meta),
            "file_count": bucket["files"],
            "line_count": bucket["lines"],
            "code_lines": code_lines,
            "lines_by_language": dict(sorted(by_lang.items(), key=lambda kv: -kv[1])),
            "bytes": bucket["bytes"],
            "languages": dict(sorted(bucket["languages"].items(), key=lambda kv: -kv[1])),
            "test_files": bucket["test_files"],
            "docs": sorted(bucket["docs"]),
            "modules": sorted(bucket["modules"])[:40],
            "subdirs": subdirs[:20],
            "external_root": str(extra_root),
            "external": True,
        }
    ]


def _accumulate(bucket: dict[str, Any], path: Path, current: Path, root: Path) -> None:
    try:
        size = path.stat().st_size
    except OSError:
        size = 0
    language = language_of(path)
    bucket["files"] += 1
    bucket["bytes"] += size
    lines = _count_lines(path, size)
    bucket["lines"] += lines
    bucket["lines_by_language"][language] = bucket["lines_by_language"].get(language, 0) + lines
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
    by_lang = bucket["lines_by_language"]
    code_lines = sum(
        value for lang, value in by_lang.items() if lang in CODE_LANGUAGES
    )
    entry: dict[str, Any] = {
        "name": meta.get("name") or name,
        "dir": name,
        "category": _classify(name),
        "description": meta.get("description") or "",
        "readme_summary": _readme_head(subsystem_dir),
        "readme_text": _readme_text(subsystem_dir),
        "keywords": meta.get("keywords") or [],
        "version": meta.get("version"),
        "license": meta.get("license"),
        "requires_python": meta.get("requires_python"),
        "dependencies": meta.get("dependencies") or [],
        "entry_points": meta.get("entry_points") or {},
        "packaged": bool(meta),
        "file_count": bucket["files"],
        "line_count": bucket["lines"],
        "code_lines": code_lines,
        "lines_by_language": dict(sorted(by_lang.items(), key=lambda kv: -kv[1])),
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
