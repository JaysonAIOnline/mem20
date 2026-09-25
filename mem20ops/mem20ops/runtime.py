"""Runtime inspection workflows: stale-code detection and bounded verification."""

from __future__ import annotations

import os
import re
import subprocess
import time
from datetime import UTC, datetime
from typing import Any

DEFAULT_PYTHON = "/root/.venv/bin/python"


def _iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=UTC).isoformat()


def _ps_fields() -> list[dict[str, str]]:
    output = subprocess.run(
        ["ps", "-ww", "-eo", "pid=,lstart=,etimes=,args="],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    rows: list[dict[str, str]] = []
    pattern = re.compile(r"^\s*(\d+)\s+(.{24})\s+(\d+)\s+(.*)$")
    for line in output.splitlines():
        match = pattern.match(line)
        if not match:
            continue
        pid, lstart, etimes, args = match.groups()
        rows.append({"pid": pid, "lstart": lstart.strip(), "elapsed_s": etimes, "cmd": args.strip()})
    return rows


def _ps_args() -> list[dict[str, str]]:
    """Process list with the full command line intact.

    ``ps`` truncates its ``args`` column to the assumed terminal width unless
    ``-ww`` is given, which silently hides long paths and makes a path match fail
    for no visible reason. Always pass ``-ww`` here.
    """
    output = subprocess.run(
        ["ps", "-ww", "-eo", "pid=,etimes=,args="],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    rows: list[dict[str, str]] = []
    pattern = re.compile(r"^\s*(\d+)\s+(\d+)\s+(.*)$")
    for line in output.splitlines():
        match = pattern.match(line)
        if not match:
            continue
        pid, etimes, args = match.groups()
        rows.append({"pid": pid, "elapsed_s": etimes, "cmd": args.strip()})
    return rows


def find_stale_processes(
    paths: list[str],
    match: str | None = None,
    related: list[str] | None = None,
) -> dict[str, Any]:
    """Report running processes that started before a source file was last modified.

    A process holds the code it loaded at start, so an edit on disk does not reach
    it until it restarts. This is the check that tells you whether a fix is live.

    ``paths`` are matched against process command lines. ``related`` files only
    contribute their mtime, which covers the common case where a long-running
    server imports a module without naming it on the command line: pass the
    server entry script in ``paths`` and the imported module in ``related``.
    """
    watched = list(paths) + list(related or [])
    missing = [p for p in watched if not os.path.exists(p)]
    if missing:
        raise FileNotFoundError("missing source file(s): " + ", ".join(missing))

    mtimes = {p: os.path.getmtime(p) for p in watched}
    newest_path = max(mtimes, key=lambda p: mtimes[p])
    newest_mtime = mtimes[newest_path]

    rows: list[dict[str, Any]] = []
    for row in _ps_fields():
        if match and match not in row["cmd"]:
            continue
        relevant = [p for p in paths if p in row["cmd"]]
        if not relevant:
            continue
        elapsed = int(row["elapsed_s"])
        started = time.time() - elapsed
        rows.append(
            {
                "pid": int(row["pid"]),
                "cmd": row["cmd"][:200],
                "elapsed_s": elapsed,
                "started_approx": _iso(started),
                "started_before_source": started < newest_mtime,
                "matched_paths": relevant,
                "watched_related": [p for p in (related or []) if p in mtimes],
                "verdict": "STALE" if started < newest_mtime else "current",
            }
        )

    stale = [r for r in rows if r["verdict"] == "STALE"]
    return {
        "source_mtimes": {p: _iso(m) for p, m in mtimes.items()},
        "newest_source": newest_path,
        "newest_mtime": _iso(newest_mtime),
        "processes_checked": len(rows),
        "stale_count": len(stale),
        "stale_pids": [r["pid"] for r in stale],
        "processes": rows,
        "interpretation": (
            "STALE processes loaded code before the source edit and will not pick it up "
            "until restarted. 'current' processes started after the edit."
        ),
    }


def _run(cmd: list[str], cwd: str | None = None, timeout: int = 900) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired:
        return {
            "command": cmd,
            "exit_code": 124,
            "timed_out": True,
            "stdout_tail": "",
            "stderr_tail": "",
        }
    return {
        "command": cmd,
        "exit_code": proc.returncode,
        "timed_out": False,
        "stdout_tail": proc.stdout[-4000:],
        "stderr_tail": proc.stderr[-4000:],
    }


PYTEST_COUNT_RE = re.compile(r"(\d+)\s+(passed|failed|error|errors|skipped)\b")


def verify_suite(
    repo: str = "/opt/mem20",
    python: str = DEFAULT_PYTHON,
    lint_paths: list[str] | None = None,
    run_tests: bool = True,
    run_lint: bool = True,
    timeout: int = 900,
) -> dict[str, Any]:
    """Run the test suite and lint, returning real counts and non-zero on failure."""
    results: dict[str, Any] = {"repo": repo, "steps": []}

    if run_tests:
        test_run = _run([python, "-m", "pytest", "tests/", "-q"], cwd=repo, timeout=timeout)
        counts: dict[str, int] = {}
        for count, label in PYTEST_COUNT_RE.findall(test_run["stdout_tail"]):
            counts[label] = int(count)
        test_run["counts"] = counts
        results["steps"].append({"name": "pytest", **test_run})

    if run_lint and lint_paths:
        lint_run = _run(
            [python, "-m", "ruff", "check", "--output-format=concise", *lint_paths],
            cwd=repo,
            timeout=300,
        )
        finding_count = len(
            [l for l in lint_run["stdout_tail"].splitlines() if l.strip()]
        )
        lint_run["finding_lines"] = finding_count
        results["steps"].append({"name": "ruff", **lint_run})

    failed = [s for s in results["steps"] if s["exit_code"] != 0]
    results["ok"] = not failed
    results["failed_steps"] = [s["name"] for s in failed]
    return results


def service_status(unit: str) -> dict[str, Any]:
    """Report systemd unit status, main pid, and whether it has restarted recently."""
    show = _run(
        [
            "systemctl",
            "show",
            unit,
            "-p",
            "ActiveState",
            "-p",
            "SubState",
            "-p",
            "MainPID",
            "-p",
            "ActiveEnterTimestamp",
            "-p",
            "ExecMainStartTimestamp",
            "--no-pager",
        ]
    )
    props: dict[str, str] = {}
    for line in show["stdout_tail"].splitlines():
        key, _, value = line.partition("=")
        if key:
            props[key.strip()] = value.strip()
    pid = int(props.get("MainPID") or 0)
    running = _run(["ps", "-o", "lstart=", "-p", str(pid)]) if pid else None
    return {
        "unit": unit,
        "active_state": props.get("ActiveState"),
        "sub_state": props.get("SubState"),
        "main_pid": pid,
        "active_enter": props.get("ActiveEnterTimestamp"),
        "exec_main_start": props.get("ExecMainStartTimestamp"),
        "main_pid_started": running["stdout_tail"].strip() if running else None,
    }
