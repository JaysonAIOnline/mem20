"""Dreams manager: read the dream store, review a dream, keep the ones worth keeping.

This is the review surface for ``mem20dreamz``. It imports the engine as a library
rather than shelling out to ``mem20-dream``, for two reasons: structured data
instead of parsed stdout, and one implementation of the rules rather than two that
can disagree. The one thing that *is* spawned is a run, because a run is a
multi-minute job with its own locking and exit-code contract - reimplementing that
here would mean reimplementing the fairness rule, and getting it wrong is exactly
how two dreams end up running at once.

Three rules this module holds to, because each one has a way of lying:

* **A refusal is never flattened into a generic error.** Promotion refuses on a
  hollow lineage and on a damaged braid chain, and those are different facts with
  different remedies. Both are reported with the engine's own wording.
* **The list never carries an artifact.** Lineages run to hundreds of kilobytes;
  a list that shipped them would move megabytes on every poll. The detail view
  fetches one dream.
* **"Already promoted" is directory-derived, and says so.** It is read from the
  promotions store on disk, not from the ledger, so a pack written elsewhere would
  not show up. That limitation is reported rather than papered over.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import uuid
from typing import Any

from mem20dreamz import audit as audit_mod
from mem20dreamz import engine as engine_mod
from mem20dreamz import idle as idle_mod
from mem20dreamz import promote as promote_mod
from mem20dreamz.lineage import Lineage, list_lineages

#: Where promotion packs are written. Matches the engine's own default so the
#: panel and the CLI cannot disagree about what "promoted" means.
PROMOTIONS_ROOT = os.environ.get("MEM20_CONTROL_PROMOTIONS", "/opt/mem20/store/promotions")

#: Run logs, beside the packs rather than inside them: a pack is a deliverable and
#: a log is not, and mixing them would put a growing file inside a portable
#: artefact that is supposed to be handed to somebody else.
RUN_LOG_DIR = os.environ.get("MEM20_CONTROL_DREAM_RUN_LOGS", "/opt/mem20/store/dream-runs")

#: A dream run spends real money: one iteration is a full panel of models. The
#: ceiling is the idle service's own TimeoutStartSec, so a browser-launched run is
#: bounded exactly like a timer-launched one.
MAX_RUN_ITERATIONS = 20
DEFAULT_RUN_ITERATIONS = 1
RUN_TIMEOUT_S = float(os.environ.get("MEM20_CONTROL_DREAM_RUN_TIMEOUT", "5400"))

#: Dream kinds the engine recognises. A `new` request for anything else is
#: refused rather than stored, so a typo cannot create a lineage that no filter
#: and no alert bar will ever match.
DREAM_KINDS = ("active", "idle_prototype", "idle_proposal", "idle_idea")

#: How much of a log tail a status read returns.
LOG_TAIL_LINES = 200

#: Run jobs, in memory. Deliberately not on disk: a job is a pointer to a process,
#: and a pointer that outlives the process it points at would report a run as live
#: when it is long dead. A restart loses the record, and `list_runs` says so.
_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()


class DreamError(Exception):
    """A refusal with a reason the UI can show. Never a generic failure."""


# --- promotion state ---------------------------------------------------------


def _promotion_dir(dream_id: str) -> str:
    return os.path.join(PROMOTIONS_ROOT, dream_id)


def promotion_state(dream_id: str) -> dict[str, Any]:
    """Whether a pack exists on disk for this dream, and how that was determined.

    Derived from the promotions directory, not from braid. That is cheap and
    reliable for packs written here, and it is *not* a ledger query - so it is
    labelled ``derived_from`` rather than presented as provenance.
    """
    target = _promotion_dir(dream_id)
    try:
        files = sorted(os.listdir(target))
    except OSError:
        files = []
    return {
        "promoted": bool(files),
        "path": target if files else None,
        "files": files,
        "derived_from": "promotions directory on disk",
        "not_derived_from": "braid ledger; a pack written elsewhere would not appear here",
    }


# --- reads -------------------------------------------------------------------


def _row(lineage: Lineage) -> dict[str, Any]:
    """One list row. Deliberately excludes the artifact and the critiques.

    A lineage's artifact reaches hundreds of kilobytes and its critiques hold every
    panelist's full reply. Neither belongs in a list the UI polls; both are one
    click away in the detail view.
    """
    status = lineage.status()
    scores = status.get("last_scores") or {}
    hollow = lineage.hollow
    return {
        **status,
        "hollow": hollow is not None,
        "hollow_why": (hollow or {}).get("why", ""),
        "hollow_iterations": (hollow or {}).get("iterations", []),
        "artifact_chars": scores.get("artifact_chars"),
        "fidelity": scores.get("fidelity"),
        "omission": scores.get("omission"),
        "last_iteration_at": scores.get("at"),
        "age_s": round(max(0.0, time.time() - float(lineage.created_at or time.time())), 1),
        **promotion_state(lineage.dream_id),
    }


def _epoch(value: Any) -> float | None:
    """Coerce a timestamp to a float, or None. Lineages are not uniformly well formed.

    ``score_history`` entries are written by several code paths over the engine's
    life, so a row's ``at`` can be missing or a string. Sorting on the raw value
    would then compare a float to a str and raise, taking the whole list down.
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _sort_key(row: dict[str, Any]) -> tuple[int, float, str]:
    """Newest first, with never-scored dreams after the scored ones.

    Every component is the same type for every row, because a sort key that
    compares a float against a str raises rather than sorting.
    """
    at = _epoch(row.get("last_iteration_at"))
    return (0 if at is None else 1, at if at is not None else 0.0, str(row.get("dream_id") or ""))


