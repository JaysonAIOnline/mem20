"""Ground-truth discovery.

Nothing in a generated onboarding pack is asserted from memory. Every path,
command, port and subsystem listed for a new agent is read off this host at
generation time, so the guide cannot tell him something untrue about what is
actually installed.

Discovery is deliberately defensive: a missing `systemctl`, an unparseable
`ss` line or an absent sitemap degrades that one section to "unknown" instead
of raising. An onboarding guide that is partly honest beats one that is
confidently wrong.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .facts import FactSet

MEM20_ROOT = Path("/opt/mem20")
SITEMAP_JSON = MEM20_ROOT / ".sitemap" / "sitemap.json"

# Commands a new agent is most likely to reach for. Probed for real, never assumed.
CANDIDATE_COMMANDS = [
    "python3",
    "pip",
    "git",
    "gh",
    "sqlite3",
    "jq",
    "rg",
    "curl",
    "systemctl",
    "ss",
    "chromium",
    "unity",
    "blender",
    "node",
    "npm",
    "tesseract",
    "ffmpeg",
    "docker",
    "psql",
    "redis-cli",
]

# Paths a new agent needs to know exist before he wanders into a wrong repo.
CANDIDATE_PATHS = [
    ("/opt/mem20", "mem20 monorepo root"),
    ("/opt/mem20/.sitemap", "generated codebase sitemap"),
    ("/root/AGENTS.md", "standing rules loaded into every agent session"),
    ("/opt/mem20/toolchest", "runtime-checked tool registry"),
    ("/opt/mem20/secrets/.env", "consolidated credentials (never print)"),
    ("/home/jayson/Desktop", "Jayson's desktop"),
    ("/home/jayson/Apps", "locally installed applications"),
    ("/etc/systemd/system", "systemd unit directory"),
]

_CMD_TIMEOUT = 8


def _run(argv: list[str], timeout: int = _CMD_TIMEOUT) -> tuple[int, str]:
    """Run a command, returning (returncode, stdout). Never raises on failure."""
    if not shutil.which(argv[0]):
        return 127, ""
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return 124, ""
    return proc.returncode, proc.stdout


def discover_paths(facts: FactSet) -> list[dict]:
    """Existence-check each candidate path. Reports type, never contents."""
    rows = []
    for raw, purpose in CANDIDATE_PATHS:
        p = Path(raw)
        exists = p.exists()
        kind = "missing"
        if exists:
            kind = "dir" if p.is_dir() else "file"
        rows.append({"path": raw, "purpose": purpose, "exists": exists, "type": kind})
        facts.add(f"path:{raw}", kind, "path", "os.path.exists")
    return rows


def discover_commands(facts: FactSet) -> list[dict]:
    """Locate real binaries and capture a real version string where cheap."""
    rows = []
    for cmd in CANDIDATE_COMMANDS:
        located = shutil.which(cmd)
        if not located:
            facts.add(f"command:{cmd}", None, "command", "shutil.which")
            rows.append({"command": cmd, "path": None, "version": None})
            continue
        version = None
        for flag in ("--version", "-version", "version"):
            code, out = _run([cmd, flag])
            if code == 0 and out.strip():
                version = out.strip().splitlines()[0][:120]
                break
        facts.add(f"command:{cmd}", located, "command", "shutil.which")
        if version:
            facts.add(f"version:{cmd}", version, "command", f"`{cmd} --version`")
        rows.append({"command": cmd, "path": located, "version": version})
    return rows


def _unit_for_pid(pid: int) -> str | None:
    """Map a PID to its owning systemd unit via /proc/<pid>/cgroup.

    This is what stops a new agent from claiming a port that belongs to a
    service they do not own.
    """
    cgroup = Path(f"/proc/{pid}/cgroup")
    try:
        raw = cgroup.read_text()
    except OSError:
        return None
    for line in raw.splitlines():
        _, _, paths = line.partition(":")
        for chunk in paths.split(","):
            chunk = chunk.strip()
            if not chunk.endswith((".service", ".scope")):
                continue
            unit = chunk.rsplit("/", 1)[-1]
            # Docker containers surface as a bare 64-hex id; not a unit name.
            if re.fullmatch(r"[0-9a-f]{12,64}", unit):
                continue
            return unit
    return None


def discover_ports(facts: FactSet) -> list[dict]:
    """Enumerate listening sockets and attribute each to its owning unit."""
    if not shutil.which("ss"):
        facts.add("ports", [], "port", "ss not installed")
        return []
    code, out = _run(["ss", "-tlnpH"])
    if code != 0:
        facts.add("ports", [], "port", f"ss exited {code}")
        return []

    rows: dict[int, dict] = {}
    for line in out.splitlines():
        fields = line.split()
        if len(fields) < 4 or fields[0].upper() != "LISTEN":
            continue
        local = fields[3]
        if local.startswith("["):
            host, _, port_s = local.rpartition("]:")
            host = host.lstrip("[")
        else:
            host, _, port_s = local.rpartition(":")
        try:
            port = int(port_s)
        except ValueError:
            continue

        pid_match = re.search(r"pid=(\d+)", line)
        pid = int(pid_match.group(1)) if pid_match else None
        proc_match = re.search(r'\("([^"]+)"', line)
        proc = proc_match.group(1) if proc_match else None
        unit = _unit_for_pid(pid) if pid else None

        existing = rows.get(port)
        if existing is None:
            rows[port] = {
                "port": port,
                "binds": [host],
                "process": proc,
                "pid": pid,
                "unit": unit,
                "owner": "systemd unit" if unit else "unattributed - verify before use",
            }
        else:
            # A port can be bound on both IPv4 and IPv6. It is still one occupied
            # port, so record every bind under the single entry.
            if host not in existing["binds"]:
                existing["binds"].append(host)
            if existing.get("unit") is None and unit:
                existing["unit"] = unit
                existing["owner"] = "systemd unit"
            if existing.get("process") is None and proc:
                existing["process"] = proc

    result = sorted(rows.values(), key=lambda r: r["port"])
    for row in result:
        facts.add(
            f"port:{row['port']}",
            {"binds": row["binds"], "unit": row["unit"], "process": row["process"]},
            "port",
            "ss -tlnpH + /proc/<pid>/cgroup",
        )
    return result


def discover_units(facts: FactSet) -> list[dict]:
    """List systemd units that are currently enabled or active."""
    if not shutil.which("systemctl"):
        facts.add("units", [], "unit", "systemctl not installed")
        return []
    code, out = _run(["systemctl", "list-units", "--type=service", "--all", "--no-pager"])
    if code != 0:
        facts.add("units", [], "unit", f"systemctl exited {code}")
        return []

    rows: dict[str, dict] = {}
    for line in out.splitlines():
        fields = line.split()
        if len(fields) < 4 or not fields[0].endswith(".service"):
            continue
        # systemctl pads with leading spaces, so index rather than partition.
        unit, load, active, sub = fields[0], fields[1], fields[2], fields[3]
        rows[unit] = {"unit": unit, "load": load, "active": active, "sub": sub}
        facts.add(f"unit:{unit}", active, "unit", "systemctl list-units")

    result = sorted(rows.values(), key=lambda r: r["unit"])
    return result


@dataclass
class Subsystem:
    name: str
    category: str
    directory: str
    description: str
    entry_points: list[str]
    packaged: bool
    test_files: int
    line_count: int


def discover_subsystems(facts: FactSet, sitemap: Path = SITEMAP_JSON) -> list[Subsystem]:
    """Read the generated sitemap index. Falls back to the filesystem."""
    rows: list[Subsystem] = []

    if sitemap.exists():
        try:
            data = json.loads(sitemap.read_text())
            for entry in data.get("subsystems", []):
                rows.append(
                    Subsystem(
                        name=entry.get("name", "?"),
                        category=entry.get("category", "?"),
                        directory=entry.get("dir", "?"),
                        description=(entry.get("description") or "").strip(),
                        entry_points=list(entry.get("entry_points") or []),
                        packaged=bool(entry.get("packaged")),
                        test_files=int(entry.get("test_files") or 0),
                        line_count=int(entry.get("line_count") or 0),
                    )
                )
            facts.add(
                "subsystems",
                len(rows),
                "subsystem",
                f"read {sitemap}",
            )
            return sorted(rows, key=lambda s: s.name)
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            pass

    # Filesystem fallback: name any immediate directory that looks like an organ.
    if MEM20_ROOT.is_dir():
        for child in sorted(MEM20_ROOT.iterdir()):
            if not child.is_dir() or child.name.startswith("."):
                continue
            rows.append(
                Subsystem(
                    name=child.name,
                    category="unindexed",
                    directory=str(child),
                    description="",
                    entry_points=[],
                    packaged=(child / "pyproject.toml").exists(),
                    test_files=len(list(child.glob("tests"))),
                    line_count=0,
                )
            )
        facts.add(
            "subsystems",
            len(rows),
            "subsystem",
            f"filesystem scan of {MEM20_ROOT} (sitemap unavailable)",
        )
    return rows


def discover_sitemap_age(facts: FactSet, sitemap: Path = SITEMAP_JSON) -> str | None:
    """How stale is the index? A stale sitemap makes every search suspect."""
    if not sitemap.exists():
        facts.add("sitemap_age", None, "index", f"{sitemap} absent")
        return None
    import datetime as _dt

    mtime = _dt.datetime.fromtimestamp(os.path.getmtime(sitemap), _dt.timezone.utc)
    age = (_dt.datetime.now(_dt.timezone.utc) - mtime).days
    facts.add("sitemap_generated", mtime.isoformat(), "index", "os.path.getmtime")
    return f"{age} day(s) old"


def survey(sitemap: Path = SITEMAP_JSON) -> tuple[FactSet, dict, list[Subsystem]]:
    """Run the full probe suite exactly once.

    Returns (facts, rows, subsystems). The CLI and the tests both go through
    here, so a test can never pass against a path the real command does not use.
    """
    facts = FactSet()
    rows = {
        "paths": discover_paths(facts),
        "commands": discover_commands(facts),
        "ports": discover_ports(facts),
        "units": discover_units(facts),
    }
    subs = discover_subsystems(facts, sitemap)
    discover_sitemap_age(facts, sitemap)
    return facts, rows, subs


def collect_all(sitemap: Path = SITEMAP_JSON) -> FactSet:
    """Run every probe and return the merged fact set."""
    facts, _, _ = survey(sitemap)
    return facts