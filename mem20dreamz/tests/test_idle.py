"""Tests for idle dreaming: fairness first, then the per-type alert bars."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from mem20dreamz import engine, idle
from mem20dreamz.lineage import Lineage


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    """Point the lock, state and lineage store at a temp dir; no braid."""
    monkeypatch.setattr(idle, "LOCK", str(tmp_path / "active.lock"))
    monkeypatch.setattr(idle, "STATE", str(tmp_path / "idle-state.json"))
    monkeypatch.setattr("mem20dreamz.lineage.STORE", str(tmp_path / "dreams"))
    monkeypatch.setattr(idle, "_notify", lambda title, message: {"delivered": True, "stub": True})
    yield


@pytest.fixture(autouse=True)
def _no_real_model_calls(monkeypatch):
    """A test in this module must never reach a provider.

    idle_turn() was switched from run_iteration() to nap_pass(), and because the
    tests mocked only the old path the suite hung on live Cohere and Groq calls
    for ten minutes. A test that can make a network call is a defect, so the
    failure is moved to the front: any unmocked dreaming call raises here rather
    than waiting on a provider.
    """

    def _refuse(*args, **kwargs):
        raise AssertionError(
            "a test reached the real dreaming path; mock engine.nap_pass or engine.run_iteration"
        )

    monkeypatch.setattr(engine, "nap_pass", _refuse)
    monkeypatch.setattr(engine, "run_iteration", _refuse)
    monkeypatch.setattr(engine, "nap", _refuse)


def _stub_pass(pass_n, *, accepted=True, braid=True, **extra):
    """A hypnagogic pass that mirrors nap_pass's real side effects, no model.

    The stub has to record the iteration, append the braid cid or the
    uncommitted reason, and save - otherwise a test asserting on the reloaded
    lineage is asserting on a lineage that was never written.
    """

    def _pass(lineage, cue, n, breadth=None):
        if not accepted:
            return {"pass": n, "accepted": False, "reason": "stubbed stop", "errors": [], "candidates": []}
        iteration = _stub_iteration(len(lineage.iterations) + 1)
        lineage.record(iteration)
        if braid:
            lineage.braid_cids.append(f"br{iteration.n}")
        else:
            lineage.uncommitted.append({"at_pass": n, "reason": "braid down (stub)"})
        lineage.save()
        result = {"pass": n, "accepted": True, "braid": braid, "genesis": False, "errors": []}
        result.update(extra)
        return result

    return _pass


# --- fairness ---------------------------------------------------------------


def test_idle_yields_to_an_active_run():
    idle.claim_active("dream-running")
    result = idle.idle_turn()
    assert result["skipped"] is True
    assert "yields" in result["reason"]
    assert result["active_dream_id"] == "dream-running"


def test_no_active_run_means_no_lock_is_reported():
    assert idle.active_run() is None


def test_stale_lock_does_not_block_forever(monkeypatch):
    """A crashed run must not wedge idle dreaming permanently."""
    idle.claim_active("dream-crashed")
    old = time.time() - 60 * 60 * 24
    os.utime(idle.LOCK, (old, old))
    monkeypatch.setenv("MEM20DREAM_LOCK_STALE_S", "3600")
    assert idle.active_run() is None, "a lock older than the stale window must not count as active"


def test_release_removes_the_lock():
    idle.claim_active("dream-x")
    assert os.path.exists(idle.LOCK)
    idle.release_active()
    assert not os.path.exists(idle.LOCK)
    idle.release_active()  # releasing twice must not raise


# --- a claim is exclusive: run versus run -------------------------------------
#
# The defect these cover: `claim_active` used to write the lock file
# unconditionally. That is enough to stop idle dreaming from crowding out a real
# run, but nothing stopped a *second run* from overwriting the first run's claim.
# Harmless when a person types one command at a time; not harmless the moment a
# web button can fire two requests, because both processes then dream
# concurrently and the lock names whichever wrote last.


def test_a_second_claim_cannot_steal_an_active_run():
    first = idle.claim_active("dream-first")
    assert first["claimed"] is True

    second = idle.claim_active("dream-second")
    assert second["claimed"] is False, "a held lock must refuse a second claim"
    assert second["held_by"]["dream_id"] == "dream-first"

    # The refusal must not have disturbed the incumbent's claim.
    assert idle.active_run()["dream_id"] == "dream-first"


def test_a_refused_claim_explains_itself():
    """A refusal nobody can act on is a refusal nobody can act on."""
    idle.claim_active("dream-first")
    second = idle.claim_active("dream-second")
    assert second["claimed"] is False
    assert second["reason"], "a refusal must say why"
    assert "dream-first" in second["reason"], "the refusal must name the holder"


def test_an_abandoned_lock_is_taken_over_rather_than_refused(monkeypatch):
    """A crashed run must not block the next one for ever."""
    monkeypatch.setenv("MEM20DREAM_LOCK_STALE_S", "3600")
    _write_lock({"dream_id": "dream-crashed", "pid": _a_dead_pid()}, age_s=60 * 60 * 24)

    takeover = idle.claim_active("dream-next")
    assert takeover["claimed"] is True
    assert idle.active_run()["dream_id"] == "dream-next"


def test_a_slow_run_is_not_stolen_from(monkeypatch):
    """Stale is not the same as dead.

    A run that is merely slow still holds a claim it is honouring. Taking it over
    would start a second run dreaming against the same estate - the collision the
    lock exists to prevent, just with a longer fuse.
    """
    monkeypatch.setenv("MEM20DREAM_LOCK_STALE_S", "3600")
    _write_lock({"dream_id": "dream-slow", "pid": os.getpid()}, age_s=60 * 60 * 24)

    refused = idle.claim_active("dream-next")
    assert refused["claimed"] is False
    assert refused["held_by"]["dream_id"] == "dream-slow"
    assert "still alive" in refused["reason"]


def test_an_unreadable_pid_is_treated_as_alive(monkeypatch):
    """A pid we cannot establish must not license a takeover."""
    monkeypatch.setenv("MEM20DREAM_LOCK_STALE_S", "3600")
    _write_lock({"dream_id": "dream-unknown-pid", "pid": "not-a-pid"}, age_s=60 * 60 * 24)

    refused = idle.claim_active("dream-next")
    assert refused["claimed"] is False, "an unestablished pid must err towards refusing"
    assert refused["held_by"]["dream_id"] == "dream-unknown-pid"


def _write_lock(body: dict, age_s: float) -> None:
    """Put a lock file on disk with a chosen payload and mtime."""
    os.makedirs(os.path.dirname(idle.LOCK) or ".", exist_ok=True)
    body = {"since": time.time() - age_s, "token": "t-pretend", **body}
    with open(idle.LOCK, "w", encoding="utf-8") as handle:
        json.dump(body, handle)
    stamp = time.time() - age_s
    os.utime(idle.LOCK, (stamp, stamp))


def _a_dead_pid() -> int:
    """A pid that has certainly exited, so it is safe to treat as abandoned."""
    import subprocess

    proc = subprocess.Popen(["/bin/true"])
    proc.wait()
    return proc.pid


def test_release_only_frees_a_lock_the_caller_owns():
    """A refused run must not delete the incumbent's lock on its way out."""
    held = idle.claim_active("dream-first")
    refused = idle.claim_active("dream-second")
    assert refused["claimed"] is False

    # The loser tries to clean up with its own (never-granted) token.
    idle.release_active(refused.get("token", "not-a-real-token"))
    assert os.path.exists(idle.LOCK), "releasing with a foreign token must not free the lock"
    assert idle.active_run()["dream_id"] == "dream-first"

    idle.release_active(held["token"])
    assert not os.path.exists(idle.LOCK)