def dream_list(
    kind: str = "",
    include_hollow: bool = True,
    only_unpromoted: bool = False,
    limit: int = 0,
) -> dict[str, Any]:
    """Every lineage, newest first, as light rows.

    Hollow lineages are included by default but flagged, because hiding them would
    be worse than showing them: thirty-nine of them exist, every one a failed
    provider call that looks like a dream unless it is labelled.
    """
    started = time.time()
    rows = []
    for entry in list_lineages(kind):
        # `list_lineages` yields status dicts, not ids.
        lineage = Lineage.load(entry["dream_id"])
        if lineage is None:
            continue
        rows.append(_row(lineage))

    hidden_hollow = 0
    if not include_hollow:
        hidden_hollow = sum(1 for r in rows if r["hollow"])
        rows = [r for r in rows if not r["hollow"]]
    if only_unpromoted:
        rows = [r for r in rows if not r["promoted"]]
    rows.sort(key=_sort_key, reverse=True)
    total = len(rows)
    if limit and limit > 0:
        rows = rows[:limit]

    return {
        "dreams": rows,
        "total": total,
        "returned": len(rows),
        "hidden_hollow": hidden_hollow,
        "kinds": list(DREAM_KINDS),
        "promotions_root": PROMOTIONS_ROOT,
        "read_s": round(time.time() - started, 3),
        "artifacts_included": False,
        "artifacts_note": "the list carries no artifact text; fetch one dream for that",
    }


def dream_detail(dream_id: str) -> dict[str, Any]:
    """One lineage in full, including the artifact - the thing being reviewed."""
    lineage = Lineage.load(dream_id)
    if lineage is None:
        raise DreamError(f"no such dream: {dream_id}")

    payload = lineage.as_dict()
    payload["promotion"] = promotion_state(dream_id)
    payload["provenance"] = _provenance_summary(lineage)
    payload["kind_known"] = lineage.kind in DREAM_KINDS
    payload["critique_count"] = sum(len(i.critiques or []) for i in lineage.iterations)
    payload["artifact_chars"] = len(lineage.artifact)
    payload["best_iteration"] = lineage.best().n if lineage.best() else None
    return payload


