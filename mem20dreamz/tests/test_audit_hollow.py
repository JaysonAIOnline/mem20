"""The hollow-iteration audit: find failed calls, mark them, and refuse to promote them.

The defect this guards: a provider outage used to produce an "iteration" with
zero critiques and zero inventions. The node was validly signed and sat in the
ledger looking like a dream. 39 such lineages exist from the DNS outage.
"""

from __future__ import annotations

import json

import pytest

from mem20dreamz import audit, promote
from mem20dreamz.lineage import Iteration, Lineage


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr("mem20dreamz.lineage.STORE", str(tmp_path / "dreams"))
    yield


def _iteration(n: int = 1, critiques: list[dict] | None = None, inventions: list[str] | None = None):
    return Iteration(
        n=n,
        artifact="draft",
        fidelity={"score": 0},
        omission={"score": 0, "summary": ""},
        forecast={},
        critiques=critiques if critiques is not None else [],
        inventions_added=inventions or [],
        dreamer_evolved=False,
        accepted=False,
    )


ERR = [{"kind": "errors", "role": "ux_architect", "text": "LLMError: name resolution"}]
REAL = [{"kind": "critique", "role": "ux_architect", "text": "the hero copy is weak"}]


def _save(lineage: Lineage) -> Lineage:
    """Persist and return, so a test can record-then-save in one call."""
    lineage.save()
    return lineage


def _with_iterations(dream_id: str, critiques: list[dict], **kw) -> Lineage:
    """Build a lineage, record the iteration, THEN persist it."""
    lineage = Lineage(
        dream_id=dream_id, seed="s", kind=kw.get("kind", "idle_idea"), foundation="s"
    )
    lineage.record(_iteration(critiques=critiques, inventions=kw.get("inventions")))
    return _save(lineage)


def test_a_failed_call_is_recognised_as_hollow():
    _with_iterations("dream-hollow", ERR)
    found = audit.find_hollow()
    assert [f["dream_id"] for f in found] == ["dream-hollow"]
    assert found[0]["hollow_iterations"][0]["reason"].startswith("LLMError")


def test_a_real_dream_is_not_hollow():
    _with_iterations("dream-real", REAL, inventions=["a thing"])
    assert audit.find_hollow() == []


def test_a_partial_run_is_not_hollow():
    """One error alongside real work is a bad run, not an empty one."""
    _with_iterations("dream-partial", ERR + REAL)
    assert audit.find_hollow() == []


def test_marking_persists_and_is_idempotent():
    _with_iterations("dream-mark", ERR)
    assert audit.quarantine(commit=False)["newly_marked"] == 1
    reloaded = Lineage.load("dream-mark")
    assert reloaded.hollow is not None, "the mark must survive a reload"
    assert reloaded.hollow["real_dream"] is False
    assert audit.quarantine(commit=False)["newly_marked"] == 0, "marking twice is not new work"


def test_hollow_mark_survives_the_serialiser(tmp_path):
    """Regression: as_dict is an explicit dict, so a new field is easy to forget."""
    lineage = _save(Lineage(dream_id="dream-ser", seed="s", kind="idle_idea", foundation="s"))
    lineage.hollow = {"why": "test", "real_dream": False}
    lineage.save()
    on_disk = json.loads((tmp_path / "dreams" / "dream-ser" / "lineage.json").read_text())
    assert on_disk["hollow"]["why"] == "test"
    assert Lineage.load("dream-ser").hollow is not None


def test_a_hollow_lineage_cannot_be_promoted(tmp_path):
    _with_iterations("dream-hp", ERR)
    audit.quarantine(commit=False)
    out = tmp_path / "pack"
    result = promote.promote("dream-hp", str(out))
    assert result["promoted"] is False
    assert "hollow" in result["reason"]
    assert not out.exists()


def test_a_hollow_lineage_with_a_valid_chain_is_still_refused(tmp_path, monkeypatch):
    """The signature proves the bytes; it does not prove a dream happened."""
    lineage = _save(Lineage(dream_id="dream-hv", seed="s", kind="idle_idea", foundation="s"))
    lineage.braid_cids = ["bra", "brb"]
    lineage.hollow = {"why": "provider outage", "real_dream": False}
    lineage.save()
    monkeypatch.setattr(promote.ledger, "verify_chain", lambda cids: {"healthy": True, "checked": 2})
    result = promote.promote("dream-hv", str(tmp_path / "pack"))
    assert result["promoted"] is False
    assert result["provenance"]["checked"] == 0, "it must not even reach chain verification"


def test_find_hollow_never_writes(tmp_path, monkeypatch):
    _with_iterations("dream-ro", ERR)
    before = (tmp_path / "dreams" / "dream-ro" / "lineage.json").read_text()
    audit.find_hollow()
    after = (tmp_path / "dreams" / "dream-ro" / "lineage.json").read_text()
    assert before == after, "the audit is a reader until you ask it to record"
    assert Lineage.load("dream-ro").hollow is None