def test_an_unreadable_lock_is_reported_as_held_not_as_free():
    """An empty lock file proves somebody claimed it; it does not prove who."""
    os.makedirs(os.path.dirname(idle.LOCK), exist_ok=True)
    with open(idle.LOCK, "w", encoding="utf-8") as handle:
        handle.write("")
    running = idle.active_run()
    assert running is not None
    assert running.get("dream_id") is None
    assert "parse_error" in running or running.get("stale") is True


def test_idle_turn_holds_the_lock_while_it_works(monkeypatch):
    """The gap a run can slip through: idle checked the lock, then did not hold it.

    The turn takes minutes. Without holding the claim, a run started during those
    minutes would proceed and the two would dream concurrently - the exact
    collision the claim exists to prevent.
    """
    monkeypatch.setattr(idle.engine, "new_dream", lambda *a, **k: Lineage(
        dream_id="dream-idle-holds", seed="s", kind="idle_idea", foundation="s", artifact="s"
    ))
    seen_lock = {}

    def _pass(lineage, cue, n, breadth=None):
        seen_lock["held"] = idle.active_run()
        iteration = _stub_iteration(len(lineage.iterations) + 1)
        lineage.record(iteration)
        return {"pass": n, "accepted": True, "braid": True, "genesis": False, "errors": []}

    monkeypatch.setattr(idle.engine, "nap_pass", _pass)
    monkeypatch.setattr(idle, "alert_if_warranted", lambda ln: {"alert": False})

    result = idle.idle_turn()
    assert result["skipped"] is False
    assert seen_lock["held"] is not None, "the idle turn must hold the claim while it iterates"
    # Named by kind, not by dream id: at claim time the turn has no dream yet, and
    # putting a not-yet-existing id in the lock would be a lie an operator reads.
    assert seen_lock["held"].get("dream_id") == "idle-dreaming"


