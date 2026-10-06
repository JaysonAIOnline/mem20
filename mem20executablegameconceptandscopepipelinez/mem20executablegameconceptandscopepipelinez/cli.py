"""Pipeline 1 CLI — independent entry point.

    python -m mem20executablegameconceptandscopepipelinez.cli analyse  <brief.json> --budget-days N
    python -m mem20executablegameconceptandscopepipelinez.cli gdd       <brief.json> --budget-days N -o out.md
    python -m mem20executablegameconceptandscopepipelinez.cli schema

This CLI depends only on the standard library and this package. It does not
import any other pipeline, and it runs with the rest of the fleet absent.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):  # direct-script execution
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from mem20executablegameconceptandscopepipelinez.concept import (  # noqa: E402
        ConceptError, analyse, render_gdd, build_brief, assess_scope,
        detect_contradictions,
    )
else:
    from .concept import (  # noqa: E402
        ConceptError, analyse, render_gdd, build_brief, assess_scope,
        detect_contradictions,
    )

SCHEMA = {
    "brief": {
        "title": "string (required)",
        "pitch": "string (required)",
        "vision": "string",
        "raw_idea": "string",
        "audience": "list[string]",
        "platforms": "list[string] — windows|linux|macos|console|android|ios|quest|vr",
        "core_loop": {
            "action": "string (required for a complete loop)",
            "feedback": "string",
            "reward": "string",
            "progression": "string",
            "duration_seconds": "number",
        },
        "features": [{
            "id": "string (unique)",
            "name": "string",
            "description": "string",
            "supports": "list[string] — action|feedback|reward|progression",
            "effort_days": "number",
            "core": "bool",
            "must_have": "bool",
        }],
        "risks": [{
            "id": "string",
            "description": "string",
            "severity": "low|medium|high|critical",
            "likelihood": "low|medium|high",
            "mitigation": "string (required when severity=critical)",
        }],
        "milestones": [{
            "id": "string",
            "name": "string",
            "exit_criteria": "list[string]",
            "depends_on": "list[milestone id]",
        }],
        "success_criteria": [{
            "id": "string",
            "statement": "string",
            "metric": "string",
            "threshold": "string",
            "kind": "measurable|timebound|player_visible",
        }],
    },
    "detections": {
        "pitch_loop_mismatch": "pitch promises actions the core loop never performs",
        "incomplete_core_loop": "core loop is missing one or more of action/feedback/reward/progression",
        "platform_scope_clash": "multiple platform families targeted without a must-have feature justifying them",
        "orphan_must_have": "must_have feature supports no core-loop part",
        "milestone_cycle": "milestone dependency cycle",
        "unmitigated_critical_risk": "critical risk with no mitigation",
        "committed_exceeds_budget": "must-have effort exceeds the budget",
        "fat_optional_feature": "single optional feature over 15% of budget with no core-loop support",
        "peripheral_dominates": "peripheral features (store/cosmetics/achievements) over 10% of budget",
        "plan_unrealistic": "total planned work over 1.5x budget",
    },
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="mem20executablegameconceptandscopepipelinez",
        description="Pipeline 1 — Game Concept, GDD & Scope")
    sub = ap.add_subparsers(dest="cmd", required=True)

    for name in ("analyse", "gdd"):
        p = sub.add_parser(name)
        p.add_argument("brief", help="path to brief JSON")
        p.add_argument("--budget-days", type=float, required=True)
        if name == "gdd":
            p.add_argument("-o", "--out", help="write markdown here instead of stdout")

    sub.add_parser("schema")

    a = ap.parse_args(argv)

    if a.cmd == "schema":
        print(json.dumps(SCHEMA, indent=2))
        return 0

    try:
        raw = json.loads(Path(a.brief).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: cannot read brief: {exc}", file=sys.stderr)
        return 2

    try:
        if a.cmd == "analyse":
            report = analyse(raw, a.budget_days)
            print(json.dumps({k: v for k, v in report.items() if k != "gdd"},
                             indent=2))
            # Exit 1 on a blocked concept so CI can gate on it.
            return 1 if report["verdict"] == "BLOCKED" else 0
        brief = build_brief(raw)
        cons = detect_contradictions(brief)
        scope = assess_scope(brief, a.budget_days)
        gdd = render_gdd(brief, a.budget_days, cons, scope)
        if a.out:
            Path(a.out).write_text(gdd)
            print(f"wrote {a.out}", file=sys.stderr)
        else:
            print(gdd)
        critical = [c for c in cons if c.severity == "critical"] + \
                   [s for s in scope if s.severity == "critical"]
        return 1 if critical else 0
    except ConceptError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
