"""Idle dreaming on a timer, and the fairness rule that protects real work.

The owner's rule: an active run always wins. When a run is in progress the timer
skips its turn entirely and resumes afterwards, so background dreaming can never
crowd out work somebody is actually waiting on.

Idle dreams are prototypes, proposals and ideas - not attempts at anyone's brief.
They land in braid whether or not they alert, so they are browsable later.

Alerts use a different bar per dream type, because a raw idle idea and a
forty-iteration refinement are not comparable: idle alerts on *novelty* (did it
find something nobody asked for?), long runs on *sustained improvement* with
fidelity held.
"""

from __future__ import annotations

import json
import os
import random
import sys
import time
from typing import Any

sys.path.insert(0, "/opt/mem20")

from llm import LLMError

from . import engine, seeds
from .lineage import Lineage, list_lineages

LOCK = os.environ.get("MEM20DREAM_IDLE_LOCK", "/opt/mem20/store/dreams/.active-run.lock")
STATE = os.path.join(os.path.dirname(LOCK), ".idle-state.json")
IDLE_KINDS = ("idle_prototype", "idle_proposal", "idle_idea")

#: An idle turn is wide and shallow, not long and deep. The creative sweet spot
#: is the hypnagogic edge: as little as fifteen seconds of N1 tripled insight
#: rates and the benefit vanished once participants reached N2. So the turn runs
#: several brief passes, each generating from every panelist at once and judged
#: only by arithmetic divergence, instead of a few iterations that critique,
#: forecast, invent and then hold a judged tournament.
IDLE_PASSES = 8
#: Writers per pass. Distinct models per candidate is what keeps the generations
#: genuinely different rather than eight samples of one voice.
IDLE_BREADTH = 6
#: Retained for the deep path (``mem20-dream run``), which is still the right
#: tool when a lineage needs a considered revision rather than a drift.
IDLE_ITERATIONS = 5

#: Novelty bar for idle dreams, on the omission axis. A short idle idea that
#: surfaces nothing genuinely new is not worth an interruption.
IDLE_NOVELTY_BAR = 55
#: A long run alerts when fidelity held and the artifact kept growing.
RUN_FIDELITY_BAR = 70
RUN_GROWTH_BAR = 1.0


# --- fairness ---------------------------------------------------------------


def _stale_window_s() -> float:
    return float(os.environ.get("MEM20DREAM_LOCK_STALE_S", "21600"))


def _read_lock() -> tuple[dict[str, Any] | None, str]:
    """Read the lock file. Returns (payload, problem).

    ``payload`` is None when the file is missing or unreadable; ``problem`` says
    which, so a caller can tell "nobody holds it" from "somebody holds it and the
    file is damaged" - two very different situations that both used to look like a
    truthy dict.
    """
    try:
        with open(LOCK, encoding="utf-8") as handle:
            raw = handle.read()
    except FileNotFoundError:
        return None, "no lock file"
    except OSError as exc:
        return None, f"unreadable: {type(exc).__name__}: {exc}"
    if not raw.strip():
        return None, "lock file is empty"
    try:
        payload = json.loads(raw)
    except ValueError as exc:
        return None, f"unparseable: {exc}"
    if not isinstance(payload, dict):
        return None, "lock file is not an object"
    return payload, ""


def _lock_age_s() -> float:
    try:
        return time.time() - os.path.getmtime(LOCK)
    except OSError:
        return 0.0


def _pid_alive(pid: Any) -> bool:
    """Whether a recorded pid still exists on this host.

    Used only to decide whether a stale lock may be taken over. If the pid cannot
    be established, the answer is "alive", so an unreadable pid errs towards
    refusing rather than towards double-dreaming.
    """
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return True
    if pid <= 0:
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, owned by another user
    except OSError:
        return True
    return True


def _holder_view(payload: dict[str, Any] | None, problem: str) -> dict[str, Any]:
    age = _lock_age_s()
    if payload is None:
        return {
            "dream_id": None,
            "token": None,
            "since": None,
            "age_s": round(age, 2),
            "unreadable": True,
            "parse_error": problem,
        }
    return {
        "dream_id": payload.get("dream_id"),
        "token": payload.get("token"),
        "since": payload.get("since"),
        "pid": payload.get("pid"),
        "age_s": round(age, 2),
        "unreadable": False,
    }


