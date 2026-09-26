"""Build and locate the native C++ kernel.

The engine is not a vendored binary: it is source that lives beside this package
and is compiled on demand. `build()` runs the project's own Makefile, so the
compiler flags the engine was written for are the ones used, and the warning
count is reported rather than swallowed — a clean build is part of the contract.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .errors import EngineMissing

BINARY_NAME = "kiln"
_WARN = re.compile(r"\bwarning:\b")
_ERR = re.compile(r"\berror:\b")


@dataclass
class BuildResult:
    ok: bool
    returncode: int
    binary: str = ""
    warnings: int = 0
    errors: int = 0
    compiler: str = ""
    log: str = field(default="", repr=False)

    def summary(self) -> str:
        if not self.ok:
            return f"build failed rc={self.returncode} ({self.errors} error(s))"
        return (
            f"built {self.binary} with {self.compiler}: "
            f"{self.warnings} warning(s), {self.errors} error(s)"
        )


def engine_source_dir() -> Path:
    from . import engine_dir

    return engine_dir()


def binary_path() -> Path:
    """Locate the engine binary.

    `KILNZ_BINARY` wins so a caller can point at a build under test. Then the
    in-tree build, then PATH. A missing binary raises rather than returning
    something that will fail later.
    """
    override = os.environ.get("KILNZ_BINARY")
    if override:
        p = Path(override).expanduser()
        if p.is_file() and os.access(p, os.X_OK):
            return p
        found = shutil.which(override)
        if found:
            return Path(found)
        raise EngineMissing(str(p), "KILNZ_BINARY is set but does not point at an executable")

    src = engine_source_dir()
    for cand in (src / BINARY_NAME, src / "build" / BINARY_NAME):
        if cand.is_file() and os.access(cand, os.X_OK):
            return cand
    found = shutil.which(BINARY_NAME)
    if found:
        return Path(found)
    raise EngineMissing(str(src / BINARY_NAME))


def have_binary() -> bool:
    try:
        binary_path()
        return True
    except EngineMissing:
        return False


def compiler_version(cxx: str | None = None) -> str:
    exe = cxx or os.environ.get("CXX") or "g++"
    if not shutil.which(exe):
        return exe
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=30)
        return out.stdout.splitlines()[0] if out.stdout else exe
    except (OSError, subprocess.SubprocessError):
        return exe


def build(jobs: int | None = None, clean: bool = False, timeout: int = 900) -> BuildResult:
    """Compile the engine with its own Makefile and report the real numbers."""
    src = engine_source_dir()
    if not (src / "Makefile").is_file():
        return BuildResult(False, 2, log=f"no Makefile in {src}")
    n = jobs or (os.cpu_count() or 2)
    cmds = [["make", "clean"]] if clean else []
    cmds.append(["make", f"-j{n}"])
    log_parts = []
    rc = 0
    for cmd in cmds:
        try:
            proc = subprocess.run(cmd, cwd=src, capture_output=True, text=True, timeout=timeout)
        except (OSError, subprocess.SubprocessError) as exc:
            return BuildResult(False, 2, log=f"{cmd} failed to run: {exc}")
        log_parts.append(proc.stdout + proc.stderr)
        rc = proc.returncode
        if rc != 0:
            break
    log = "\n".join(log_parts)
    warnings = len(_WARN.findall(log))
    errors = len(_ERR.findall(log))
    binary = ""
    if rc == 0:
        try:
            binary = str(binary_path())
        except EngineMissing:
            rc = 2
            log += "\nbuild reported success but no binary is present"
    return BuildResult(rc == 0, rc, binary, warnings, errors, compiler_version(), log)


def engine_info() -> dict[str, object]:
    """Describe the local kernel without starting a session."""
    src = engine_source_dir()
    info: dict[str, object] = {
        "source_dir": str(src),
        "source_exists": src.is_dir(),
        "binary": "",
        "binary_exists": False,
        "compiler": compiler_version(),
    }
    try:
        p = binary_path()
        info["binary"] = str(p)
        info["binary_exists"] = True
        info["binary_bytes"] = p.stat().st_size
    except EngineMissing as exc:
        info["binary_missing_reason"] = exc.message
    return info
