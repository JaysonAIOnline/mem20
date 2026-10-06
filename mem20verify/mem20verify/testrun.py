"""Per-package test runner and pre-existing-failure separator.

Why this exists: running `pytest` from /opt/mem20 breaks the nested packages.
The outer directory (mem20unitiz/) has no __init__.py, so Python treats it as a
namespace package that shadows the real mem20unitiz/mem20unitiz. Tests must
therefore run from each package root, or from that package's own venv.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field

DEFAULT_ROOT = "/opt/mem20"
DEFAULT_PYTHON = "/root/.venv/bin/python"

_COUNT_RE = re.compile(r"(\d+)\s+(passed|failed|error|errors|skipped|xfailed|xpassed)")
_FAILED_RE = re.compile(r"^FAILED\s+(\S+)", re.MULTILINE)


@dataclass
class TestResult:
    package: str
    workdir: str = ""
    interpreter: str = ""
    returncode: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    failed_ids: list[str] = field(default_factory=list)
    timed_out: bool = False
    error_text: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and self.failed == 0 and not self.errors

    def as_dict(self) -> dict:
        return {
            "package": self.package,
            "workdir": self.workdir,
            "interpreter": self.interpreter,
            "returncode": self.returncode,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "errors": self.errors,
            "failed_ids": self.failed_ids,
            "timed_out": self.timed_out,
            "ok": self.ok,
        }


def discover_packages(root: str = DEFAULT_ROOT) -> list[str]:
    """Directories that look like test-bearing packages."""
    found = []
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name)
        if not os.path.isdir(path) or name.startswith("."):
            continue
        if name in ("tests", "test", "__pycache__"):
            continue
        if os.path.exists(os.path.join(path, "pyproject.toml")) or \
                os.path.isdir(os.path.join(path, "tests")) or \
                os.path.isdir(os.path.join(path, name, "tests")):
            found.append(name)
    return found


def interpreter_for(package_dir: str, preferred: str = DEFAULT_PYTHON) -> str:
    """Use the package's own venv when it has one, else the shared interpreter."""
    local = os.path.join(package_dir, ".venv", "bin", "python")
    if os.path.exists(local):
        return local
    return preferred


def parse_counts(output: str) -> dict[str, int]:
    counts = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}
    for number, word in _COUNT_RE.findall(output):
        key = {"error": "errors", "errors": "errors"}.get(word, word)
        if key in counts:
            counts[key] = int(number)
    return counts


def run_package(
    package: str,
    root: str = DEFAULT_ROOT,
    python: str | None = None,
    extra_args: list[str] | None = None,
    timeout: int = 600,
    test_pattern: str | None = None,
) -> TestResult:
    package_dir = os.path.join(root, package)
    interpreter = python or interpreter_for(package_dir)
    result = TestResult(
        package=package,
        workdir=package_dir,
        interpreter=interpreter,
    )
    if not os.path.exists(interpreter):
        result.error_text = f"interpreter not found: {interpreter}"
        result.returncode = 127
        return result

    # --override-ini addopts= neutralises the package's own addopts. Several
    # packages set addopts="-q"; stacked with our -q that becomes a double
    # --quiet, which suppresses pytest's "N passed" summary entirely. The suite
    # still ran, but parse_counts() had no summary line to read and scored the
    # package as 0 passed. Overriding addopts keeps exactly one -q so the
    # summary is always emitted and the counts are real.
    cmd = [interpreter, "-m", "pytest", "-q", "-p", "no:warnings",
           "--override-ini", "addopts="]
    if test_pattern:
        cmd += ["-k", test_pattern]
    cmd += extra_args or []

    try:
        proc = subprocess.run(cmd, cwd=package_dir, capture_output=True,
                              text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        result.timed_out = True
        result.error_text = f"exceeded {timeout}s"
        result.returncode = 124
        return result

    output = proc.stdout + proc.stderr
    result.returncode = proc.returncode
    counts = parse_counts(output)
    result.passed = counts["passed"]
    result.failed = counts["failed"]
    result.skipped = counts["skipped"]
    result.errors = counts["errors"]
    result.failed_ids = _FAILED_RE.findall(output)
    if proc.returncode != 0 and not result.failed and not result.errors:
        result.error_text = output.strip()[-800:]
    return result


def index_version(repo: str, rel_path: str) -> bytes | None:
    """Contents of a path at the git index, i.e. the pre-edit baseline.

    The index, not HEAD: much of this tree is staged-but-uncommitted, so HEAD
    predates the files entirely and `git show HEAD:<path>` fails.
    """
    try:
        proc = subprocess.run(["git", "-C", repo, "show", f":{rel_path}"],
                              capture_output=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def head_has_path(repo: str, rel_path: str) -> bool:
    try:
        proc = subprocess.run(
            ["git", "-C", repo, "cat-file", "-e", f"HEAD:{rel_path}"],
            capture_output=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


@dataclass
class BaselineVerdict:
    test_id: str
    fails_on_baseline: bool = False
    baseline_available: bool = True
    detail: str = ""

    @property
    def preexisting(self) -> bool:
        return self.baseline_available and self.fails_on_baseline

    def as_dict(self) -> dict:
        return {
            "test_id": self.test_id,
            "preexisting": self.preexisting,
            "baseline_available": self.baseline_available,
            "detail": self.detail,
        }


def attribute(
    package: str,
    test_ids: list[str],
    root: str = DEFAULT_ROOT,
    python: str | None = None,
    timeout: int = 600,
) -> list[BaselineVerdict]:
    """Decide whether failures are pre-existing by re-running them on the
    pre-edit baseline.

    The working tree is restored in a `finally` block from an explicit backup,
    so an interrupted run cannot leave the user's files modified. `git stash` is
    deliberately not used: it can collide with unrelated stashes.
    """
    package_dir = os.path.join(root, package)

    tracked: list[str] = []
    for dirpath, dirnames, filenames in os.walk(package_dir):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for filename in filenames:
            if filename.endswith((".py", ".toml", ".cfg", ".ini", ".md")):
                tracked.append(os.path.join(dirpath, filename))

    backups: dict[str, bytes | None] = {}
    for absolute in tracked:
        relpath = os.path.relpath(absolute, root)
        with open(absolute, "rb") as fh:
            backups[absolute] = fh.read()

    verdicts: list[BaselineVerdict] = []
    try:
        restored = 0
        for absolute in tracked:
            relpath = os.path.relpath(absolute, root)
            baseline = index_version(root, relpath)
            if baseline is not None:
                with open(absolute, "wb") as fh:
                    fh.write(baseline)
                restored += 1
        if restored == 0:
            for test_id in test_ids:
                verdicts.append(BaselineVerdict(
                    test_id, False, False,
                    "no baseline in git index; cannot attribute"))
            return verdicts

        for test_id in test_ids:
            target = test_id.split("::", 1)[-1] if "::" in test_id else test_id
            result = run_package(package, root=root, python=python,
                                 extra_args=[target], timeout=timeout)
            verdicts.append(BaselineVerdict(
                test_id=test_id,
                fails_on_baseline=not result.ok,
                baseline_available=True,
                detail=f"baseline returncode={result.returncode} "
                       f"failed={result.failed} errors={result.errors}",
            ))
    finally:
        for absolute, data in backups.items():
            if data is None:
                continue
            with open(absolute, "wb") as fh:
                fh.write(data)

    return verdicts


def verify_restore(package_dir: str, expected: dict[str, bytes]) -> bool:
    for absolute, data in expected.items():
        try:
            with open(absolute, "rb") as fh:
                if fh.read() != data:
                    return False
        except OSError:
            return False
    return True