def active_run() -> dict[str, Any] | None:
    """Return the active run if one holds the lock, else None."""
    payload, problem = _read_lock()
    age = _lock_age_s()
    stale = age > _stale_window_s()
    if payload is None:
        # A missing lock is free. A damaged one is *not* free while it is fresh:
        # the file existing is itself evidence that a claim was made, and
        # pretending otherwise is how two runs end up dreaming at once.
        if problem == "no lock file" or stale:
            return None
        return _holder_view(None, problem)
    if stale:
        return None
    return _holder_view(payload, "")


def claim_active(dream_id: str) -> dict[str, Any]:
    """Claim the run lock exclusively. Returns a record; never raises.

    The claim used to be an unconditional write, which is enough to stop idle
    dreaming from crowding out a real run but does nothing about run versus run:
    the second writer silently replaced the first's claim, so both dreamed at once
    and the lock named whichever wrote last. That is survivable when a person runs
    one command at a time and is not survivable the moment a button can fire two
    requests.

    The file is created with O_EXCL so the check and the claim are one step, not
    two steps with a window between them.
    """
    token = f"{os.getpid()}-{time.time_ns()}"
    body = {"dream_id": dream_id, "since": time.time(), "token": token, "pid": os.getpid()}
    os.makedirs(os.path.dirname(LOCK) or ".", exist_ok=True)

    for attempt in (0, 1):
        try:
            handle = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            payload, problem = _read_lock()
            age = _lock_age_s()
            stale = age > _stale_window_s()
            # Take over only when the claim is provably abandoned: past the stale
            # window *and* the process that made it is gone. A stale lock whose pid
            # is still alive is a slow run, not a dead one, and stealing it would
            # cause exactly the collision this lock exists to prevent.
            if stale and (payload is None or not _pid_alive(payload.get("pid"))):
                try:
                    os.remove(LOCK)
                except OSError:
                    pass
                if attempt == 0:
                    continue
            holder = active_run()
            if holder is None:
                holder = _holder_view(payload, problem)
            return {
                "claimed": False,
                "lock": LOCK,
                "held_by": holder,
                "reason": _refusal_reason(holder, stale=stale),
            }
        except OSError as exc:
            return {
                "claimed": False,
                "lock": LOCK,
                "held_by": None,
                "reason": f"could not create the lock file: {type(exc).__name__}: {exc}",
            }
        try:
            os.write(handle, json.dumps(body).encode("utf-8"))
        except OSError as exc:
            # Do not leave a claim behind that we could not describe: an empty lock
            # file is a held lock nobody can attribute.
            os.close(handle)
            try:
                os.remove(LOCK)
            except OSError:
                pass
            return {
                "claimed": False,
                "lock": LOCK,
                "held_by": None,
                "reason": f"could not write the claim: {type(exc).__name__}: {exc}",
            }
        os.close(handle)
        return {"claimed": True, "lock": LOCK, **body}

    return {"claimed": False, "lock": LOCK, "held_by": None, "reason": "claim lost a race"}


def _refusal_reason(holder: dict[str, Any] | None, stale: bool = False) -> str:
    if holder is None:
        return "the run lock is held and could not be read"
    if holder.get("unreadable"):
        return (
            "the run lock is held by an unreadable claim "
            f"({holder.get('parse_error', 'unknown')}); remove {LOCK} if no run is alive"
        )
    who = holder.get("dream_id") or "an unidentified run"
    if stale:
        # Past the stale window but still running: not abandoned, just slow.
        return (
            f"{who} has held the run lock for {holder.get('age_s', 0)}s, past the stale "
            f"window, but its process is still alive; it is slow, not dead, so it is "
            "not being taken over"
        )
    return (
        f"{who} has held the run lock for {holder.get('age_s', 0)}s; "
        "wait for it to finish, or clear the lock if that run is gone"
    )


