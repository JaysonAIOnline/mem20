"""Tests for the dream engine's invariants.

These pin the properties that make improvement real rather than asserted: the
never-condenses rule, the distinct-model rule, the veto, and the fact that
selection cannot adopt a regression.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, "/opt/mem20")

from mem20dreamz import engine, panel, verdicts
from mem20dreamz.lineage import (
    Iteration,
    Lineage,
)

# --- the never-condenses invariant -----------------------------------------


def test_condenses_catches_a_shrinking_revision():
    """The original defect: seed = out[:300] every pass."""
    shrunk, why = verdicts.condenses("x" * 5000, "y" * 500)
    assert shrunk is True
    assert "condensed" in why


def test_a_healthy_revision_is_not_condensation():
    shrunk, _ = verdicts.condenses("x" * 5000, "y" * 5200)
    assert shrunk is False


def test_trimming_within_allowance_is_allowed():
    # 0.6 of previous must pass; iterating should not forbid tidying up.
    shrunk, _ = verdicts.condenses("x" * 5000, "y" * 3100)
    assert shrunk is False


def test_small_artifacts_are_exempt_from_the_shrink_guard():
    # Below the floor, "shrinking" is meaningless and would false-positive.
    shrunk, _ = verdicts.condenses("x" * 100, "y" * 10)
    assert shrunk is False


# --- the distinct-model rule -----------------------------------------------


def test_duplicate_model_in_the_roster_raises(monkeypatch):
    """It previously deduplicated silently and deleted a whole role."""
    dup = panel.Panelist(
        role="ghost", provider="cohere", model=panel.PANEL[0].model, context=1000, focus="x"
    )
    monkeypatch.setattr(panel, "PANEL", panel.PANEL + (dup,))
    with pytest.raises(panel.PanelConfigError) as exc:
        panel.assert_roster_valid()
    assert "distinct-model rule violated" in str(exc.value)


def test_shipped_roster_has_no_duplicate_models():
    panel.assert_roster_valid()
    ids = [m.model for m in panel.PANEL]
    assert len(ids) == len(set(ids))


def test_every_shipped_panelist_is_verified_answering():
    """Every id in the roster was proven to answer on this host."""
    from verify_panel_reference import VERIFIED  # type: ignore

    for member in panel.PANEL:
        assert member.model in VERIFIED, f"{member.model} was never verified answering"


# --- the omission veto ------------------------------------------------------


def test_all_candidates_vetoed_returns_no_winner():
    scored = [
        {
            "writer": "a", "text": "x" * 5000, "eligible": True,
            "fidelity_score": 90.0, "omission_score": 5.0,
        }
    ]
    result = engine._select(scored, "incumbent" * 500, "seed")
    assert result["chosen"] is None
    assert "vetoed" in result["reason"]


def test_candidate_below_fidelity_floor_is_ineligible():

    # A condense check is pure, so exercise the eligibility rule directly.
    candidate = {
        "writer": "a", "text": "x" * 5000, "condensed": False,
        "fidelity_score": 40.0, "omission_score": 80.0,
    }
    candidate["eligible"] = (
        not candidate["condensed"] and candidate["fidelity_score"] >= verdicts.FIDELITY_FLOOR
    )
    assert candidate["eligible"] is False


# --- selection cannot adopt a regression -----------------------------------


def test_incumbent_that_wins_every_contest_is_kept(monkeypatch):
    monkeypatch.setattr(
        engine, "_pairwise", lambda *a, **k: {"winner": "incumbent", "reason": "", "judged_by": "x"}
    )
    scored = [
        {"writer": "a", "text": "x" * 5000, "eligible": True, "fidelity_score": 95.0, "omission_score": 80.0}
    ]
    result = engine._select(scored, "incumbent text", "seed")
    assert result["chosen"] is None
    assert "incumbent won" in result["reason"]


def test_candidate_that_wins_is_adopted(monkeypatch):
    monkeypatch.setattr(
        engine, "_pairwise", lambda *a, **k: {"winner": "candidate", "reason": "", "judged_by": "x"}
    )
    scored = [
        {"writer": "a", "text": "x" * 5000, "eligible": True, "fidelity_score": 95.0, "omission_score": 80.0}
    ]
    result = engine._select(scored, "incumbent text", "seed")
    assert result["chosen"] is not None
    assert result["chosen"]["writer"] == "a"


# --- lineage ---------------------------------------------------------------


def test_lineage_roundtrips(tmp_path, monkeypatch):
    monkeypatch.setattr("mem20dreamz.lineage.STORE", str(tmp_path))
    lineage = Lineage(dream_id="d1", seed="seed text", foundation="foundation")
    lineage.inventions.add("Flux Capacitor", "it levitates", "a 3D printed shell", 1)
    lineage.dreamer.add_technique("always show the price")
    lineage.record(
        Iteration(
            n=1, artifact="a" * 100, fidelity={"score": 90}, omission={"score": 50},
            forecast={}, critiques=[], inventions_added=[], dreamer_evolved=True, accepted=True,
        )
    )
    lineage.save()

    back = Lineage.load("d1")
    assert back is not None
    assert back.inventions.entries[0]["name"] == "Flux Capacitor"
    assert back.dreamer.techniques == ["always show the price"]
    assert back.score_history[0]["fidelity"] == 90


def test_digest_respects_its_budget():
    lineage = Lineage(dream_id="d2", seed="s")
    for n in range(30):
        lineage.changelog.append({"n": n, "change": "x" * 400, "accepted": True})
    digest = lineage.lineage_digest(2000)
    assert len(digest) <= 2100
    # Newest first: the most recent change must survive the cut.
    assert "iter 29" in digest


def test_artifact_is_never_truncated(tmp_path, monkeypatch):
    monkeypatch.setattr("mem20dreamz.lineage.STORE", str(tmp_path))
    long_artifact = "y" * 40_000
    lineage = Lineage(dream_id="d3", seed="s", artifact=long_artifact)
    assert lineage.current_artifact() == long_artifact


def test_score_history_records_acceptance():
    lineage = Lineage(dream_id="d4", seed="s")
    for n, accepted in ((1, True), (2, False)):
        lineage.record(
            Iteration(
                n=n, artifact="x", fidelity={"score": 90}, omission={"score": 50},
                forecast={}, critiques=[], inventions_added=[],
                dreamer_evolved=False, accepted=accepted,
            )
        )
    assert [h["accepted"] for h in lineage.score_history] == [True, False]


# --- verdict parsing -------------------------------------------------------


def test_parse_json_handles_fences_and_prose():
    assert verdicts.parse_json('```json\n{"score": 7}\n```')["score"] == 7
    assert verdicts.parse_json('Sure! {"score": 9} hope that helps')["score"] == 9


def test_parse_json_returns_empty_on_garbage():
    assert verdicts.parse_json("no json here") == {}


def test_score_is_clamped():
    assert verdicts.score_from({"score": 500}) == 100
    assert verdicts.score_from({"score": -5}) == 0
    assert verdicts.score_from({"score": "bad"}) == 0


def test_pairwise_parses_winner():
    assert verdicts.pairwise('{"winner": "B", "reason": "clearer"}')["winner"] == "B"


# --- the panel must be able to tell that it is funded -------------------------
#
# A regression that happened for real: `panel._key_for` read `os.environ` directly
# and only ever found COHERE_API_KEY / GROQ_API_KEY because `llm` was publishing
# the whole secrets file into the process environment at import. When that leak
# was closed, the panel quietly reported *no funded members* and `panel()` handed
# back an empty list. Nothing raised, nothing was logged, and a panel whose entire
# job is noticing it has lost a member would have gone on producing confident work
# from nobody.


def test_panel_finds_its_keys_without_anything_publishing_them():
    from mem20dreamz import panel as panel_mod

    keys = [panel_mod.KEY_ENV[m.provider] for m in panel_mod.PANEL if m.provider in panel_mod.KEY_ENV]
    assert keys, "the roster should name provider key variables"
    for provider in ("cohere", "groq"):
        if provider in panel_mod.KEY_ENV:
            assert panel_mod._key_for(provider), f"{provider} must resolve as funded"


def test_an_unfunded_provider_is_reported_as_unfunded(monkeypatch):
    """A funded check that says yes to everything is as useless as one that says no."""
    from mem20dreamz import panel as panel_mod

    monkeypatch.setattr(panel_mod.llm, "env_value", lambda name, default="": "")
    assert panel_mod._key_for("cohere") == ""
    assert panel_mod.panel() == []


def test_the_panel_never_publishes_secrets_into_the_environment():
    import subprocess
    import sys as _sys

    code = (
        "import os, sys;"
        "before=set(os.environ);"
        "sys.path.insert(0,'/opt/mem20');"
        "from mem20dreamz import panel;"
        "panel.panel();"
        "import json;print(json.dumps(sorted(set(os.environ)-before)))"
    )
    proc = subprocess.run(
        [_sys.executable, "-c", code], capture_output=True, text=True, timeout=60, check=False
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip().splitlines()[-1] == "[]", (
        "the panel must not publish keys into os.environ"
    )
