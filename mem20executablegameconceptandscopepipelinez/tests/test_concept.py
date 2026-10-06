"""Tests for Pipeline 1 — Game Concept, GDD & Scope.

Each test maps to a clause in the pipeline 1 spec:
    structured concept brief / core loop / audience / platform targets /
    feature list / risks / milestones / controlled GDD, plus detection of
    contradictions, uncontrolled scope, missing success criteria, and features
    that do not support the core experience.

Run:
    /root/.venv/bin/python -m pytest /opt/mem20/mem20executablegameconceptandscopepipelinez/tests -q
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mem20executablegameconceptandscopepipelinez.concept import (  # noqa: E402
    ConceptError, analyse, assess_scope, build_brief, core_loop_support,
    detect_contradictions, missing_success_criteria, render_gdd,
)

GOOD = {
    "title": "Iron Ledger",
    "pitch": "A duel where two armored duelists trade attacks in timed rounds.",
    "audience": ["fighting-game players", "competitive players"],
    "platforms": ["Windows", "Linux"],
    "core_loop": {
        "action": "attack and block",
        "feedback": "hit sparks and screen shake",
        "reward": "round win and meter gain",
        "progression": "championship ladder",
        "duration_seconds": 90,
    },
    "features": [
        {"id": "F001", "name": "Round combat", "supports": ["action"],
         "effort_days": 30, "core": True, "must_have": True},
        {"id": "F002", "name": "Round results screen", "supports": ["feedback"],
         "effort_days": 6, "must_have": True},
        {"id": "F003", "name": "Meter and super", "supports": ["reward"],
         "effort_days": 10, "must_have": True},
        {"id": "F004", "name": "Championship ladder", "supports": ["progression"],
         "effort_days": 8, "must_have": True},
    ],
    "risks": [
        {"id": "R001", "description": "Animation feels floaty",
         "severity": "critical", "likelihood": "medium",
         "mitigation": "Frame data locked before art pass"},
    ],
    "milestones": [
        {"id": "M001", "name": "Combat prototype",
         "exit_criteria": ["One character can attack and block"]},
        {"id": "M002", "name": "Full round", "depends_on": ["M001"],
         "exit_criteria": ["Round completes with a winner"]},
    ],
    "success_criteria": [
        {"id": "S001", "statement": "A round resolves without a soft lock",
         "metric": "soft_locks_per_100_rounds", "threshold": "0",
         "kind": "measurable"},
        {"id": "S002", "statement": "A new player reaches their first win",
         "metric": "first_win_minutes", "threshold": "<= 5",
         "kind": "timebound"},
        {"id": "S003", "statement": "Players can read a move before it lands",
         "metric": "survey", "threshold": ">= 4/5",
         "kind": "player_visible"},
    ],
}


# ── structured brief ────────────────────────────────────────────────────────

def test_brief_builds_from_raw_mapping():
    b = build_brief(GOOD)
    assert b.title == "Iron Ledger"
    assert b.core_loop.is_complete()
    assert len(b.features) == 4
    assert b.platforms == ["windows", "linux"]
    assert b.milestones[1].depends_on == ["M001"]


def test_brief_requires_title_and_pitch():
    with pytest.raises(ConceptError):
        build_brief({"pitch": "x"})
    with pytest.raises(ConceptError):
        build_brief({"title": "x"})


def test_brief_rejects_duplicate_feature_ids():
    bad = json.loads(json.dumps(GOOD))
    bad["features"][1]["id"] = "F001"
    with pytest.raises(ConceptError, match="duplicate feature id"):
        build_brief(bad)


def test_brief_rejects_unknown_milestone_dependency():
    bad = json.loads(json.dumps(GOOD))
    bad["milestones"][0]["depends_on"] = ["M999"]
    with pytest.raises(ConceptError, match="not a milestone"):
        build_brief(bad)


def test_brief_rejects_bad_risk_severity():
    bad = json.loads(json.dumps(GOOD))
    bad["risks"][0]["severity"] = "spicy"
    with pytest.raises(ConceptError, match="bad severity"):
        build_brief(bad)


# ── contradiction detection ─────────────────────────────────────────────────

def test_detects_pitch_that_core_loop_never_delivers():
    bad = json.loads(json.dumps(GOOD))
    bad["pitch"] = "Players fight with kombat finishers and block attacks."
    bad["core_loop"] = {"action": "walk around", "feedback": "dust",
                        "reward": "nothing", "progression": "nothing"}
    codes = {c.code for c in detect_contradictions(build_brief(bad))}
    assert "pitch_loop_mismatch" in codes


def test_detects_incomplete_core_loop_as_critical():
    bad = json.loads(json.dumps(GOOD))
    bad["core_loop"] = {"action": "attack", "feedback": "", "reward": "",
                        "progression": ""}
    found = [c for c in detect_contradictions(build_brief(bad))
             if c.code == "incomplete_core_loop"]
    assert found and found[0].severity == "critical"


def test_detects_orphan_must_have_feature():
    bad = json.loads(json.dumps(GOOD))
    bad["features"].append({"id": "F005", "name": "Leaderboard",
                            "supports": [], "must_have": True, "effort_days": 3})
    codes = {c.code for c in detect_contradictions(build_brief(bad))}
    assert "orphan_must_have" in codes


def test_detects_critical_risk_without_mitigation():
    bad = json.loads(json.dumps(GOOD))
    bad["risks"][0]["mitigation"] = ""
    codes = {c.code for c in detect_contradictions(build_brief(bad))}
    assert "unmitigated_critical_risk" in codes


def test_detects_milestone_dependency_cycle():
    bad = json.loads(json.dumps(GOOD))
    bad["milestones"][0]["depends_on"] = ["M002"]
    codes = {c.code for c in detect_contradictions(build_brief(bad))}
    assert "milestone_cycle" in codes


def test_detects_vr_and_pc_without_vr_justification():
    bad = json.loads(json.dumps(GOOD))
    bad["platforms"] = ["Windows", "Quest 3"]
    codes = {c.code for c in detect_contradictions(build_brief(bad))}
    assert "platform_scope_clash" in codes


def test_healthy_brief_has_no_critical_contradictions():
    critical = [c for c in detect_contradictions(build_brief(GOOD))
                if c.severity == "critical"]
    assert critical == []


# ── uncontrolled scope ──────────────────────────────────────────────────────

def test_flags_committed_work_over_budget_as_critical():
    findings = assess_scope(build_brief(GOOD), budget_days=10)
    hit = [f for f in findings if f.code == "committed_exceeds_budget"]
    assert hit and hit[0].severity == "critical"
    assert hit[0].impact_days == pytest.approx(44.0)


def test_flags_fat_optional_feature():
    bad = json.loads(json.dumps(GOOD))
    bad["features"].append({"id": "F005", "name": "Cinematic campaign",
                            "effort_days": 20})
    findings = assess_scope(build_brief(bad), budget_days=60)
    assert any(f.code == "fat_optional_feature" for f in findings)


def test_flags_peripheral_features_dominating_budget():
    bad = json.loads(json.dumps(GOOD))
    bad["features"].append({"id": "F006", "name": "Cosmetic store",
                            "effort_days": 25})
    findings = assess_scope(build_brief(bad), budget_days=60)
    assert any(f.code == "peripheral_dominates" for f in findings)


def test_flags_unrealistic_total_plan():
    findings = assess_scope(build_brief(GOOD), budget_days=20)
    assert any(f.code == "plan_unrealistic" for f in findings)


def test_scope_rejects_nonpositive_budget():
    with pytest.raises(ConceptError):
        assess_scope(build_brief(GOOD), budget_days=0)


def test_realistic_budget_reports_nothing():
    findings = assess_scope(build_brief(GOOD), budget_days=200)
    assert findings == []


# ── missing success criteria ────────────────────────────────────────────────

def test_missing_criteria_names_every_kind_when_absent():
    bad = json.loads(json.dumps(GOOD))
    bad["success_criteria"] = []
    assert set(missing_success_criteria(build_brief(bad))) == \
        {"measurable", "timebound", "player_visible"}


def test_measurable_criterion_without_metric_counts_as_missing():
    bad = json.loads(json.dumps(GOOD))
    bad["success_criteria"] = [
        {"id": "S001", "statement": "It feels good", "kind": "measurable"},
        {"id": "S002", "statement": "Fast onboarding", "kind": "timebound"},
        {"id": "S003", "statement": "Readable moves", "kind": "player_visible"},
    ]
    assert "measurable" in missing_success_criteria(build_brief(bad))


def test_complete_brief_is_missing_nothing():
    assert missing_success_criteria(build_brief(GOOD)) == []


# ── features that do not support the core experience ────────────────────────

def test_finds_features_carrying_no_core_loop_part():
    bad = json.loads(json.dumps(GOOD))
    bad["features"].append({"id": "F005", "name": "Ink filter shop",
                            "effort_days": 2})
    support = core_loop_support(build_brief(bad))
    assert support["features_not_supporting_core"] == ["F005"]


def test_support_ratio_and_coverage_are_computed():
    support = core_loop_support(build_brief(GOOD))
    assert support["support_ratio"] == 1.0
    assert support["uncovered_core_parts"] == []
    assert support["coverage_by_core_part"]["action"] == ["F001"]


def test_uncovered_core_part_is_reported():
    bad = json.loads(json.dumps(GOOD))
    bad["features"] = [f for f in bad["features"] if f["id"] != "F004"]
    support = core_loop_support(build_brief(bad))
    assert "progression" in support["uncovered_core_parts"]


# ── controlled GDD ──────────────────────────────────────────────────────────

def test_gdd_contains_every_required_section():
    gdd = render_gdd(build_brief(GOOD), 200)
    for heading in ("## Pitch", "## Audience", "## Platforms", "## Core Loop",
                    "## Success Criteria", "## Feature List", "## Risks",
                    "## Milestones", "## Control Findings", "## Sign-off"):
        assert heading in gdd, heading


def test_gdd_lists_every_feature_in_a_table():
    gdd = render_gdd(build_brief(GOOD), 200)
    for f in ("F001", "F002", "F003", "F004"):
        assert f"| {f} |" in gdd


def test_gdd_reports_ready_when_no_critical_findings():
    gdd = render_gdd(build_brief(GOOD), 200)
    assert "READY FOR REVIEW" in gdd
    assert "BLOCKED" not in gdd


def test_gdd_blocks_on_critical_contradiction():
    bad = json.loads(json.dumps(GOOD))
    bad["core_loop"] = {"action": "attack", "feedback": "", "reward": "",
                        "progression": ""}
    brief = build_brief(bad)
    cons = detect_contradictions(brief)
    gdd = render_gdd(brief, 200, cons, [])
    assert "BLOCKED" in gdd
    assert "incomplete_core_loop" in gdd


def test_gdd_blocks_on_critical_scope_finding():
    cons = []
    scope = assess_scope(build_brief(GOOD), budget_days=5)
    assert render_gdd(build_brief(GOOD), 5, cons, scope).count("BLOCKED") >= 1


# ── whole-pipeline call ─────────────────────────────────────────────────────

def test_analyse_returns_serialisable_report():
    report = analyse(GOOD, budget_days=200)
    json.dumps(report)  # must not raise
    assert report["verdict"] == "READY_FOR_REVIEW"
    assert report["missing_success_criteria"] == []
    assert report["gdd"].startswith("# Iron Ledger")


def test_analyse_blocks_a_broken_concept():
    bad = json.loads(json.dumps(GOOD))
    bad["core_loop"] = {"action": "", "feedback": "", "reward": "",
                        "progression": ""}
    report = analyse(bad, budget_days=200)
    assert report["verdict"] == "BLOCKED"
    assert report["critical_count"] >= 1


# ── independence ────────────────────────────────────────────────────────────

def test_module_imports_only_standard_library():
    """Pipeline 1 must stand alone: no sibling pipeline on the import path."""
    src = (Path(__file__).resolve().parent.parent
           / "mem20executablegameconceptandscopepipelinez" / "concept.py")
    text = src.read_text()
    for line in text.splitlines():
        if line.startswith(("import ", "from ")):
            assert "mem20" not in line or "concept" in line, line


def test_fat_optional_message_reports_a_ratio_not_a_raw_day_count():
    """Regression: the threshold message used to print budget*0.15 formatted
    as a percentage, producing nonsense like '>1350% of budget'."""
    bad = json.loads(json.dumps(GOOD))
    bad["features"].append({"id": "F005", "name": "Cinematic campaign",
                            "effort_days": 20})
    findings = assess_scope(build_brief(bad), budget_days=60)
    hit = next(f for f in findings if f.code == "fat_optional_feature")
    assert "1350%" not in hit.detail          # the old nonsense output
    assert "15% of the 60 day budget" in hit.detail
    assert hit.impact_days == 20.0


def test_optional_feature_under_threshold_is_not_flagged():
    bad = json.loads(json.dumps(GOOD))
    bad["features"].append({"id": "F005", "name": "Small extra",
                            "effort_days": 5})          # 5 < 200*0.15 = 30
    findings = assess_scope(build_brief(bad), budget_days=200)
    assert not any(f.code == "fat_optional_feature" for f in findings)
