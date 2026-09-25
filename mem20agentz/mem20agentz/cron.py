"""Cron — scheduled jobs (sub-phase 2.4).

Jobs are stored as JSON under <runtime>/cron/jobs.json:
    {name: {schedule, type, target, profile, enabled, runs}}

A small real cron parser supports: "*", "*/n", "a,b", "a-b" across
minute/hour/day-of-month/month/day-of-week. `next()` scans forward minute-by-
minute (max 24h lookahead). A job run records its outcome in the job's `runs`
list. `serve()` ticks a scheduler; `tick()` is the testable primitive.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import time
from typing import Optional

from .config import config_dir
from .profiles import Profiles

CRON_DIR = "cron"
JOBS_FILE = "jobs.json"


class CronParseError(ValueError):
    pass


def _parse_field(field: str, lo: int, hi: int) -> list[int]:
    values: set[int] = set()
    for token in field.split(","):
        token = token.strip()
        if not token:
            continue
        step = 1
        if "/" in token:
            token, _, step_s = token.partition("/")
            step = int(step_s)
            if step < 1:
                raise CronParseError("step must be >= 1")
        if token == "*":
            lo_v, hi_v = lo, hi
        elif "-" in token:
            a, _, b = token.partition("-")
            lo_v, hi_v = int(a), int(b)
        else:
            lo_v = hi_v = int(token)
        if lo_v < lo or hi_v > hi:
            raise CronParseError(f"value out of range: {lo}-{hi}")
        values.update(range(lo_v, hi_v + 1, step))
    if not values:
        raise CronParseError("empty field")
    return sorted(values)


class Schedule:
    def __init__(self, expr: str) -> None:
        parts = expr.split()
        if len(parts) != 5:
            raise CronParseError("schedule must have 5 fields "
                                 "(minute hour dom month dow)")
        try:
            self.minutes = _parse_field(parts[0], 0, 59)
            self.hours = _parse_field(parts[1], 0, 23)
            self.dom = _parse_field(parts[2], 1, 31)
            self.months = _parse_field(parts[3], 1, 12)
            self.dow = _parse_field(parts[4], 0, 6)
        except (ValueError, CronParseError) as exc:
            raise CronParseError(f"bad schedule {expr!r}: {exc}")

    def matches(self, t: time.struct_time) -> bool:
        if (t.tm_min not in self.minutes or t.tm_hour not in self.hours
                or t.tm_mon not in self.months):
            return False
        # day-of-month / day-of-week: if both are restricted, either match.
        dom_any = self.dom == list(range(1, 32))
        dow_any = self.dow == list(range(0, 7))
        if dom_any and dow_any:
            return True
        if dom_any:
            return t.tm_wday in self.dow
        if dow_any:
            return t.tm_mday in self.dom
        return (t.tm_mday in self.dom) or (t.tm_wday in self.dow)

    def next(self, after: Optional[time.struct_time] = None) -> time.struct_time:
        """Next scheduled time strictly after `after` (default now)."""
        cursor = time.localtime(time.mktime(after or time.localtime()) + 60)
        for _ in range(24 * 60 + 1):
            if self.matches(cursor):
                return cursor
            # advance one minute
            cursor = time.localtime(time.mktime(cursor) + 60)
        raise CronParseError("no match within 24h lookahead")


class Job:
    def __init__(self, name: str, schedule: str, type_: str = "prompt",
                 target: str = "", profile: str = "mem20",
                 enabled: bool = True) -> None:
        self.name = name
        self.schedule = Schedule(schedule)
        self.schedule_expr = schedule
        self.type = type_          # "prompt" | "command"
        self.target = target
        self.profile = profile
        self.enabled = enabled

    def to_dict(self) -> dict:
        return {"name": self.name, "schedule": self.schedule_expr,
                "type": self.type, "target": self.target,
                "profile": self.profile, "enabled": self.enabled}

    @classmethod
    def from_dict(cls, d: dict) -> "Job":
        return cls(name=str(d.get("name") or ""),
                   schedule=str(d.get("schedule") or ""),
                   type_=str(d.get("type") or "prompt"),
                   target=str(d.get("target") or ""),
                   profile=str(d.get("profile") or "mem20"),
                   enabled=bool(d.get("enabled", True)))


class Cron:
    def __init__(self, backend=None, root: Optional[pathlib.Path] = None,
                 runner=None) -> None:
        self._b = backend
        self.root = root or config_dir() / CRON_DIR
        self.path = self.root / JOBS_FILE
        self.runner = runner  # callable(job) -> result; default below

    # ----------------------------------------------------------- jobs
    def add(self, job: Job) -> None:
        jobs = self._load()
        jobs[job.name] = {**job.to_dict(), "runs": jobs.get(job.name, {}).get("runs", [])}
        self._save(jobs)

    def remove(self, name: str) -> bool:
        jobs = self._load()
        removed = jobs.pop(name, None) is not None
        self._save(jobs)
        return removed

    def list(self) -> list[dict]:
        return [{k: v for k, v in j.items() if k != "runs"}
                for j in self._load().values()]

    def list_jobs(self) -> list[dict]:
        """Alias of `list()` — matching the name used by the office/web
        surfaces (the scheduler has always exposed this as the canonical
        read)."""
        return self.list()

    def get(self, name: str) -> Optional[Job]:
        j = self._load().get(name)
        return Job.from_dict(j) if j else None

    def next_run(self, name: str) -> str:
        job = self.get(name)
        if job is None:
            raise KeyError(name)
        nxt = job.schedule.next()
        return time.strftime("%Y-%m-%d %H:%M:%S", nxt)

    # ----------------------------------------------------------- running
    def run(self, name: str, backend=None) -> dict:
        job = self.get(name)
        if job is None:
            raise KeyError(name)
        if job.type == "prompt":
            result = self._run_prompt(job, backend)
        elif job.type == "command":
            result = self._run_command(job)
        else:
            result = {"error": f"unknown job type: {job.type}"}
        self._record(name, result)
        return result

    def tick(self, backend=None, now: Optional[float] = None) -> list[str]:
        """Run every enabled job whose schedule matches `now`. Testable."""
        now = now if now is not None else time.time()
        now_t = time.localtime(now)
        ran = []
        for j in self._load().values():
            job = Job.from_dict(j)
            if not job.enabled:
                continue
            try:
                if job.schedule.matches(now_t):
                    job.type = str(job.type or "prompt")
                    job_proxy = Job.from_dict(j)
                    result = self.run(job_proxy.name, backend=backend)
                    ran.append({"name": job_proxy.name,
                                "ok": "error" not in result})
            except Exception as exc:  # noqa: BLE001
                ran.append({"name": job.name, "ok": False,
                            "error": str(exc)})
        return ran

    # ----------------------------------------------------------- helpers
    def _run_prompt(self, job: Job, backend=None) -> dict:
        if self.runner is not None:
            return self.runner(job) or {}
        if backend is None:
            return {"error": "no backend for prompt job (sealed?)"}
        from .agentz import AgentCore
        core = AgentCore(backend=backend, profile=job.profile,
                         approvals="auto", toolsets=("skills",))
        result = core.run(job.target)
        return {"ok": not result.blocked, "text": result.text}

    def _run_command(self, job: Job) -> dict:
        try:
            proc = subprocess.run(job.target, shell=True, capture_output=True,
                                  text=True, timeout=120)
            return {"ok": proc.returncode == 0, "stdout": proc.stdout[-400:]}
        except (subprocess.TimeoutExpired, OSError) as exc:
            return {"error": str(exc)}

    def _record(self, name: str, result: dict) -> None:
        jobs = self._load()
        jobs.setdefault(name, {}).setdefault("runs", []).append(
            {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
             "result": result})
        self._save(jobs)

    def _load(self) -> dict:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, jobs: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(jobs, indent=2), encoding="utf-8")


def serve(cron: Cron, backend=None, interval_s: float = 30.0,
          stop_event=None) -> None:
    """Blocking scheduler loop. Ctrl-C / stop_event to exit."""
    import threading
    stop = stop_event or threading.Event()
    while not stop.is_set():
        cron.tick(backend=backend)
        stop.wait(interval_s)