def _provenance_summary(lineage: Lineage) -> dict[str, Any]:
    """Chain shape without proving it.

    Proving re-reads and re-verifies every node, which is a real cost, so the
    detail view reports the shape and the verify action reports the proof. Labelled
    ``verified`` only when something actually verified it.
    """
    return {
        "braid_cids": len(lineage.braid_cids),
        "uncommitted": len(lineage.uncommitted),
        "uncommitted_detail": lineage.uncommitted,
        "verified": None,
        "verify_with": "POST /api/dreams/verify",
    }


def dream_chain(dream_id: str) -> dict[str, Any]:
    lineage = Lineage.load(dream_id)
    if lineage is None:
        raise DreamError(f"no such dream: {dream_id}")
    return {
        "dream_id": dream_id,
        "iterations": lineage.iteration_count,
        "braid_committed": len(lineage.braid_cids),
        "uncommitted": lineage.uncommitted,
        "chain": [{"iteration": i + 1, "cid": cid} for i, cid in enumerate(lineage.braid_cids)],
    }


def dream_verify(dream_id: str) -> dict[str, Any]:
    """Re-prove every node. This is the only thing that reports ``verified: true``."""
    from mem20dreamz import ledger as ledger_mod

    lineage = Lineage.load(dream_id)
    if lineage is None:
        raise DreamError(f"no such dream: {dream_id}")
    if lineage.hollow:
        return {
            "dream_id": dream_id,
            "healthy": False,
            "checked": 0,
            "verified": 0,
            "broken": [],
            "note": (
                "this lineage is marked hollow: it recorded provider errors, not work. "
                "Its signatures may well verify - a signature proves the bytes are "
                "intact, not that a dream happened."
            ),
        }
    report = ledger_mod.verify_chain(lineage.braid_cids)
    return {"dream_id": dream_id, **report}


def dream_idle_stats() -> dict[str, Any]:
    """What idle dreaming has produced, plus who currently holds the run lock."""
    inventory = idle_mod.inventory()
    return {
        **inventory,
        "run_lock": idle_mod.active_run(),
    }


def manifest() -> dict[str, Any]:
    """Describe this manager for the UI."""
    return {
        "capabilities": [
            "list dream lineages with hollow and promoted flags",
            "read one lineage in full, artifact included",
            "re-prove a lineage's braid chain",
            "promote a lineage to a portable roadmap pack",
            "create a new dream from a seed",
            "run a dream as a bounded background job",
        ],
        "kinds": list(DREAM_KINDS),
        "default_kind": "active",
        "promotions_root": PROMOTIONS_ROOT,
        "run": {
            "max_iterations": MAX_RUN_ITERATIONS,
            "default_iterations": DEFAULT_RUN_ITERATIONS,
            "timeout_s": RUN_TIMEOUT_S,
            "cost_note": (
                "one iteration is a full panel of models; creating a dream costs "
                "nothing, running one is not free"
            ),
            "exit_codes": {
                "0": "finished",
                "2": "paused on a provider error, with everything that landed kept",
                "3": "refused: another run holds the lock",
            },
        },
        "promotion": {
            "writes": "a pack directory on disk, and one braid record naming the promotion",
            "refuses_on": ["a hollow lineage", "a braid chain that does not verify"],
            "force": "overwrites an existing pack for this dream only; other dreams are untouched",
        },
        "honesty": {
            "promoted_is": "derived from the promotions directory on disk",
            "promoted_is_not": "read from the ledger",
            "hollow": "39 of the lineages on this host recorded provider errors, not dreams",
        },
    }


# --- writes ------------------------------------------------------------------


def dream_promote(dream_id: str, force: bool = False) -> dict[str, Any]:
    """Promote a dream, surfacing the engine's own refusal wording.

    The engine refuses on a hollow lineage and on a damaged chain, and those
    deserve different words: one says "this was never a dream", the other says
    "this dream's provenance is broken". Both are returned as ``promoted: False``
    with the engine's reason, never as an exception the UI has to interpret.
    """
    try:
        return promote_mod.promote(dream_id, PROMOTIONS_ROOT, force=force)
    except FileNotFoundError as exc:
        raise DreamError(str(exc)) from exc
    except FileExistsError as exc:
        raise DreamError(str(exc)) from exc


