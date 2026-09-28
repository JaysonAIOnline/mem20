"""CLI contract coverage harness for the mem20 fleet.

Audits every subsystem CLI against the agreed contract:

* the binary is actually installed (not merely declared in a pyproject)
* ``--help`` exits 0 within a hard timeout
* the command advertises a machine contract (``--json``)

Naming is **not** part of the contract: Jayson decided on 2026-09-25 that no
subsystem is renamed, so ``fs-*`` and ``mem20*`` names are both correct and no
exception list is needed. Naming is still reported as information only.

Binaries listed in ``NON_CLI_BINARIES`` are excluded: they are support tooling
such as the install counter, not subsystem CLIs.

Read-only and bounded: it runs help probes with timeouts and never mutates
anything.
"""

from __future__ import annotations

import glob
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from typing import Any

REPO = "/opt/mem20"
VENV_BIN = "/root/.venv/bin"
HELP_TIMEOUT = 25
# Concurrent help probes. Enough to hide the slow CLIs without thrashing the box
# with 30 simultaneous heavy interpreter starts.
AUDIT_WORKERS = 12
FS_NAMING = re.compile(r"^fs-[a-z0-9][a-z0-9-]*$")
MEM20_NAMING = re.compile(r"^mem20(?:[-_]?[a-z0-9][a-z0-9_-]*)?$")
VERB_GROUP_RE = re.compile(r"\{([a-z0-9,\-]+)\}")

# Support tooling, not subsystem CLIs. mem20-metrics is an install counter and
# deliberately runs no argument parser, so it is never probed for --help.
NON_CLI_BINARIES = ("mem20-metrics",)


def _load_pyproject(path: str) -> dict:
    try:
        import tomllib
    except ImportError:
        return {}
    try:
        with open(path, "rb") as handle:
            return tomllib.load(handle)
    except (OSError, ValueError):
        return {}


def declared_scripts() -> list[dict[str, Any]]:
    """Every console script declared by a mem20* package pyproject on disk."""
    rows: list[dict[str, Any]] = []
    for pkg_dir in sorted(glob.glob(os.path.join(REPO, "mem20*"))):
        pyproject = os.path.join(pkg_dir, "pyproject.toml")
        if not os.path.isfile(pyproject):
            continue
        data = _load_pyproject(pyproject)
        if not data:
            continue
        scripts = (data.get("project") or {}).get("scripts") or {}
        package = (data.get("project") or {}).get("name") or os.path.basename(pkg_dir)
        for name, target in scripts.items():
            rows.append(
                {
                    "package": package,
                    "package_dir": pkg_dir,
                    "name": name,
                    "target": target,
                }
            )
    return rows


def installed_binaries() -> dict[str, dict[str, Any]]:
    """Console scripts physically present in the estate venv."""
    found: dict[str, dict[str, Any]] = {}
    for pattern in ("fs*", "mem20*"):
        for path in sorted(glob.glob(os.path.join(VENV_BIN, pattern))):
            name = os.path.basename(path)
            if not (os.path.isfile(path) or os.path.islink(path)):
                continue
            found[name] = {
                "path": path,
                "is_symlink": os.path.islink(path),
                "target": os.path.realpath(path) if os.path.islink(path) else None,
            }
    return found


def probe_help(name: str, path: str, timeout: int = HELP_TIMEOUT) -> dict[str, Any]:
    """Run ``<binary> --help`` under a hard timeout and summarise the result."""
    try:
        proc = subprocess.run(
            [path, "--help"], capture_output=True, text=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired:
        return {
            "help_exit": None,
            "help_ok": False,
            "timed_out": True,
            "has_json": False,
            "verbs": [],
            "detail": f"exceeded {timeout}s",
        }
    except OSError as exc:
        return {
            "help_exit": None,
            "help_ok": False,
            "timed_out": False,
            "has_json": False,
            "verbs": [],
            "detail": f"{type(exc).__name__}: {exc}",
        }

    output = f"{proc.stdout}\n{proc.stderr}"
    verbs: list[str] = []
    match = VERB_GROUP_RE.search(output)
    if match:
        verbs = [v for v in match.group(1).split(",") if v]
    return {
        "help_exit": proc.returncode,
        "help_ok": proc.returncode == 0,
        "timed_out": False,
        "has_json": "--json" in output,
        "verbs": verbs,
        "detail": "" if proc.returncode == 0 else (output.strip().splitlines() or [""])[0][:120],
    }


def classify_naming(name: str) -> str:
    if FS_NAMING.match(name):
        return "fs-standard"
    if MEM20_NAMING.match(name):
        return "mem20-native"
    return "other"


def audit(timeout: int = HELP_TIMEOUT) -> dict[str, Any]:
    """Run the full CLI contract audit."""
    declared = declared_scripts()
    binaries = installed_binaries()
    declared_by_name = {row["name"]: row for row in declared}

    results: list[dict[str, Any]] = []
    skipped: list[str] = []
    auditable = [name for name in sorted(binaries) if name not in NON_CLI_BINARIES]
    skipped = sorted(name for name in binaries if name in NON_CLI_BINARIES)

    # Probe concurrently. Each ``<binary> --help`` is a subprocess that can take
    # seconds on the CLIs with heavy imports, and running them one at a time made
    # a full audit take ~24s; the probes are independent and each already carries
    # its own hard timeout, so a slow CLI can no longer hold up the rest.
    # ``map`` preserves input order, so the report stays deterministically sorted.
    def _probe(name: str) -> dict[str, Any]:
        info = binaries[name]
        probe = probe_help(name, info["path"], timeout=timeout)
        row = {
            "name": name,
            "naming": classify_naming(name),
            "installed": True,
            "path": info["path"],
            "symlink": info["is_symlink"],
            "declared_in": declared_by_name.get(name, {}).get("package"),
            **probe,
        }
        gaps: list[str] = []
        if not row["help_ok"]:
            gaps.append("help-fails" if not row["timed_out"] else "help-timeout")
        if not row["has_json"]:
            gaps.append("no-json")
        row["gaps"] = gaps
        return row

    with ThreadPoolExecutor(max_workers=AUDIT_WORKERS) as pool:
        results = list(pool.map(_probe, auditable))


    undeclared = sorted(name for name in binaries if name not in declared_by_name)
    declared_missing = sorted(
        row["name"] for row in declared if row["name"] not in binaries
    )

    by_naming: dict[str, int] = {}
    for row in results:
        by_naming[row["naming"]] = by_naming.get(row["naming"], 0) + 1

    compliant = [r for r in results if not r["gaps"]]
    return {
        "repo": REPO,
        "venv_bin": VENV_BIN,
        "help_timeout_s": timeout,
        "naming_is_a_gap": False,
        "skipped_non_cli": skipped,
        "totals": {
            "installed_binaries": len(results) + len(skipped),
            "audited_clis": len(results),
            "skipped": len(skipped),
            "declared_scripts": len(declared),
            "fully_compliant": len(compliant),
            "with_help_failure": sum(
                1 for r in results if not r["help_ok"] and not r["timed_out"]
            ),
            "with_help_timeout": sum(1 for r in results if r["timed_out"]),
            "with_json": sum(1 for r in results if r["has_json"]),
            "fs_standard": by_naming.get("fs-standard", 0),
            "mem20_native": by_naming.get("mem20-native", 0),
        },
        "binaries_present_but_not_declared": undeclared,
        "declared_but_not_installed": declared_missing,
        "results": results,
    }
