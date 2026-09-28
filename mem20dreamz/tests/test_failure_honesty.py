"""A failed panel must not manufacture an iteration that never happened.

This is a real defect, found in production: an idle timer ran through a DNS
outage and committed ~24 hollow iterations to braid. Each one had zero critiques
and zero inventions, and the lineage looked like a dream that had happened.

The engine records errors honestly in `critiques`, but recording the error is not
the same as being honest about the run: with zero panelist answers there was no
dream, and the correct behaviour is to abort so the caller pauses.
"""

from __future__ import annotations

import os

import pytest

from mem20dreamz import engine
from mem20dreamz import idle
from mem20dreamz import panel as panel_mod
from mem20dreamz.lineage import Lineage


class _Member:
    def __init__(self, role="ux_architect", model="test/model", context=8000):
        self.role = role
        self.model = model
        self.context = context


@pytest.fixture
def _panel(monkeypatch):
    monkeypatch.setattr(panel_mod, "panel", lambda: [_Member(role=r) for r in ("ux_architect", "product")])
    monkeypatch.setattr(panel_mod, "CRITIC_ROLES", {"ux_architect", "product"})


def _fail(*args, **kwargs):
    return "", "LLMError: [Errno -3] Temporary failure in name resolution"


def test_total_provider_failure_aborts_instead_of_committing_nothing(_panel, monkeypatch):
    monkeypatch.setattr(engine, "ask", _fail)
    lineage = Lineage(dream_id="dream-dns", seed="s", foundation="f", artifact="a")
    with pytest.raises(Exception) as excinfo:
        engine.run_iteration(lineage, 1)
    assert "no panelist answered" in str(excinfo.value), "a total failure must abort the iteration"
    assert "name resolution" in str(excinfo.value), "the underlying cause must survive to the caller"


def test_one_surviving_critic_is_enough_to_continue(_panel, monkeypatch):
    """Partial success is still a dream; only a total wipeout is not."""
    calls = {"n": 0}

    def ask(member, prompt, cont=""):
        calls["n"] += 1
        if member.role == "ux_architect":
            return "", "LLMError: upstream refused"
        return '{"missing": ["nothing"]}', None

    monkeypatch.setattr(engine, "ask", ask)
    monkeypatch.setattr(engine.v, "aggregate_omission", lambda x: {"score": 50, "summary": "", "missing": []})
    monkeypatch.setattr(engine, "_evolve_dreamer", lambda *a, **k: None)
    lineage = Lineage(dream_id="dream-partial", seed="s", foundation="f", artifact="a")
    iteration = engine.run_iteration(lineage, 1)
    assert iteration.n == 1
    assert any(c.get("kind") == "critique" for c in iteration.critiques)


def test_no_panel_members_is_still_its_own_error(monkeypatch):
    monkeypatch.setattr(panel_mod, "panel", list)
    monkeypatch.setattr(panel_mod, "CRITIC_ROLES", {"ux_architect"})
    lineage = Lineage(dream_id="dream-empty", seed="s", foundation="f", artifact="a")
    with pytest.raises(Exception) as excinfo:
        engine.run_iteration(lineage, 1)
    assert "no funded panel members" in str(excinfo.value)


def test_cli_pauses_rather_than_recording_a_failed_iteration(tmp_path, monkeypatch):
    """The user-visible consequence: a pause, and nothing written."""
    from mem20dreamz import __main__ as cli

    monkeypatch.setattr("mem20dreamz.lineage.STORE", str(tmp_path / "dreams"))
    # The run lock must be redirected too. `run` claims it before doing anything,
    # so without this the test reads - and briefly writes - the real lock beside
    # the production store, and its result depends on whether the twenty-minute
    # idle timer happens to be mid-turn.
    monkeypatch.setattr(idle, "LOCK", str(tmp_path / "active.lock"))
    monkeypatch.setattr(idle, "STATE", str(tmp_path / "idle-state.json"))
    lineage = Lineage(dream_id="dream-pause", seed="s", foundation="f", artifact="a")
    lineage.save()

    def boom(*args, **kwargs):
        raise engine.LLMError("no panelist answered; Temporary failure in name resolution")

    monkeypatch.setattr(engine, "run_iteration", boom)
    code = cli.main(["run", "--dream-id", "dream-pause", "--iterations", "1"])
    assert code == 2, "a provider outage must exit 2 (paused), not 0 (success)"

    from mem20dreamz.lineage import Lineage as L

    reloaded = L.load("dream-pause")
    assert reloaded.paused is True
    assert reloaded.iteration_count == 0, "no iteration may be recorded for a failed call"
    assert "name resolution" in reloaded.pause_reason
    assert reloaded.braid_cids == [], "a failed run must not write to braid"
    assert not os.path.exists(idle.LOCK), "a paused run must still release the lock"