def dream_new(seed: str, foundation: str = "", kind: str = "active") -> dict[str, Any]:
    """Create a lineage. Cheap: no model is called until it is run."""
    seed = (seed or "").strip()
    if not seed:
        raise DreamError("a dream needs a seed: the brief it starts from")
    if kind not in DREAM_KINDS:
        raise DreamError(f"unknown kind {kind!r}; expected one of {', '.join(DREAM_KINDS)}")
    if len(seed) > 4000:
        raise DreamError("the seed is too long; keep it to 4000 characters")
    lineage = engine_mod.new_dream(seed, kind=kind, foundation=foundation.strip() or seed)
    return {
        "dream_id": lineage.dream_id,
        "kind": lineage.kind,
        "state_path": lineage.state_path,
        "iterations": lineage.iteration_count,
        "costs_tokens": False,
        "note": "created but not run; nothing has been spent and no model has been called",
    }


# --- the run job -------------------------------------------------------------


def _interpret(exit_code: int | None) -> tuple[str, str]:
    """Map the CLI's exit code to a state and a sentence.

    These are the engine's own codes, kept distinct on purpose. Exit 2 is a pause
    with everything that landed preserved, and reporting it as a failure would
    tell the operator to throw away a run that is mostly intact.
    """
    if exit_code == 0:
        return "done", "finished; every requested iteration ran"
    if exit_code == 2:
        return "paused", (
            "paused on a provider error. Everything that landed was kept - resume by "
            "running it again."
        )
    if exit_code == 3:
        return "refused", "refused: another run already holds the lock"
    if exit_code is None:
        return "unknown", "the process ended without an exit code"
    return "failed", f"the run exited {exit_code}"


def _read_log_tail(path: str, limit: int = LOG_TAIL_LINES) -> list[str]:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read().splitlines()[-max(1, limit) :]
    except OSError:
        return []


def _watch(job_id: str, proc: subprocess.Popen, log_path: str, timeout_s: float) -> None:
    """Wait for the run, then record what actually happened.

    One thread per run, which the lock keeps to one. It reaps the child, applies
    the timeout, and writes the outcome - so a finished run is never left looking
    live just because nobody was watching.
    """
    timed_out = False
    try:
        exit_code = proc.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        timed_out = True
        proc.kill()
        try:
            exit_code = proc.wait(timeout=30)
        except subprocess.TimeoutExpired:  # pragma: no cover - the kill was ignored
            exit_code = None

    state, note = _interpret(exit_code)
    if timed_out:
        state = "failed"
        note = f"killed after {timeout_s:.0f}s, which is past the run ceiling"
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is not None:
            job.update(
                {
                    "status": state,
                    "note": note,
                    "exit_code": exit_code,
                    "finished_at": time.time(),
                    "duration_s": round(time.time() - job["started_at"], 1),
                    "timed_out": timed_out,
                }
            )


