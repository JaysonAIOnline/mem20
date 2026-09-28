"""Source-only archive writer. Never carries secrets, databases or binaries."""

from __future__ import annotations

import fnmatch
import os
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .policy import is_skipped_dir, is_skipped_file, is_source_file

DEFAULT_OUT = Path("/opt/fullsrc.zip")

EXTRA_SKIP_DIR_GLOBS = (
    "*.dist-info",
    "htmlcov",
    "cov",
    "reports",
    "logs",
    "log",
    "tmp",
    "temp",
    "target",
    "vendor",
    "third_party",
    "playwright",
    "ms-playwright",
    "chromium",
    "models",
    "checkpoints",
    "blobs",
)


@dataclass
class SnapshotResult:
    out: str
    root: str
    files: int = 0
    skipped: int = 0
    skipped_secrets: int = 0
    raw_bytes: int = 0
    zip_bytes: int = 0
    seconds: float = 0.0
    finished_at: str = ""
    top_dirs: dict[str, int] = field(default_factory=dict)

    def to_json(self) -> str:
        import json

        payload: dict[str, Any] = dict(self.__dict__)
        payload["top_dirs"] = dict(sorted(self.top_dirs.items(), key=lambda kv: -kv[1])[:40])
        return json.dumps(payload, indent=2, sort_keys=True)


def _is_secret_path(rel: str) -> bool:
    parts = rel.split("/")
    if any(part in ("secrets", ".secrets") for part in parts):
        return True
    name = parts[-1]
    return bool(
        fnmatch.fnmatch(name, "*.env")
        or fnmatch.fnmatch(name, ".env*")
        or name in ("id_rsa", "id_ed25519", "credentials", "secrets.json", "auth.json")
        or fnmatch.fnmatch(name, "*.pem")
        or fnmatch.fnmatch(name, "*.key")
    )


def _should_skip(rel_path: str, extra_dirs: tuple[str, ...], extra_suffixes: tuple[str, ...]) -> bool:
    parts = rel_path.split("/")
    for part in parts[:-1]:
        if is_skipped_dir(part, extra_dirs):
            return True
    name = parts[-1]
    if is_skipped_dir(name, extra_dirs):
        return True
    return is_skipped_file(Path(name), extra_suffixes)


def create_snapshot(
    root: Path,
    out: Path = DEFAULT_OUT,
    extra_skip_dirs: tuple[str, ...] = (),
    extra_skip_suffixes: tuple[str, ...] = (),
    dry_run: bool = False,
    progress_every: int = 5000,
    on_progress: Any = None,
) -> SnapshotResult:
    root = root.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()
    result = SnapshotResult(out=str(out), root=str(root))

    tmp_out = out.with_suffix(out.suffix + ".partial")
    handle = None
    if not dry_run:
        handle = zipfile.ZipFile(
            tmp_out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True
        )

    try:
        for dirpath, dirnames, filenames in os.walk(root, topdown=True):
            current = Path(dirpath)
            rel_dir = current.relative_to(root)
            rel_str = "" if rel_dir == Path(".") else str(rel_dir)

            dirnames[:] = sorted(
                d
                for d in dirnames
                if not is_skipped_dir(d, extra_skip_dirs)
                and not _is_secret_path(f"{rel_str}/{d}".lstrip("/"))
            )

            for name in sorted(filenames):
                rel = f"{rel_str}/{name}".lstrip("/")
                if _is_secret_path(rel):
                    result.skipped_secrets += 1
                    result.skipped += 1
                    continue
                if _should_skip(rel, extra_skip_dirs, extra_skip_suffixes):
                    result.skipped += 1
                    continue
                path = current / name
                if not path.is_file() or path.is_symlink():
                    result.skipped += 1
                    continue
                if not is_source_file(path):
                    result.skipped += 1
                    continue
                try:
                    size = path.stat().st_size
                except OSError:
                    result.skipped += 1
                    continue
                if handle is not None:
                    try:
                        handle.write(path, rel)
                    except OSError:
                        result.skipped += 1
                        continue
                result.files += 1
                result.raw_bytes += size
                top = rel.split("/")[0]
                result.top_dirs[top] = result.top_dirs.get(top, 0) + 1
                if progress_every and result.files % progress_every == 0 and on_progress:
                    on_progress(result)
    finally:
        if handle is not None:
            handle.close()

    if not dry_run:
        os.replace(tmp_out, out)
        result.zip_bytes = out.stat().st_size

    result.seconds = round(time.time() - started, 2)
    result.finished_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    return result


def verify_zip(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"ok": False, "error": f"missing: {path}"}
    try:
        with zipfile.ZipFile(path) as zf:
            bad = zf.testzip()
            names = zf.namelist()
            secret_hits = [n for n in names if _is_secret_path(n)]
    except zipfile.BadZipFile as exc:
        return {"ok": False, "error": f"bad zip: {exc}"}
    return {
        "ok": bad is None and not secret_hits,
        "entries": len(names),
        "corrupt_entry": bad,
        "secret_paths": secret_hits[:20],
        "bytes": path.stat().st_size,
    }
