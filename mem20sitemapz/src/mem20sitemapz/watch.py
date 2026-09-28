"""Quiescence poller: waits until every target agent has genuinely stopped working."""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from . import procinfo

OPENCODE_DBUS = "/root/.local/share/opencode/opencode.db"

DEFAULT_WINDOW = 20.0
DEFAULT_STREAK = 3
DEFAULT_MAX_WAIT = 6 * 3600.0

AGENT_COMM_NAMES = ("opencode", "opencode serve")


@dataclass
class Sample:
    pid: int
    comm: str = ""
    alive: bool = False
    tty: str | None = None
    cpu_seconds: float = 0.0
    subtree_cpu_seconds: float = 0.0
    cpu_delta: float = 0.0
    subtree_cpu_delta: float = 0.0
    children: list[int] = field(default_factory=list)
    child_names: list[str] = field(default_factory=list)
    busy_children: list[str] = field(default_factory=list)
    owns_foreground: bool | None = None
    quiet_streak: int = 0
    quiescent: bool = False
    reasons: list[str] = field(default_factory=list)


@dataclass
class PollState:
    started_at: float
    window: float
    streak_required: int
    max_wait: float
    self_sessions: list[str] = field(default_factory=list)
    self_agent_pid: int | None = None
    samples: dict[int, Sample] = field(default_factory=dict)
    in_flight_others: list[str] = field(default_factory=list)
    finished: bool = False
    reason: str = ""

    def to_json(self) -> str:
        payload = asdict(self)
        payload["elapsed"] = round(time.time() - self.started_at, 1)
        return json.dumps(payload, indent=2, sort_keys=True)


def _opencode_db(path: str | Path = OPENCODE_DBUS) -> Path:
    return Path(path)


def in_flight_sessions(db: Path, self_sessions: Iterable[str], window: float) -> list[str]:
    if not db.is_file():
        return []
    cutoff = int((time.time() - window) * 1000)
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=2.0)
    except sqlite3.Error:
        return []
    try:
        rows = conn.execute(
            "select distinct session_id from part "
            "where json_extract(data,'$.state.status')='running' and time_updated >= ?",
            (cutoff,),
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.close()
    mine = set(self_sessions)
    return sorted({row[0] for row in rows} - mine)


def infer_self_sessions(
    db: Path,
    self_agent_pid: int | None,
    directory: str | None,
    window: float = 900.0,
) -> tuple[list[str], int | None]:
    if self_agent_pid is None:
        return [], None
    start = procinfo.process_start_wallclock(self_agent_pid)
    if start is None or not db.is_file():
        return [], self_agent_pid
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=2.0)
    except sqlite3.Error:
        return [], self_agent_pid
    try:
        if directory:
            rows = conn.execute(
                "select id, time_created from session where directory=? "
                "and time_created between ? and ?",
                (directory, int((start - window) * 1000), int((start + window) * 1000)),
            ).fetchall()
        else:
            rows = conn.execute(
                "select id, time_created from session where time_created between ? and ?",
                (int((start - window) * 1000), int((start + window) * 1000)),
            ).fetchall()
    except sqlite3.Error:
        return [], self_agent_pid
    finally:
        conn.close()
    if not rows:
        return [], self_agent_pid
    best = min(rows, key=lambda row: abs(row[1] / 1000.0 - start))
    return [best[0]], self_agent_pid