def release_active(token: str | None = None) -> dict[str, Any]:
    """Release the lock, but only if the caller is the one holding it.

    Ownership matters because a refused run also reaches its cleanup path. Before
    this, a run that was told to wait would delete the *incumbent's* lock on its
    way out - the collision the lock exists to prevent, caused by the cleanup.
    Passing no token keeps the unconditional behaviour for manual recovery.
    """
    if token is not None:
        payload, _ = _read_lock()
        held = (payload or {}).get("token")
        if held != token:
            return {
                "released": False,
                "reason": "the lock is not held by this claim; leaving it alone",
                "held_by": _holder_view(payload, "") if payload else None,
            }
    try:
        os.remove(LOCK)
        return {"released": True}
    except FileNotFoundError:
        return {"released": False, "reason": "no lock to release"}
    except OSError as exc:
        return {"released": False, "reason": f"{type(exc).__name__}: {exc}"}



# --- idle seeds -------------------------------------------------------------


def next_seed() -> str:
    """Draw an estate-derived seed that has never been issued before.

    There is no pool. The previous twelve hardcoded sentences were handed out
    with ``index % 12``, so the estate re-dreamed the same ideas forever; a
    canned list cannot know what exists. Seeds are now derived from live estate
    facts and the issued ledger is persisted, so a restart cannot reissue one.
    """
    state = _load_state()
    seed = seeds.next_seed(state)
    _save_state(state)
    return seed


# --- state ------------------------------------------------------------------