def test_idle_turn_releases_the_claim_when_it_finishes(monkeypatch):
    monkeypatch.setattr(idle.engine, "new_dream", lambda *a, **k: Lineage(
        dream_id="dream-idle-release", seed="s", kind="idle_idea", foundation="s", artifact="s"
    ))
    monkeypatch.setattr(idle.engine, "nap_pass", _stub_pass(1))
    monkeypatch.setattr(idle, "alert_if_warranted", lambda ln: {"alert": False})

    idle.idle_turn()
    assert not os.path.exists(idle.LOCK), "an idle turn must not wedge the next run"


def test_cli_run_refuses_when_another_run_holds_the_claim(tmp_path, monkeypatch):
    """The user-visible consequence: a refusal, and no iteration spent."""
    from mem20dreamz import __main__ as cli

    monkeypatch.setattr("mem20dreamz.lineage.STORE", str(tmp_path / "dreams"))
    monkeypatch.setattr(idle, "LOCK", str(tmp_path / "active.lock"))
    monkeypatch.setattr(idle, "STATE", str(tmp_path / "idle-state.json"))

    lineage = Lineage(dream_id="dream-busy", seed="s", foundation="f", artifact="a")
    lineage.save()

    ran = []
    monkeypatch.setattr(engine, "run_iteration", lambda ln, n: ran.append(n))

    idle.claim_active("dream-already-running")
    code = cli.main(["run", "--dream-id", "dream-busy", "--iterations", "1"])

    assert code == 3, "a refused claim must exit 3, distinct from 2 (paused) and 0 (done)"
    assert ran == [], "a refused run must not spend a single iteration"
    assert idle.active_run()["dream_id"] == "dream-already-running", "the incumbent keeps the lock"


# --- alert bars differ by dream type ----------------------------------------


def _lineage(kind: str, scores: list[tuple[float, float]], chars: list[int]) -> Lineage:
    lineage = Lineage(dream_id=f"dream-test-{kind}", seed="s", kind=kind, foundation="s", artifact="s")
    for index, (fidelity, omission) in enumerate(scores, start=1):
        lineage.score_history.append(
            {
                "n": index,
                "fidelity": fidelity,
                "omission": omission,
                "artifact_chars": chars[index - 1],
                "accepted": True,
                "at": time.time(),
            }
        )
    return lineage


def test_idle_dream_alerts_on_novelty_not_volume():
    """A short idle idea alerting is the point: novelty, not depth."""
    quiet = _lineage("idle_idea", [(100, 20)], [200])
    assert idle.judge_alert(quiet)["alert"] is False

    lively = _lineage("idle_idea", [(100, 80)], [200])
    verdict = idle.judge_alert(lively)
    assert verdict["alert"] is True
    assert "novelty" in verdict["bar"]


