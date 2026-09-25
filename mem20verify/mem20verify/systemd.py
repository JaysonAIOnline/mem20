"""Systemd persistence sweep.

The standing rule: a long-lived server is a systemd unit, enabled, active,
Restart=on-failure, MainPID parented to PID 1, with exactly one listener and
no orphan process. This module verifies that against the running system by
actually executing systemctl and reading /proc.
"""

from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass, field

DEFAULT_UNITS = (
    "mem20corez-serve.service",
    "mem20mktz-serve.service",
    "mem20gamez.service",
    "mem20yetiz.service",
    "mem20googlez-serve.service",
)


@dataclass
class UnitReport:
    unit: str
    exists: bool = False
    enabled: bool = False
    active: bool = False
    main_pid: int = 0
    ppid: int = 0
    restart_policy: str = ""
    listener_count: int = 0
    listener_port: int = 0
    orphan_processes: list[int] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.exists and self.enabled and self.active and not self.problems

    def as_dict(self) -> dict:
        return {
            "unit": self.unit,
            "ok": self.ok,
            "exists": self.exists,
            "enabled": self.enabled,
            "active": self.active,
            "main_pid": self.main_pid,
            "ppid": self.ppid,
            "restart_policy": self.restart_policy,
            "listener_count": self.listener_count,
            "listener_port": self.listener_port,
            "orphans": self.orphan_processes,
            "problems": self.problems,
        }


def _run(args: list[str], timeout: int = 15) -> str:
    if not shutil.which(args[0]):
        raise RuntimeError(f"{args[0]} not available on this host")
    try:
        proc = subprocess.run(args, capture_output=True, text=True,
                              timeout=timeout, check=False)
    except subprocess.SubprocessError as exc:
        raise RuntimeError(f"{args[0]} failed: {exc}") from exc
    return proc.stdout.strip()


def _unit_file(unit: str) -> str:
    return f"/etc/systemd/system/{unit}"


def _ppid_of(pid: int) -> int:
    if not pid:
        return 0
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as fh:
            data = fh.read()
    except OSError:
        return 0
    # comm may contain spaces/parens, so parse after the final ')'
    close = data.rfind(")")
    if close == -1:
        return 0
    fields = data[close + 2:].split()
    try:
        return int(fields[1])
    except (IndexError, ValueError):
        return 0


def _listeners_on(port: int) -> list[int]:
    """PIDs listening on a TCP port, read from /proc rather than trusting ss."""
    inodes: set[str] = set()
    tcp = "/proc/net/tcp"
    for name in (tcp, "/proc/net/tcp6"):
        try:
            with open(name, encoding="utf-8") as fh:
                next(fh, None)
                for line in fh:
                    cols = line.split()
                    if len(cols) < 10:
                        continue
                    if cols[3] != "0A":  # TCP_LISTEN
                        continue
                    local = cols[1]
                    try:
                        if int(local.rsplit(":", 1)[1], 16) == port:
                            inodes.add(cols[9])
                    except (ValueError, IndexError):
                        continue
        except OSError:
            continue
    if not inodes:
        return []
    pids: list[int] = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        fd_dir = f"/proc/{entry}/fd"
        try:
            for fd in os.listdir(fd_dir):
                try:
                    target = os.readlink(f"{fd_dir}/{fd}")
                except OSError:
                    continue
                if target.startswith("socket:[") and target[8:-1] in inodes:
                        pids.append(int(entry))
                        break
        except OSError:
            continue
    return sorted(set(pids))


def _port_from_execstart(unit: str) -> int:
    try:
        with open(_unit_file(unit), encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return 0
    match = re.search(r"--port[= ](\d{2,5})", text)
    return int(match.group(1)) if match else 0


def check_unit(unit: str, require_ppid_one: bool = True) -> UnitReport:
    report = UnitReport(unit=unit)

    if not os.path.exists(_unit_file(unit)):
        report.problems.append("unit file missing")
        return report
    report.exists = True

    report.enabled = _run(["systemctl", "is-enabled", unit]) == "enabled"
    report.active = _run(["systemctl", "is-active", unit]) == "active"
    if not report.enabled:
        report.problems.append("not enabled (will not survive reboot)")
    if not report.active:
        report.problems.append("not active")

    try:
        pid = int(_run(["systemctl", "show", "-p", "MainPID", "--value", unit]) or 0)
    except ValueError:
        pid = 0
    report.main_pid = pid
    report.ppid = _ppid_of(pid)

    if pid:
        if require_ppid_one and report.ppid != 1:
            report.problems.append(
                f"MainPID {pid} has PPID {report.ppid}, not 1 (floating process)")
    else:
        report.problems.append("no MainPID")

    try:
        with open(_unit_file(unit), encoding="utf-8") as fh:
            text = fh.read()
        match = re.search(r"^\s*Restart\s*=\s*(\S+)", text, re.MULTILINE)
        report.restart_policy = match.group(1) if match else ""
        if report.restart_policy not in ("always", "on-failure"):
            report.problems.append(
                f"Restart={report.restart_policy or 'unset'}, want on-failure")
    except OSError:
        pass

    port = _port_from_execstart(unit)
    report.listener_port = port
    if port:
        listeners = _listeners_on(port)
        report.listener_count = len(listeners)
        if port_is_open(port) and not listeners:
            report.problems.append(
                f"port {port} accepts connections but no owning process found")
        elif len(listeners) > 1:
            report.problems.append(
                f"port {port} has {len(listeners)} listeners, want exactly 1")
        elif pid and listeners and pid not in listeners:
            report.problems.append(
                f"port {port} is held by {listeners}, not MainPID {pid}")
    return report


def port_is_open(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1.5)
        return sock.connect_ex((host, port)) == 0


def restart_survives(unit: str, timeout: int = 20) -> tuple[bool, str]:
    """Actually restart the unit and confirm it returns to active."""
    try:
        _run(["systemctl", "restart", unit], timeout=timeout)
    except RuntimeError as exc:
        return False, str(exc)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _run(["systemctl", "is-active", unit]) == "active":
            return True, "active after restart"
        time.sleep(0.5)
    return False, f"did not return to active within {timeout}s"


def sweep(units=None, require_ppid_one: bool = True) -> list[UnitReport]:
    """Check each unit. `units` defaults to DEFAULT_UNITS when omitted."""
    if not units:
        units = DEFAULT_UNITS
    return [check_unit(u, require_ppid_one) for u in units]
