"""Dreams manager: review surface for the dream engine.

The engine's rules are not reimplemented here, so most of what these tests check is
that the manager reports the engine's answers faithfully rather than dressing them
up: a refusal stays a refusal with its reason, a paused run is not a failed run,
and the list never smuggles an artifact into a payload the UI polls.

The run-job tests never spawn anything. ``conftest`` makes ``subprocess.Popen``
raise, and these patch it with a fake process instead - the real spawn is verified
against the live service, not in a unit test.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mem20controlz import dreams


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    """Point the engine's store and the manager's roots at temp dirs.

    ``mem20dreamz.lineage.STORE`` is read at call time by ``Lineage.dir``, so
    patching the module attribute is enough to redirect every read and write.
    """
    monkeypatch.setattr("mem20dreamz.lineage.STORE", str(tmp_path / "dreams"))
    monkeypatch.setattr(dreams, "PROMOTIONS_ROOT", str(tmp_path / "promotions"))
    monkeypatch.setattr(dreams, "RUN_LOG_DIR", str(tmp_path / "run-logs"))
    monkeypatch.setattr("mem20dreamz.idle.LOCK", str(tmp_path / "active.lock"))
    monkeypatch.setattr("mem20dreamz.idle.STATE", str(tmp_path / "idle-state.json"))
    with dreams._jobs_lock:
        dreams._jobs.clear()
    yield


def _lineage(dream_id="dream-test-a", kind="active", artifact="a real thing", hollow=False):
    from mem20dreamz.lineage import Iteration, Lineage

    lineage = Lineage(
        dream_id=dream_id,
        seed="a brief worth dreaming about",
        kind=kind,
        foundation="make it trustworthy",
        artifact=artifact,
    )
    lineage.record(
        Iteration(
            n=1,
            artifact=artifact,
            fidelity={"score": 88.0},
            omission={"score": 61.0, "summary": "tightened the opening"},
            forecast={},
            critiques=[{"kind": "critique", "role": "ux_architect", "text": "the fold is unclear"}],
            inventions_added=["a changelog view"],
            dreamer_evolved=True,
            accepted=True,
        )
    )
    if hollow:
        lineage.hollow = {
            "marked_at": time.time(),
            "why": "iteration recorded provider errors instead of a panel result",
            "iterations": [1],
            "first_reason": "Temporary failure in name resolution",
            "real_dream": False,
        }
    lineage.save()
    return lineage


# --- the list stays light ----------------------------------------------------


def test_list_carries_no_artifact_text():
    """A polled list must not move megabytes, and must not leak the draft."""
    _lineage(artifact="SECRET-DRAFT-TEXT " * 200)
    result = dreams.dream_list()
    blob = repr(result)
    assert "SECRET-DRAFT-TEXT" not in blob, "the list must not carry artifact text"
    assert result["artifacts_included"] is False


def test_list_reports_the_artifact_length_without_the_artifact():
    _lineage(artifact="x" * 5000)
    row = dreams.dream_list()["dreams"][0]
    assert row["artifact_chars"] == 5000
    assert "artifact" not in row


def test_list_flags_hollow_dreams_instead_of_hiding_them():
    _lineage("dream-real")
    _lineage("dream-dead", hollow=True)
    result = dreams.dream_list()
    by_id = {r["dream_id"]: r for r in result["dreams"]}
    assert by_id["dream-real"]["hollow"] is False
    assert by_id["dream-dead"]["hollow"] is True
    assert "provider errors" in by_id["dream-dead"]["hollow_why"]


def test_hollow_can_be_filtered_out_and_the_filter_is_reported():
    _lineage("dream-real")
    _lineage("dream-dead", hollow=True)
    result = dreams.dream_list(include_hollow=False)
    assert [r["dream_id"] for r in result["dreams"]] == ["dream-real"]
    assert result["hidden_hollow"] == 1, "a filter that hides rows must say how many"


def test_only_unpromoted_filter():
    _lineage("dream-kept")
    _lineage("dream-fresh")
    kept = Path(dreams.PROMOTIONS_ROOT) / "dream-kept"
    kept.mkdir(parents=True)
    (kept / "dream-kept.md").write_text("pack")

    result = dreams.dream_list(only_unpromoted=True)
    assert [r["dream_id"] for r in result["dreams"]] == ["dream-fresh"]


def test_promotion_state_says_how_it_was_derived():
    """It is a directory listing, and it must not pretend to be a ledger query."""
    state = dreams.promotion_state("dream-x")
    assert state["promoted"] is False
    assert "directory" in state["derived_from"]
    assert "braid" in state["not_derived_from"]


def test_list_filters_by_kind():
    _lineage("dream-active", kind="active")
    _lineage("dream-idea", kind="idle_idea")
    result = dreams.dream_list(kind="idle_idea")
    assert [r["dream_id"] for r in result["dreams"]] == ["dream-idea"]


def test_list_limit_reports_the_untruncated_total():
    for index in range(5):
        _lineage(f"dream-{index}")
    result = dreams.dream_list(limit=2)
    assert result["returned"] == 2
    assert result["total"] == 5, "a truncated list must still say how many exist"


def test_list_sorts_a_mix_of_scored_unscored_and_odd_timestamps():
    """Found on the live store, not in a test: the sort compared float to str.

    Rows arrive with a float timestamp, with no timestamp at all, and — from
    lineages written by older code paths — with a timestamp that is not a number.
    Sorting on the raw value raised, and the whole list 500'd.
    """
    scored = _lineage("dream-scored")
    scored.score_history[-1]["at"] = 1_700_000_000.0
    scored.save()

    unscored = _lineage("dream-unscored")
    unscored.score_history.clear()
    unscored.save()

    odd = _lineage("dream-odd")
    odd.score_history[-1]["at"] = "not-a-number"
    odd.save()

    result = dreams.dream_list()
    ids = [row["dream_id"] for row in result["dreams"]]
    assert set(ids) == {"dream-scored", "dream-unscored", "dream-odd"}
    assert ids[0] == "dream-scored", "a scored dream sorts ahead of an unscored one"


def test_a_missing_timestamp_does_not_raise():
    _lineage("dream-a")
    _lineage("dream-b")
    result = dreams.dream_list()
    assert result["total"] == 2


# --- detail ------------------------------------------------------------------


def test_detail_includes_the_artifact_because_that_is_the_review():
    _lineage(artifact="the exact text a person is here to read")
    detail = dreams.dream_detail("dream-test-a")
    assert detail["artifact"] == "the exact text a person is here to read"
    assert detail["artifact_chars"] == len(detail["artifact"])
    assert detail["critique_count"] == 1


def test_detail_of_an_unknown_dream_is_a_refusal_with_a_reason():
    with pytest.raises(dreams.DreamError) as excinfo:
        dreams.dream_detail("dream-nope")
    assert "no such dream" in str(excinfo.value)


def test_detail_does_not_claim_provenance_it_has_not_checked():
    """``verified: None`` is the honest answer before anything has verified it."""
    _lineage()
    detail = dreams.dream_detail("dream-test-a")
    assert detail["provenance"]["verified"] is None
    assert "verify" in detail["provenance"]["verify_with"]


def test_chain_reports_uncommitted_iterations_rather_than_hiding_them():
    lineage = _lineage()
    lineage.uncommitted.append({"n": 2, "reason": "braid reports unavailable"})
    lineage.save()
    chain = dreams.dream_chain("dream-test-a")
    assert chain["braid_committed"] == 0
    assert chain["uncommitted"][0]["reason"] == "braid reports unavailable"


# --- verify ------------------------------------------------------------------


def test_verify_refuses_to_call_a_hollow_lineage_proven():
    """A valid signature proves the bytes, not that a dream happened."""
    _lineage("dream-dead", hollow=True)
    report = dreams.dream_verify("dream-dead")
    assert report["healthy"] is False
    assert report["checked"] == 0
    assert "not that a dream happened" in report["note"] or "not work" in report["note"]


# --- promote -----------------------------------------------------------------


def test_a_hollow_lineage_is_not_promoted_and_says_which_reason(monkeypatch):
    _lineage("dream-dead", hollow=True)
    result = dreams.dream_promote("dream-dead")
    assert result["promoted"] is False
    assert "hollow" in result["reason"]
    assert not Path(dreams.PROMOTIONS_ROOT).exists(), "a refusal must write nothing"


def test_a_damaged_chain_is_not_promoted_and_says_which_reason(monkeypatch):
    _lineage("dream-test-a")
    monkeypatch.setattr(
        dreams.promote_mod, "check_provenance", lambda ln: {"healthy": False, "broken": [{"cid": "brx"}]}
    )
    result = dreams.dream_promote("dream-test-a")
    assert result["promoted"] is False
    assert "does not verify" in result["reason"]


def test_promoting_an_unknown_dream_is_a_refusal_not_a_crash():
    with pytest.raises(dreams.DreamError):
        dreams.dream_promote("dream-nope")


def test_a_successful_promotion_writes_a_pack_and_says_what_it_wrote(monkeypatch):
    _lineage("dream-test-a")
    monkeypatch.setattr(dreams.promote_mod, "check_provenance", lambda ln: {"healthy": True, "checked": 0})
    monkeypatch.setattr(dreams.promote_mod, "commit_promotion", lambda ln, pk: {"committed": True, "cid": "brp"})
    result = dreams.dream_promote("dream-test-a")
    assert result["promoted"] is True
    assert result["files"] == ["dream-test-a.json", "dream-test-a.md"]
    assert Path(result["out_dir"]).is_dir()
    assert dreams.promotion_state("dream-test-a")["promoted"] is True


def test_an_existing_pack_is_refused_rather_than_overwritten(monkeypatch):
    _lineage("dream-test-a")
    monkeypatch.setattr(dreams.promote_mod, "check_provenance", lambda ln: {"healthy": True, "checked": 0})
    monkeypatch.setattr(dreams.promote_mod, "commit_promotion", lambda ln, pk: {"committed": True})
    dreams.dream_promote("dream-test-a")
    with pytest.raises(dreams.DreamError) as excinfo:
        dreams.dream_promote("dream-test-a")
    assert "force" in str(excinfo.value)


# --- new dream ---------------------------------------------------------------


def test_creating_a_dream_says_outright_that_it_cost_nothing(monkeypatch):
    monkeypatch.setattr(dreams, "MAX_RUN_ITERATIONS", 5)
    result = dreams.dream_new("a seed worth keeping", foundation="the premise")
    assert result["costs_tokens"] is False
    assert result["iterations"] == 0
    assert Path(result["state_path"]).exists()


def test_a_dream_needs_a_seed():
    with pytest.raises(dreams.DreamError) as excinfo:
        dreams.dream_new("   ")
    assert "seed" in str(excinfo.value)


def test_an_unknown_kind_is_refused_rather_than_stored():
    """A typo here would create a lineage no filter and no alert bar matches."""
    with pytest.raises(dreams.DreamError) as excinfo:
        dreams.dream_new("a seed", kind="idle_idee")
    assert "unknown kind" in str(excinfo.value)


# --- the run job -------------------------------------------------------------


class _FakeProc:
    """Stands in for a spawned run. Never a real process."""

    def __init__(self, pid=4242):
        self.pid = pid
        self._code = None
        self.killed = False

    def wait(self, timeout=None):
        if self._code is None:
            raise subprocess.TimeoutExpired("mem20-dream", timeout or 0)
        return self._code

    def kill(self):
        self.killed = True
        self._code = -9


@pytest.fixture
def no_threads(monkeypatch):
    """Keep the watcher thread out of unit tests; the wait is asserted directly."""
    started = []
    monkeypatch.setattr(
        dreams.threading, "Thread", lambda target=None, args=(), daemon=None: type(
            "T", (), {"start": lambda self: started.append((target, args))}
        )()
    )
    return started


def test_starting_a_run_spawns_the_engine_cli_not_an_in_process_call(monkeypatch, no_threads):
    """The CLI owns the lock and the exit codes; the manager must not reimplement them."""
    _lineage("dream-test-a")
    seen = {}

    def _popen(argv, **kwargs):
        seen["argv"] = argv
        seen["kwargs"] = kwargs
        return _FakeProc()

    monkeypatch.setattr(dreams.subprocess, "Popen", _popen)
    result = dreams.start_run("dream-test-a", iterations=2)

    assert "run" in seen["argv"] and "--dream-id" in seen["argv"]
    assert seen["argv"][seen["argv"].index("--dream-id") + 1] == "dream-test-a"
    assert seen["argv"][seen["argv"].index("--iterations") + 1] == "2"
    assert "shell" not in seen["kwargs"], "argv is fixed, so no shell is needed"
    assert result["status"] == "running"
    assert result["job_id"].startswith("run-")


def test_a_second_run_for_the_same_dream_is_refused_before_spawning(monkeypatch, no_threads):
    """The double-click case. One run per dream, refused rather than raced."""
    _lineage("dream-test-a")
    monkeypatch.setattr(dreams.subprocess, "Popen", lambda *a, **k: _FakeProc())
    dreams.start_run("dream-test-a")

    with pytest.raises(dreams.DreamError) as excinfo:
        dreams.start_run("dream-test-a")
    assert "already in flight" in str(excinfo.value)


def test_a_run_is_refused_while_another_holds_the_engine_lock(monkeypatch, no_threads):
    from mem20dreamz import idle

    _lineage("dream-test-a")
    idle.claim_active("dream-someone-else")
    monkeypatch.setattr(dreams.subprocess, "Popen", lambda *a, **k: _FakeProc())

    with pytest.raises(dreams.DreamError) as excinfo:
        dreams.start_run("dream-test-a")
    assert "dream-someone-else" in str(excinfo.value)


def test_iterations_are_bounded(monkeypatch, no_threads):
    _lineage("dream-test-a")
    monkeypatch.setattr(dreams.subprocess, "Popen", lambda *a, **k: _FakeProc())
    for bad in (0, -1, dreams.MAX_RUN_ITERATIONS + 1, "many"):
        with pytest.raises(dreams.DreamError):
            dreams.start_run("dream-test-a", iterations=bad)


def test_a_hollow_lineage_is_never_run(monkeypatch, no_threads):
    """Running a dead lineage would spend real money to reproduce the failure."""
    _lineage("dream-dead", hollow=True)
    monkeypatch.setattr(dreams.subprocess, "Popen", lambda *a, **k: _FakeProc())
    with pytest.raises(dreams.DreamError) as excinfo:
        dreams.start_run("dream-dead")
    assert "hollow" in str(excinfo.value)


def test_a_finished_dream_is_not_run_again(monkeypatch, no_threads):
    lineage = _lineage("dream-done")
    lineage.done = True
    lineage.save()
    monkeypatch.setattr(dreams.subprocess, "Popen", lambda *a, **k: _FakeProc())
    with pytest.raises(dreams.DreamError) as excinfo:
        dreams.start_run("dream-done")
    assert "already done" in str(excinfo.value)


def test_running_an_unknown_dream_is_a_refusal():
    with pytest.raises(dreams.DreamError):
        dreams.start_run("dream-nope")


# --- exit codes are three different facts ------------------------------------


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (0, "done"),
        (2, "paused"),
        (3, "refused"),
        (1, "failed"),
        (None, "unknown"),
    ],
)
def test_exit_codes_map_to_distinct_states(code, expected):
    state, note = dreams._interpret(code)
    assert state == expected
    assert note, "every state must come with a sentence a person can act on"


def test_a_paused_run_is_not_reported_as_a_failure():
    """Exit 2 keeps everything that landed; calling it a failure invites a false retry."""
    state, note = dreams._interpret(2)
    assert state == "paused"
    assert "kept" in note


def test_a_refused_run_says_another_run_holds_the_lock():
    state, note = dreams._interpret(3)
    assert state == "refused"
    assert "lock" in note


def test_a_run_that_overruns_its_ceiling_is_killed_and_called_failed(monkeypatch, no_threads):
    _lineage("dream-test-a")
    proc = _FakeProc()
    monkeypatch.setattr(dreams.subprocess, "Popen", lambda *a, **k: proc)
    job = dreams.start_run("dream-test-a")

    target, args = no_threads[0]
    target(*args)  # run the watcher inline with a 0s ceiling

    status = dreams.run_status(job["job_id"])
    assert proc.killed is True, "a run past its ceiling must actually be killed"
    assert status["status"] == "failed"
    assert status["timed_out"] is True


def test_status_of_an_unknown_job_is_a_refusal():
    with pytest.raises(dreams.DreamError):
        dreams.run_status("run-does-not-exist")


def test_run_records_admit_they_are_in_memory_only(monkeypatch, no_threads):
    _lineage("dream-test-a")
    monkeypatch.setattr(dreams.subprocess, "Popen", lambda *a, **k: _FakeProc())
    dreams.start_run("dream-test-a")
    listing = dreams.list_runs()
    assert listing["total"] == 1
    assert listing["running"] == 1
    assert listing["in_memory_only"] is True
    assert "restart" in listing["note"]


def test_the_log_tail_is_bounded(monkeypatch, no_threads):
    _lineage("dream-test-a")
    monkeypatch.setattr(dreams.subprocess, "Popen", lambda *a, **k: _FakeProc())
    job = dreams.start_run("dream-test-a")
    Path(job["log_path"]).write_text("\n".join(f"line {i}" for i in range(5000)))
    status = dreams.run_status(job["job_id"])
    assert status["log_lines"] == dreams.LOG_TAIL_LINES
    assert status["log"][-1] == "line 4999", "the newest line must be the one kept"


# --- the read-only hollow census ---------------------------------------------


def test_the_hollow_census_reads_and_says_so(monkeypatch):
    # `find_hollow` re-derives hollowness from the critiques rather than trusting
    # the stored flag, so the fixture has to be a genuine failed call: an
    # iteration carrying only provider errors and no critique at all.
    from mem20dreamz.lineage import Iteration, Lineage

    lineage = Lineage(dream_id="dream-failed-call", seed="s", kind="idle_idea", artifact="")
    lineage.iterations.append(
        Iteration(
            n=1,
            artifact="",
            fidelity={"score": 0.0},
            omission={"score": 0.0, "summary": ""},
            forecast={},
            critiques=[{"kind": "errors", "text": "Temporary failure in name resolution"}],
            inventions_added=[],
            dreamer_evolved=False,
            accepted=False,
        )
    )
    lineage.save()

    report = dreams.hollow_report()
    assert report["hollow_lineages"] >= 1
    assert report["hollow_iterations"] >= 1
    assert report["read_only"] is True
    assert "separate, explicit act" in report["note"]


# --- manifest ----------------------------------------------------------------


def test_manifest_states_what_promotion_writes_and_refuses():
    manifest = dreams.manifest()
    assert "braid" in manifest["promotion"]["writes"]
    assert any("hollow" in reason for reason in manifest["promotion"]["refuses_on"])
    assert any("braid" in reason for reason in manifest["promotion"]["refuses_on"])
    assert "directory" in manifest["honesty"]["promoted_is"]
    assert manifest["run"]["exit_codes"]["2"].startswith("paused")


def test_manifest_advertises_a_bounded_run():
    manifest = dreams.manifest()
    assert manifest["run"]["max_iterations"] >= 1
    assert manifest["run"]["timeout_s"] > 0
    assert "not free" in manifest["run"]["cost_note"]