class Monitor:
    def __init__(
        self,
        pids: Iterable[int],
        self_sessions: Iterable[str] = (),
        self_agent_pid: int | None = None,
        window: float = DEFAULT_WINDOW,
        streak_required: int = DEFAULT_STREAK,
        max_wait: float = DEFAULT_MAX_WAIT,
        db: Path | None = None,
        clock: Callable[[], float] = time.time,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.pids = [int(p) for p in pids]
        self.db = db if db is not None else _opencode_db()
        self.clock = clock
        self.sleeper = sleeper
        self.state = PollState(
            started_at=clock(),
            window=window,
            streak_required=streak_required,
            max_wait=max_wait,
            self_sessions=list(self_sessions),
            self_agent_pid=self_agent_pid,
        )
        self._prev_cpu: dict[int, float] = {}
        self._prev_subtree: dict[int, float] = {}
        self._prev_child_cpu: dict[int, float] = {}

    def _observe(self, pid: int, table: dict[int, procinfo.ProcInfo]) -> Sample:
        sample = Sample(pid=pid)
        info = table.get(pid)
        if info is None:
            sample.quiescent = True
            sample.reasons.append("process-exited")
            return sample
        sample.alive = True
        sample.comm = info.comm
        sample.tty = info.tty_path()
        sample.cpu_seconds = info.cpu_seconds
        sample.cpu_delta = self._delta(self._prev_cpu, pid, sample.cpu_seconds)

        subtree = procinfo.subtree_cpu_seconds(pid, table)
        sample.subtree_cpu_seconds = subtree if subtree is not None else 0.0
        sample.subtree_cpu_delta = self._delta(self._prev_subtree, pid, sample.subtree_cpu_seconds)

        children = procinfo.descendants(pid, table)
        sample.children = children
        for child in children:
            child_info = table.get(child)
            if child_info is None:
                continue
            sample.child_names.append(f"{child}:{child_info.comm}")
            delta = self._delta(self._prev_child_cpu, child, child_info.cpu_seconds)
            if delta > 0.0:
                sample.busy_children.append(f"{child}:{child_info.comm}+{delta:.2f}s")

        pgrp = procinfo.pgrp_of(pid)
        fg = procinfo.foreground_pgrp(sample.tty)
        if pgrp is not None and fg is not None:
            sample.owns_foreground = fg == pgrp
        return sample

    def _delta(self, store: dict[int, float], key: int, value: float) -> float:
        previous = store.get(key)
        store[key] = value
        if previous is None:
            return 0.0
        return max(0.0, value - previous)

    def tick(self) -> bool:
        """One window. Returns True when every target is quiescent."""
        table = procinfo.process_table()
        for pid in self.pids:
            sample = self._observe(pid, table)
            previous = self.state.samples.get(pid)
            if previous is not None:
                sample.quiet_streak = previous.quiet_streak + 1
            self.state.samples[pid] = sample

        self.state.in_flight_others = in_flight_sessions(
            self.db, self.state.self_sessions, self.state.window * 2
        )

        for sample in self.state.samples.values():
            if not sample.alive:
                sample.quiescent = True
                sample.reasons = ["process-exited"]
                continue
            reasons = []
            if sample.cpu_delta > 0.0:
                reasons.append(f"cpu+{sample.cpu_delta:.2f}s")
            if sample.subtree_cpu_delta > 0.0:
                reasons.append(f"subtree+{sample.subtree_cpu_delta:.2f}s")
            if sample.busy_children:
                reasons.append("childwork:" + ",".join(sample.busy_children[:3]))
            if sample.owns_foreground is False:
                reasons.append("tty-owned-by-child")
            if reasons:
                sample.quiet_streak = 0
                sample.reasons = reasons
                sample.quiescent = False
            else:
                sample.reasons = ["silent"]
                sample.quiescent = sample.quiet_streak >= self.state.streak_required

        all_quiet = all(s.quiescent for s in self.state.samples.values())
        if all_quiet and self.state.in_flight_others:
            all_quiet = False
            for sample in self.state.samples.values():
                if sample.alive:
                    sample.reasons.append("other-session-in-flight")
                    sample.quiescent = False

        elapsed = self.clock() - self.state.started_at
        if all_quiet:
            self.state.finished = True
            self.state.reason = "all-targets-quiescent"
            return True
        if elapsed >= self.state.max_wait:
            self.state.finished = True
            self.state.reason = f"max-wait-exceeded-{int(elapsed)}s"
            return True
        return False

    def run(self, on_tick: Callable[[PollState], None] | None = None) -> bool:
        while True:
            done = self.tick()
            if on_tick is not None:
                on_tick(self.state)
            if done:
                return self.state.reason == "all-targets-quiescent"
            self.sleeper(self.state.window)

    def summary(self) -> dict[str, Any]:
        return {
            "finished": self.state.finished,
            "reason": self.state.reason,
            "quiescent": all(s.quiescent for s in self.state.samples.values()),
            "in_flight_others": self.state.in_flight_others,
            "self_sessions": self.state.self_sessions,
            "targets": {str(pid): asdict(s) for pid, s in self.state.samples.items()},
        }


def format_status(state: PollState) -> str:
    parts = [f"elapsed={int(time.time() - state.started_at)}s"]
    if state.in_flight_others:
        parts.append(f"other_sessions_in_flight={len(state.in_flight_others)}")
    for pid in sorted(state.samples):
        sample = state.samples[pid]
        mark = "QUIET" if sample.quiescent else "BUSY "
        detail = ",".join(sample.reasons) or "-"
        parts.append(
            f"{pid}:{mark}(streak={sample.quiet_streak}/{state.streak_required} {detail})"
        )
    return " | ".join(parts)
