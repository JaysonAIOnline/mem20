"""Read-only procfs and tty inspection used by the quiescence poller."""

from __future__ import annotations

import fcntl
import os
import struct
import termios
import time
from dataclasses import dataclass, field
from pathlib import Path

PROC = Path("/proc")
CLK_TCK = os.sysconf("SC_CLK_TCK")
TIOCGPGRP = 0x5405

CLOCK_TICKS_PER_SEC = CLK_TCK


@dataclass
class ProcInfo:
    pid: int
    comm: str
    state: str
    ppid: int
    tty_nr: int
    utime: int
    stime: int
    starttime: float
    children: list[int] = field(default_factory=list)

    @property
    def cpu_ticks(self) -> int:
        return self.utime + self.stime

    @property
    def cpu_seconds(self) -> float:
        return self.cpu_ticks / CLOCK_TICKS_PER_SEC

    def tty_path(self) -> str | None:
        if self.tty_nr <= 0:
            return None
        return _tty_from_nr(self.tty_nr)


def _tty_from_nr(tty_nr: int) -> str | None:
    major = (tty_nr >> 8) & 0xFFF
    minor = tty_nr & 0xFF
    if major == 136:
        return f"/dev/pts/{minor}"
    if major == 4:
        names = {0: "tty0", 1: "tty1", 2: "tty2", 3: "tty3", 4: "tty4", 5: "tty5"}
        return f"/dev/{names.get(minor, f'tty{minor}')}"
    return f"/dev/tty{major}-{minor}"


def boot_time() -> float:
    try:
        with (PROC / "stat").open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("btime "):
                    return float(line.split()[1])
    except OSError:
        pass
    return 0.0


def read_proc(pid: int) -> ProcInfo | None:
    path = PROC / str(pid) / "stat"
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    close = raw.rfind(")")
    if close < 0:
        return None
    comm = raw[raw.find("(") + 1 : close]
    fields = raw[close + 2 :].split()
    if len(fields) < 20:
        return None
    try:
        return ProcInfo(
            pid=pid,
            comm=comm,
            state=fields[0],
            ppid=int(fields[1]),
            tty_nr=int(fields[4]),
            utime=int(fields[11]),
            stime=int(fields[12]),
            starttime=float(fields[19]),
        )
    except (ValueError, IndexError):
        return None


def read_children(pid: int) -> list[int]:
    """Children across every thread of the process.

    /proc/<pid>/task/<tid>/children is per-thread, and a process may fork from
    any thread, so reading only the main task under-reports. Aggregate all
    tasks, then confirm with a full ppid scan when the result is empty.
    """
    children: set[int] = set()
    task_dir = PROC / str(pid) / "task"
    try:
        tids = os.listdir(task_dir)
    except OSError:
        return scan_children(pid)
    for tid in tids:
        try:
            data = (task_dir / tid / "children").read_text(encoding="utf-8")
        except OSError:
            continue
        for token in data.split():
            try:
                children.add(int(token))
            except ValueError:
                continue
    if not children:
        return scan_children(pid)
    return sorted(children)


def scan_children(pid: int) -> list[int]:
    found: list[int] = []
    try:
        entries = os.listdir(PROC)
    except OSError:
        return found
    for entry in entries:
        if not entry.isdigit():
            continue
        info = read_proc(int(entry))
        if info is not None and info.ppid == pid:
            found.append(info.pid)
    return found


def process_table() -> dict[int, ProcInfo]:
    """One /proc scan yielding every readable process, keyed by pid."""
    table: dict[int, ProcInfo] = {}
    try:
        entries = os.listdir(PROC)
    except OSError:
        return table
    for entry in entries:
        if not entry.isdigit():
            continue
        pid = int(entry)
        info = read_proc(pid)
        if info is not None:
            table[pid] = info
    return table


def descendants(pid: int, table: dict[int, ProcInfo] | None = None) -> list[int]:
    """All transitive children of pid, resolved through the full ppid tree."""
    if table is None:
        table = process_table()
    by_parent: dict[int, list[int]] = {}
    for child_pid, info in table.items():
        by_parent.setdefault(info.ppid, []).append(child_pid)
    found: list[int] = []
    queue = list(by_parent.get(pid, []))
    seen: set[int] = set()
    while queue:
        current = queue.pop(0)
        if current in seen or current == pid:
            continue
        seen.add(current)
        found.append(current)
        queue.extend(by_parent.get(current, []))
    return sorted(found)


def subtree_cpu_seconds(pid: int, table: dict[int, ProcInfo] | None = None) -> float | None:
    """Total CPU seconds burned by pid and all its descendants, or None if pid is gone."""
    if table is None:
        table = process_table()
    if pid not in table:
        return None
    total = table[pid].cpu_seconds
    for child in descendants(pid, table):
        total += table[child].cpu_seconds
    return total


def process_start_wallclock(pid: int, boot: float | None = None) -> float | None:
    info = read_proc(pid)
    if info is None:
        return None
    base = boot_time() if boot is None else boot
    return base + info.starttime / CLOCK_TICKS_PER_SEC


def foreground_pgrp(tty_path: str | None) -> int | None:
    if not tty_path:
        return None
    try:
        fd = os.open(tty_path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    except OSError:
        return None
    try:
        buf = struct.pack("i", 0)
        return struct.unpack("i", fcntl.ioctl(fd, termios.TIOCGPGRP, buf))[0]
    except OSError:
        return None
    finally:
        os.close(fd)


def pgrp_of(pid: int) -> int | None:
    try:
        return os.getpgid(pid)
    except OSError:
        return None


def now() -> float:
    return time.time()


def ppid_chain(pid: int, limit: int = 20) -> list[int]:
    chain = [pid]
    current = pid
    for _ in range(limit):
        info = read_proc(current)
        if info is None or info.ppid <= 1:
            break
        chain.append(info.ppid)
        current = info.ppid
    return chain


def ancestor_matching(pid: int, names: tuple[str, ...]) -> int | None:
    for candidate in ppid_chain(pid):
        info = read_proc(candidate)
        if info is not None and info.comm in names:
            return candidate
    return None