def test_active_run_does_not_alert_on_a_single_good_iteration():
    """One good iteration is not a trend, and must not interrupt anybody."""
    lineage = _lineage("active", [(95, 90)], [1000])
    verdict = idle.judge_alert(lineage)
    assert verdict["alert"] is False
    assert "3+" in verdict["bar"]


def test_active_run_alerts_only_when_fidelity_held_and_still_growing():
    declining = _lineage("active", [(95, 90), (95, 90), (95, 90)], [1000, 900, 800])
    assert idle.judge_alert(declining)["alert"] is False, "shrinking artifact is not improvement"

    growing = _lineage("active", [(95, 90), (95, 90), (95, 90)], [1000, 1200, 1500])
    verdict = idle.judge_alert(growing)
    assert verdict["alert"] is True
    assert verdict["fidelity_held"] == 1.0
    assert verdict["artifact_growth"] == 300


def test_fidelity_collapse_blocks_a_run_alert():
    """Growth is not enough if the brief was abandoned."""
    leaky = _lineage("active", [(95, 90), (40, 90), (95, 90)], [1000, 1200, 1500])
    verdict = idle.judge_alert(leaky)
    assert verdict["alert"] is False


def test_empty_history_never_alerts():
    assert idle.judge_alert(_lineage("active", [], []))["alert"] is False


# --- notification honesty ---------------------------------------------------


def test_failed_alert_is_reported_as_not_delivered(monkeypatch):
    """A dream must not claim it alerted when the push did not go out."""
    monkeypatch.setattr(
        idle, "_notify", lambda t, m: {"delivered": False, "error": "boom"}
    )
    lineage = _lineage("idle_idea", [(100, 90)], [200])
    verdict = idle.alert_if_warranted(lineage)
    assert verdict["alert"] is True
    assert verdict["notification"]["delivered"] is False
    assert verdict["notification"]["error"] == "boom"


def test_successful_alert_records_delivery():
    lineage = _lineage("idle_idea", [(100, 90)], [200])
    verdict = idle.alert_if_warranted(lineage)
    assert verdict["notification"]["delivered"] is True


def test_quiet_dream_does_not_attempt_an_alert(monkeypatch):
    calls = []
    monkeypatch.setattr(idle, "_notify", lambda t, m: calls.append(t) or {"delivered": True})
    idle.alert_if_warranted(_lineage("idle_idea", [(100, 10)], [200]))
    assert calls == [], "nothing worth interrupting for means no push"


# --- state and inventory ----------------------------------------------------


def test_seed_advances_and_never_wraps():
    """The pool used to wrap: seed N+12 repeated seed N.

    That was twelve invented sentences on a 336-directory estate, and the
    engine re-dreamed the same ideas forever. It must now advance and refuse to
    repeat rather than wrap quietly.
    """
    first = idle.next_seed()
    second = idle.next_seed()
    assert first != second
    with open(idle.STATE, encoding="utf-8") as handle:
        state = json.load(handle)
    assert state["seed_index"] == 2
    assert first in state["seeds_issued"]
    assert second in state["seeds_issued"]
    assert not hasattr(idle, "SEED_POOL")


def test_inventory_reports_bars_and_browsable_dreams():
    listing = idle.inventory()
    assert listing["alert_bars"]["idle_novelty_bar"] == idle.IDLE_NOVELTY_BAR
    assert listing["alert_bars"]["run_fidelity_bar"] == idle.RUN_FIDELITY_BAR
    assert isinstance(listing["dreams"], list)
    assert "idle_novELITY_BAR" not in json.dumps(listing)


def test_state_write_is_atomic():
    """A half-written state file would silently reset the idle cycle."""
    idle._save_state({"seed_index": 7})
    assert not os.path.exists(idle.STATE + ".tmp")
    assert json.loads(Path(idle.STATE).read_text())["seed_index"] == 7


# --- a turn is many brief passes, not one deep iteration -------------------


