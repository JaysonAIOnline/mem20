"""Fleet-wide CLI dispatcher for the mem20 subsystems.

One command reaches every subsystem CLI:

    fs                     list every subsystem and its binary
    fs list --json         machine-readable inventory
    fs cv infer ...        runs the cv subsystem CLI
    fs corez serve ...     runs the corez subsystem CLI
    fs ops dns-audit ...   runs the fleet operations CLI

Subsystem names are matched loosely so ``fs corez``, ``fs mem20corez`` and
``fs-cv`` all reach the same CLI. The child's exit code is propagated so this
composes in scripts.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from typing import Any

VENV_BIN = "/root/.venv/bin"
FS_NAME_RE = re.compile(r"^fs-(?P<sub>.+)$")
MEM20_NAME_RE = re.compile(r"^mem20(?P<sub>[a-z0-9][a-z0-9_-]*)$")
MAX_LIST = 200


def _installed() -> dict[str, str]:
    found: dict[str, str] = {}
    if not os.path.isdir(VENV_BIN):
        return found
    for name in os.listdir(VENV_BIN):
        path = os.path.join(VENV_BIN, name)
        if not (os.path.isfile(path) or os.path.islink(path)):
            continue
        if name.startswith(("fs-", "mem20")):
            found[name] = path
    return found


def _subsystem_key(binary: str) -> str | None:
    match = FS_NAME_RE.match(binary)
    if match:
        return match.group("sub")
    match = MEM20_NAME_RE.match(binary)
    if match:
        return match.group("sub") or "core"
    return None


def inventory() -> list[dict[str, Any]]:
    """Every fleet CLI, keyed by subsystem, preferring the ``fs-*`` binary."""
    rows: dict[str, dict[str, Any]] = {}
    for binary, path in sorted(_installed().items()):
        key = _subsystem_key(binary)
        if key is None:
            continue
        row = rows.setdefault(
            key,
            {"subsystem": key, "binaries": [], "preferred": None, "path": None},
        )
        row["binaries"].append(binary)
        if binary.startswith("fs-"):
            row["preferred"] = binary
            row["path"] = path
    for row in rows.values():
        if row["preferred"] is None and row["binaries"]:
            row["preferred"] = row["binaries"][0]
            row["path"] = _installed()[row["preferred"]]
    return sorted(rows.values(), key=lambda r: r["subsystem"])


def resolve(name: str) -> dict[str, Any] | None:
    """Find a subsystem by loose name (sub, full binary name, or fs- name)."""
    wanted = name.strip().lower()
    for row in inventory():
        if row["subsystem"] == wanted or row["subsystem"].replace("-", "_") == wanted:
            return row
        if wanted in row["binaries"]:
            return row
        if wanted.replace("mem20", "", 1) == row["subsystem"]:
            return row
    return None


def _render_list(as_json: bool) -> int:
    rows = inventory()
    if as_json:
        print(json.dumps({"count": len(rows), "subsystems": rows}, indent=2))
        return 0
    if not rows:
        print("no fleet CLIs found in " + VENV_BIN)
        return 1
    print(f"{len(rows)} fleet CLI(s) in {VENV_BIN}\n")
    width = max(len(r["subsystem"]) for r in rows)
    for row in rows:
        aliases = ",".join(row["binaries"])
        print(f"  {row['subsystem']:<{width}}  ->  {row['preferred']:<22} ({aliases})")
    print("\nrun a subsystem:  fs <subsystem> [args...]")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    if not args:
        return _render_list(False)

    if args[0] in {"list", "--list"}:
        return _render_list("--json" in args)

    if args[0] in {"-h", "--help", "help"}:
        print(__doc__)
        return 0

    if args[0].startswith("-"):
        print(f"error: unknown option {args[0]!r}\n", file=sys.stderr)
        _render_list(False)
        return 2

    row = resolve(args[0])
    if row is None or not row["path"]:
        print(f"error: unknown subsystem {args[0]!r}", file=sys.stderr)
        known = ", ".join(r["subsystem"] for r in inventory())
        print(f"known subsystems: {known}", file=sys.stderr)
        return 1

    try:
        completed = subprocess.run([row["path"], *args[1:]], check=False)
    except FileNotFoundError:
        print(f"error: {row['path']} not found", file=sys.stderr)
        return 1
    return completed.returncode


if __name__ == "__main__":
    sys.exit(main())
