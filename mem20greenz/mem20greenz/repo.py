"""Software clone helper (git, subprocess, bounded)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class CloneError(RuntimeError):
    pass


def clone_repo(source: str, out_dir: str | Path, *,
               timeout: float = 120.0) -> dict:
    """Clone a git repo (https or file://) into out_dir. Returns a report."""
    git = shutil.which("git")
    if git is None:
        raise CloneError("git executable not found on PATH")
    out = Path(out_dir)
    if out.exists() and any(out.iterdir()):
        raise CloneError(f"refusing to clone into non-empty {out}")
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            [git, "clone", "--depth", "1", source, str(out)],
            capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise CloneError(f"clone timed out after {timeout}s") from exc
    if proc.returncode != 0:
        raise CloneError(f"git clone failed: {proc.stderr.strip()[:300]}")
    files = sum(1 for _ in out.rglob("*") if _.is_file())
    return {"source": source, "dir": str(out), "files": files,
            "stderr_tail": proc.stderr.strip()[-200:]}
