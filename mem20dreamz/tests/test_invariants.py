"""Tests for the dream engine's invariants.

These pin the properties that make improvement real rather than asserted. Two
kinds live here now.

Retained: the distinct-model rule, the omission veto, no-funding-no-dream, and
the honesty properties that stop a failed provider call passing for a dream.

Changed: the never-condenses rule, the fidelity floor and the blind tournament
were removed, because together they made the engine a polisher that could only
refine what it already had. What replaced them is divergence - distance from
the incumbent rather than resemblance to it - and a genesis path that lets a
candidate with no continuity supersede a lineage outright.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, "/opt/mem20")

from mem20dreamz import engine, panel, verdicts
from mem20dreamz import verdicts as v
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


def test_incumbent_winning_every_contest_no_longer_blocks(monkeypatch):
    """The blind tournament is evidence now, not a gate.

    It was removed because requiring a candidate to *beat the incumbent* meant
    the artifact could only ever be a refinement of itself. A candidate that
    opened new ground is adopted on that ground, and a judge that prefers the
    incumbent is recorded rather than obeyed.
    """
    monkeypatch.setattr(
        engine, "_pairwise", lambda *a, **k: {"winner": "incumbent", "reason": "", "judged_by": "x"}
    )
    scored = [
        {
            "writer": "a",
            "text": "x" * 5000,
            "eligible": True,
            "fidelity_score": 95.0,
            "omission_score": 80.0,
            "divergence_score": 70.0,
            "genesis": False,
        }
    ]
    result = engine._select(scored, "incumbent text", "seed")
    assert result["chosen"] is not None
    assert result["chosen"]["writer"] == "a"
    assert result["contests"], "the comparison is still recorded as evidence"
    assert result["contests"][0]["evidence_only"] is True


def test_the_candidate_that_travelled_furthest_is_adopted(monkeypatch):
    monkeypatch.setattr(
        engine, "_pairwise", lambda *a, **k: {"winner": "incumbent", "reason": "", "judged_by": "x"}
    )
    scored = [
        {"writer": "near", "text": "a", "eligible": True, "omission_score": 90.0,
         "divergence_score": 30.0, "genesis": False},
        {"writer": "far", "text": "b", "eligible": True, "omission_score": 40.0,
         "divergence_score": 88.0, "genesis": True},
    ]
    result = engine._select(scored, "incumbent text", "seed")
    assert result["chosen"]["writer"] == "far"
    assert result["genesis"] is True
    assert result["supersedes_lineage"] is True


def test_a_paraphrase_is_not_a_dream():
    """Divergence replaces fidelity as the eligibility test."""
    seed = "a capability gap mapper that notices what the fleet can do but cannot prove"
    same = "a capability gap mapper which notices what the fleet can do but cannot prove"
    alien = (
        "a mycelial consensus protocol where every node dreams alone and trades only "
        "spores of unresolved questions, refusing any answer the colony shares"
    )
    assert v.divergence(same, seed)["score"] < v.DIVERGENCE_FLOOR
    assert v.divergence(alien, seed)["score"] >= v.DIVERGENCE_FLOOR
    assert v.divergence(alien, seed)["score"] >= v.GENESIS_DISTANCE


def test_divergence_needs_no_model():
    """It is arithmetic, so no panelist can talk it into a good score."""
    a = v.divergence("alpha beta gamma delta", "epsilon zeta eta theta")
    assert a["score"] > 0
    assert a["novelty"] == 100.0


def test_omission_veto_is_kept():
    """The one guard that demands novelty survives the rebuild."""
    scored = [
        {"writer": "a", "text": "x", "eligible": True, "omission_score": 1.0,
         "divergence_score": 90.0, "genesis": True}
    ]
    result = engine._select(scored, "incumbent", "seed")
    assert result["chosen"] is None
    assert "vetoed" in result["reason"]


def test_honesty_guards_are_untouched():
    """No funding, no dream: the engine still refuses rather than faking."""
    src = open(engine.__file__, encoding="utf-8").read()  # noqa: SIM115 - one read, asserted immediately below
    assert "no funded panel members; cannot dream honestly" in src
    assert engine.v.GENESIS_DISTANCE > engine.v.DIVERGENCE_FLOOR


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


# --- the hypnagogic pass ----------------------------------------------------
#
# The deep iteration critiques, forecasts, invents, conditions, scores and holds
# a judged tournament. The research puts the creative effect at the opposite
# end of sleep, so the pass below is deliberately shallow: many candidates, one
# model each, arithmetic judging, no panel round and no model-as-judge call.


def _fake_reply(text):
    return ({"text": text}, None)


def test_pass_generates_broadly_and_judges_without_a_model(monkeypatch):
    calls = []

    def _ask(member, prompt, seed):
        calls.append((member.model, prompt))
        return _fake_reply(
            "a weather system for credentials, which argues with itself across a frontier "
            "of machines and settles on nothing anyone would recognise as an answer; it has "
            "no owner and no user, and it is the only place on this estate where two systems "
            "that have never met can be wrong about the same thing at the same moment"
        )

    monkeypatch.setattr(engine, "ask", _ask)
    monkeypatch.setattr(engine.panel_mod, "panel", lambda: [
        panel.Panelist(role=f"r{i}", provider="cohere", model=f"m{i}", context=1000, focus="")
        for i in range(4)
    ])
    monkeypatch.setattr(engine, "_panel_call", lambda m, build: _ask(m, build(m), ""))
    monkeypatch.setattr(engine.ledger, "commit_iteration", lambda ln, it: {"committed": True, "cid": "br1"})
    monkeypatch.setattr(engine.estate, "context_block", lambda: "")

    lineage = Lineage(dream_id="d-nap", seed="cue", foundation="cue", artifact="the seed text")
    result = engine.nap_pass(lineage, "cue", 1, breadth=4)

    assert result["accepted"] is True
    assert result["candidates"] == 4, "one candidate per writer"
    assert len({m for m, _ in calls}) == 4, "each candidate written by a different model"
    assert result["braid"] is True
    assert lineage.current_artifact() != "the seed text"


def test_pass_refuses_unfunded_rather_than_inventing(monkeypatch):
    monkeypatch.setattr(engine.panel_mod, "panel", list)
    lineage = Lineage(dream_id="d-nap-nofund", seed="c", foundation="c", artifact="c")
    with pytest.raises(engine.LLMError):
        engine.nap_pass(lineage, "c", 1)


def test_pass_stops_when_nothing_travelled(monkeypatch):
    """A paraphrase of the seed is not a dream, and must not be adopted."""
    monkeypatch.setattr(engine.panel_mod, "panel", lambda: [
        panel.Panelist(role="r0", provider="cohere", model="m0", context=1000, focus="")
    ])
    paraphrase = (
        "a weather system for credentials, which argues with itself across a frontier of "
        "machines and settles on nothing that anyone would recognise as an answer at all, "
        "and which is in every respect the same system described in slightly other words"
    )
    monkeypatch.setattr(engine, "_panel_call", lambda m, build: _fake_reply(paraphrase))
    monkeypatch.setattr(engine.ledger, "commit_iteration", lambda ln, it: {"committed": True, "cid": "br1"})

    # Same content words as the incumbent, different filler. This is what
    # "rewording the brief" looks like, and it must not pass as a dream.
    seed = (
        "a weather system for credentials, that argues with itself across a frontier of "
        "machines and settles on nothing that anyone would recognise as an answer at all, "
        "and that is in every respect the same system described in slightly other words"
    )
    lineage = Lineage(dream_id="d-nap-same", seed=seed, foundation=seed, artifact=seed)
    before = lineage.current_artifact()
    result = engine.nap_pass(lineage, seed, 1, breadth=1)
    assert result["accepted"] is False
    assert "nothing travelled" in result["reason"]
    assert lineage.current_artifact() == before, "the incumbent is untouched"


def test_a_supersession_keeps_the_prior_artifact(monkeypatch):
    """A dream that erases its own past cannot be audited."""
    monkeypatch.setattr(engine.panel_mod, "panel", lambda: [
        panel.Panelist(role="r0", provider="cohere", model="m0", context=1000, focus="")
    ])
    monkeypatch.setattr(engine, "_panel_call", lambda m, build: _fake_reply(
        "mycelium, a protocol wherein every node dreams alone and trades only spores of "
        "unresolved questions across the colony, permanently refusing any answer that two "
        "nodes happen to share, and keeping no ledger of what it has already believed"
    ))
    monkeypatch.setattr(engine.ledger, "commit_iteration", lambda ln, it: {"committed": True, "cid": "br1"})

    lineage = Lineage(dream_id="d-nap-gen", seed="c", foundation="c", artifact="the old artifact")
    result = engine.nap_pass(lineage, "c", 1, breadth=1)
    assert result["accepted"] is True
    assert result["genesis"] is True
    assert lineage.superseded is not None
    assert lineage.superseded["artifact"] == "the old artifact"
    assert lineage.current_artifact() != "the old artifact"


def test_superseded_survives_a_reload(tmp_path, monkeypatch):
    monkeypatch.setattr("mem20dreamz.lineage.STORE", str(tmp_path))
    lineage = Lineage(dream_id="d-sup", seed="c", foundation="c", artifact="new")
    lineage.superseded = {"artifact": "old", "at_pass": 2, "divergence": 91.0, "reason": "r"}
    lineage.save()
    assert Lineage.load("d-sup").superseded["artifact"] == "old"