def _stub_iteration(n: int):
    from mem20dreamz.lineage import Iteration

    return Iteration(
        n=n,
        artifact=f"draft {n}",
        fidelity={"score": 90.0},
        omission={"score": 40.0, "summary": "tightened the copy"},
        forecast={},
        critiques=[{"kind": "critique", "role": "ux_architect", "text": "t"}],
        inventions_added=[f"invention {n}"],
        dreamer_evolved=True,
        accepted=True,
    )


def test_idle_turn_runs_the_full_pass_count(monkeypatch):
    """The constant was declared but never wired; this is the guard for that.

    It used to assert five deep iterations. The turn is now wide and shallow:
    eight brief passes, because the creative effect lives at the hypnagogic
    edge and dies at depth.
    """
    assert idle.IDLE_PASSES == 8, "the turn is 8 brief passes, not 5 deep iterations"
    assert idle.IDLE_BREADTH == 6, "six writers per pass, so generations differ"
    seen = []
    monkeypatch.setattr(idle.engine, "new_dream", lambda *a, **k: Lineage(
        dream_id="dream-idle-deep", seed="s", kind="idle_idea", foundation="s", artifact="s"
    ))
    monkeypatch.setattr(idle.engine, "nap_pass", lambda ln, cue, n, breadth=None: (
        seen.append(n), _stub_pass(n)(ln, cue, n, breadth)
    )[1])
    monkeypatch.setattr(idle, "alert_if_warranted", lambda ln: {"alert": False})

    result = idle.idle_turn()
    assert seen == list(range(1, idle.IDLE_PASSES + 1)), seen
    assert result["iterations_run"] == idle.IDLE_PASSES
    assert result["committed"] == idle.IDLE_PASSES
    assert result["uncommitted"] == 0
    assert result["paused"] is False


def test_a_provider_outage_midway_pauses_and_keeps_real_work(monkeypatch):
    """Keep the iterations that happened; never invent the ones that did not."""
    from llm import LLMError

    monkeypatch.setattr(idle.engine, "new_dream", lambda *a, **k: Lineage(
        dream_id="dream-idle-outage", seed="s", kind="idle_idea", foundation="s", artifact="s"
    ))
    monkeypatch.setattr(idle.engine, "nap_pass", lambda ln, cue, n, breadth=None: (
        (_ for _ in ()).throw(LLMError("no panelist answered; name resolution"))
        if n > 3 else _stub_pass(n)(ln, cue, n, breadth)
    ))
    monkeypatch.setattr(idle, "alert_if_warranted", lambda ln: {"alert": False})

    result = idle.idle_turn()
    assert result["paused"] is True
    assert "name resolution" in result["pause_reason"]
    assert result["iterations_run"] == 3, "only the three that really ran"
    assert result["committed"] == 3

    from mem20dreamz.lineage import Lineage as L

    reloaded = L.load("dream-idle-outage")
    assert reloaded.paused is True
    assert reloaded.iteration_count == 3
    assert len(reloaded.braid_cids) == 3
    assert "name resolution" in reloaded.pause_reason


def test_uncommitted_iteration_is_recorded_not_hidden(monkeypatch):
    monkeypatch.setattr(idle.engine, "new_dream", lambda *a, **k: Lineage(
        dream_id="dream-idle-nocommit", seed="s", kind="idle_idea", foundation="s", artifact="s"
    ))
    # nap_pass commits to braid itself, so the outcome is driven by what it
    # reports rather than by a separate commit mock.
    monkeypatch.setattr(idle.engine, "nap_pass", _stub_pass(1, braid=False))
    monkeypatch.setattr(idle, "alert_if_warranted", lambda ln: {"alert": False})

    result = idle.idle_turn()
    assert result["uncommitted"] == idle.IDLE_PASSES
    from mem20dreamz.lineage import Lineage as L

    reloaded = L.load("dream-idle-nocommit")
    assert len(reloaded.uncommitted) == idle.IDLE_PASSES
    assert reloaded.braid_cids == []


def test_inventory_reports_the_pass_depth():
    inv = idle.inventory()
    assert inv["passes_per_turn"] == idle.IDLE_PASSES
    assert inv["writers_per_pass"] == idle.IDLE_BREADTH