def start_run(dream_id: str, iterations: int = DEFAULT_RUN_ITERATIONS) -> dict[str, Any]:
    """Start a dream run in the background and return immediately.

    A run is minutes of panel work; the browser's request timeout is twenty
    seconds. So this spawns the engine's own CLI - which already owns the lock,
    the pause-on-outage behaviour and the exit-code contract - and hands back a
    job id to poll. Spawning the CLI rather than calling the engine in-process is
    deliberate: the CLI's lock discipline is the thing being relied upon, and
    reimplementing it here is how a second run sneaks in.
    """
    lineage = Lineage.load(dream_id)
    if lineage is None:
        raise DreamError(f"no such dream: {dream_id}")
    if lineage.hollow:
        raise DreamError(
            "refusing to run a hollow lineage: it recorded provider errors, not a dream. "
            "Create a new dream from the seed instead."
        )
    if lineage.done:
        raise DreamError(f"{dream_id} is already done; create a new dream to keep going")
    try:
        count = int(iterations)
    except (TypeError, ValueError) as exc:
        raise DreamError(f"iterations must be a whole number, got {iterations!r}") from exc
    if count < 1 or count > MAX_RUN_ITERATIONS:
        raise DreamError(f"iterations must be between 1 and {MAX_RUN_ITERATIONS}, got {count}")

    with _jobs_lock:
        for job in _jobs.values():
            if job["dream_id"] == dream_id and job["status"] == "running":
                raise DreamError(
                    f"a run for {dream_id} is already in flight "
                    f"(job {job['job_id']}, started {job['duration_note']})"
                )

    # A fast, friendly pre-check. The engine's own lock is the authority - this
    # only saves the caller a doomed spawn.
    holder = idle_mod.active_run()
    if holder is not None:
        who = holder.get("dream_id") or "another run"
        raise DreamError(f"{who} holds the run lock right now; wait for it to finish")

    job_id = f"run-{uuid.uuid4().hex[:12]}"
    os.makedirs(RUN_LOG_DIR, exist_ok=True)
    log_path = os.path.join(RUN_LOG_DIR, f"{job_id}.log")
    argv = [
        sys.executable,
        "-m",
        "mem20dreamz",
        "run",
        "--dream-id",
        dream_id,
        "--iterations",
        str(count),
    ]
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    # The child inherits the descriptor; the parent must drop its own copy or the
    # log can never be read as "finished" by anything watching the file.
    with open(log_path, "w", encoding="utf-8") as handle:
        try:
            proc = subprocess.Popen(
                argv,
                stdout=handle,
                stderr=subprocess.STDOUT,
                cwd="/opt/mem20",
                env=env,
                start_new_session=True,
            )
        except OSError as exc:
            raise DreamError(f"could not start the run: {type(exc).__name__}: {exc}") from exc

    job = {
        "job_id": job_id,
        "dream_id": dream_id,
        "iterations": count,
        "argv": argv,
        "pid": proc.pid,
        "status": "running",
        "note": "running",
        "exit_code": None,
        "started_at": time.time(),
        "finished_at": None,
        "duration_s": 0.0,
        "duration_note": "just started",
        "timed_out": False,
        "log_path": log_path,
    }
    with _jobs_lock:
        _jobs[job_id] = job
    threading.Thread(
        target=_watch, args=(job_id, proc, log_path, RUN_TIMEOUT_S), daemon=True
    ).start()
    return {**job, "log": _read_log_tail(log_path)}


def _decorate(job: dict[str, Any]) -> dict[str, Any]:
    out = dict(job)
    out["duration_note"] = (
        f"{job['duration_s']:.0f}s"
        if job.get("finished_at")
        else f"{time.time() - job['started_at']:.0f}s ago"
    )
    out["log"] = _read_log_tail(job["log_path"])
    out["log_lines"] = len(out["log"])
    return out


def run_status(job_id: str) -> dict[str, Any]:
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        raise DreamError(f"no such run job: {job_id}")
    return _decorate(job)


def list_runs() -> dict[str, Any]:
    with _jobs_lock:
        jobs = [_decorate(job) for job in _jobs.values()]
    jobs.sort(key=lambda j: j["started_at"], reverse=True)
    return {
        "jobs": jobs,
        "total": len(jobs),
        "running": sum(1 for j in jobs if j["status"] == "running"),
        "in_memory_only": True,
        "note": "run records live in this process; a restart forgets them, and a forgotten run is not a live one",
    }


def hollow_report() -> dict[str, Any]:
    """Read-only hollow census. Never marks and never writes to the ledger."""
    entries = audit_mod.find_hollow()
    return {
        "hollow_lineages": len(entries),
        "already_marked": sum(1 for e in entries if e.get("already_marked")),
        "unmarked": sum(1 for e in entries if not e.get("already_marked")),
        "hollow_iterations": sum(len(e["hollow_iterations"]) for e in entries),
        "read_only": True,
        "note": "this census only reads; marking and ledger records are a separate, explicit act",
        "entries": [
            {
                "dream_id": e["dream_id"],
                "kind": e["kind"],
                "iterations": [i["n"] for i in e["hollow_iterations"]],
                "already_marked": e.get("already_marked", False),
            }
            for e in entries
        ],
    }