def _load_state() -> dict[str, Any]:
    try:
        with open(STATE, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {}


def _save_state(state: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2)
    os.replace(tmp, STATE)


# --- alerting ---------------------------------------------------------------


def _notify(title: str, message: str) -> dict[str, Any]:
    """Best-effort push via ntfy. Never fatal, but never silently pretended either.

    An alert that did not go out is reported as ``delivered: False`` with the
    reason, so a dream that claims it alerted can be checked.
    """
    topic = os.environ.get("NTFY_TOPIC", "mem20")
    try:
        import urllib.request

        request = urllib.request.Request(
            f"https://ntfy.sh/{topic}",
            data=message.encode("utf-8"),
            headers={"Title": title, "Priority": "default"},
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            return {"delivered": True, "service": "ntfy", "status": response.status}
    except Exception as exc:  # noqa: BLE001 - an alert must never stop dreaming
        return {
            "delivered": False,
            "service": "ntfy",
            "error": f"{type(exc).__name__}: {exc}",
        }


def judge_alert(lineage: Lineage) -> dict[str, Any]:
    """Different bar per dream type, as specified."""
    history = lineage.score_history
    if not history:
        return {"alert": False, "bar": "none yet", "reason": "no scored iteration"}

    latest = history[-1]

    if lineage.kind in IDLE_KINDS:
        novelty = float(latest.get("omission") or 0)
        inventions = len(lineage.inventions.entries)
        alert = novelty >= IDLE_NOVELTY_BAR or inventions >= 3
        return {
            "alert": alert,
            "bar": f"idle novelty >= {IDLE_NOVELTY_BAR} (or 3+ inventions)",
            "novelty": novelty,
            "inventions": inventions,
            "reason": "idle dream surfaced material nobody asked for"
            if alert
            else "idle dream found nothing worth interrupting for",
        }

    if len(history) < 3:
        return {"alert": False, "bar": "needs 3+ iterations", "reason": "too early to judge a run"}
    fidelities = [float(h.get("fidelity") or 0) for h in history]
    lengths = [int(h.get("artifact_chars") or 0) for h in history]
    held = sum(1 for f in fidelities if f >= RUN_FIDELITY_BAR) / len(fidelities)
    growth = lengths[-1] - max(lengths[: len(lengths) - 1] or [0])
    alert = held >= 0.8 and growth > 0
    return {
        "alert": alert,
        "bar": "fidelity held in >=80% of iterations and artifact still growing",
        "fidelity_held": round(held, 2),
        "artifact_growth": growth,
        "reason": "sustained improvement with the brief intact"
        if alert
        else "run has not yet shown sustained improvement",
    }


def alert_if_warranted(lineage: Lineage) -> dict[str, Any]:
    verdict = judge_alert(lineage)
    verdict["notification"] = {"attempted": False}
    if verdict.get("alert"):
        title = f"mem20 dream: {lineage.kind} {lineage.dream_id}"
        message = (
            f"{verdict.get('reason')}\n"
            f"iterations={lineage.iteration_count} "
            f"inventions={len(lineage.inventions.entries)}\n"
            f"bar: {verdict.get('bar')}"
        )
        verdict["notification"] = {"attempted": True, **_notify(title, message)}
    return verdict


# --- the timer turn ---------------------------------------------------------


def idle_turn() -> dict[str, Any]:
    """One idle turn: IDLE_ITERATIONS of real dreaming.

    Skips entirely when an active run holds the lock. If the panel goes dark
    partway through, the iterations already committed stay committed and the
    lineage pauses with the reason - it does not keep calling into a dead
    provider, and it does not pretend the remaining iterations happened.
    """
    # Claimed before the seed is drawn: the point of the claim is to stop work
    # starting, so it has to happen first. The holder is named by kind and pid -
    # the turn's own dream_id is not known yet, and guessing one would be a lie.
    claim = claim_active("idle-dreaming")
    if not claim.get("claimed"):
        held = claim.get("held_by") or {}
        return {
            "skipped": True,
            "reason": f"another run holds the lock; idle dreaming yields ({claim.get('reason', '')})",
            "active_dream_id": held.get("dream_id"),
        }

    seed = next_seed()
    kind = random.choice(IDLE_KINDS)
    lineage = engine.new_dream(seed, kind=kind, foundation=seed)

    last: Any = None
    committed = 0
    uncommitted = 0
    paused_reason = ""
    try:
        # The hypnagogic shape: many brief, unjudged passes rather than a few
        # long convergent ones. Fifteen seconds of N1 tripled insight and the
        # effect vanished at N2, so the turn is now wide and shallow.
        for pass_n in range(1, IDLE_PASSES + 1):
            if lineage.done:
                break
            result = engine.nap_pass(lineage, seed, pass_n, breadth=IDLE_BREADTH)
            if not result["accepted"]:
                paused_reason = result["reason"]
                break
            if result.get("braid"):
                committed += 1
            else:
                uncommitted += 1
            last = lineage.iterations[-1] if lineage.iterations else None
    except LLMError as exc:
        # A provider outage is not an iteration. Keep what genuinely happened,
        # say plainly where it stopped, and wait for the next tick.
        paused_reason = str(exc)[:400]
        lineage.paused = True
        lineage.pause_reason = paused_reason
        lineage.save()
    finally:
        # Released even on an outage or a crash, so a dead turn cannot wedge the
        # next run - and released by token, so a turn that lost the claim on the
        # way out cannot delete somebody else's.
        release_active(claim.get("token"))

    verdict = alert_if_warranted(lineage)
    state = _load_state()
    state["last_idle_turn"] = {
        "at": time.time(),
        "dream_id": lineage.dream_id,
        "kind": kind,
        "seed": seed[:120],
        "iterations_run": lineage.iteration_count,
        "passes_planned": IDLE_PASSES,
        "committed": committed,
        "uncommitted": uncommitted,
        "fidelity": last.fidelity.get("score") if last else None,
        "omission": last.omission.get("score") if last else None,
        "inventions": len(lineage.inventions.entries),
        "paused": bool(paused_reason),
        "pause_reason": paused_reason,
        "alerted": verdict.get("alert"),
        "alert_delivered": verdict.get("notification", {}).get("delivered"),
    }
    _save_state(state)

    return {
        "skipped": False,
        "dream_id": lineage.dream_id,
        "kind": kind,
        "seed": seed,
        "iterations_run": lineage.iteration_count,
        "passes_planned": IDLE_PASSES,
        "committed": committed,
        "uncommitted": uncommitted,
        "paused": bool(paused_reason),
        "pause_reason": paused_reason,
        "fidelity": last.fidelity.get("score") if last else None,
        "omission": last.omission.get("score") if last else None,
        "inventions": len(lineage.inventions.entries),
        "alert": verdict,
    }


def inventory() -> dict[str, Any]:
    """Everything idle dreaming has produced, browsable later."""
    rows = list_lineages()
    idle = [r for r in rows if r["kind"] in IDLE_KINDS]
    return {
        "active_run": active_run(),
        "idle_dreams": len(idle),
        "active_dreams": len([r for r in rows if r["kind"] == "active"]),
        "passes_per_turn": IDLE_PASSES, "writers_per_pass": IDLE_BREADTH,
        "state": _load_state().get("last_idle_turn"),
        "alert_bars": {
            "idle_novelty_bar": IDLE_NOVELTY_BAR,
            "run_fidelity_bar": RUN_FIDELITY_BAR,
            "run_needs_iterations": 3,
        },
        "dreams": idle[-25:],
    }
