"""Pipeline 1 — Game Concept, GDD & Scope.

Real domain logic for turning a raw game idea into a controlled, reviewable
concept brief and Game Design Document.

Spec authority: /home/jayson/Desktop/6/20_Essential_Game_Maker_Pipelines.md
pipeline 1 — "Game Concept, GDD & Scope Pipeline":

    Turns a raw game idea into a structured concept brief, core loop, audience
    definition, platform targets, feature list, risks, milestones, and a
    controlled Game Design Document. It should detect contradictions,
    uncontrolled scope, missing success criteria, and features that do not
    support the core experience.

This module owns that behaviour. It depends only on the standard library, so
it runs standalone with the other nineteen pipelines absent from the path.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Iterable

__all__ = [
    "ConceptBrief", "CoreLoop", "Feature", "Risk", "Milestone",
    "Contradiction", "ScopeFinding", "ConceptError",
    "build_brief", "detect_contradictions", "assess_scope",
    "core_loop_support", "render_gdd", "analyse",
]


class ConceptError(ValueError):
    """Raised when a concept brief cannot be parsed or is structurally invalid."""


# ── vocabulary ──────────────────────────────────────────────────────────────

# Interaction verbs that mark a feature as actually touching the core loop.
CORE_VERBS = {
    "fight", "attack", "block", "jump", "move", "select", "choose", "score",
    "win", "lose", "round", "match", "play", "aim", "shoot", "dodge", "cast",
}

# Words that mark a feature as surface-area rather than core experience.
PERIPHERAL_MARKERS = {
    "store", "shop", "cosmetic", "skin", "microtransaction", "monetization",
    "monetisation", "lootbox", "battlepass", "battle-pass", "ads",
    "leaderboard", "analytics", "telemetry", "achievement", "achievements",
    "tutorial", "settings", "credit", "credits",
}

SUCCESS_CRITERIA_TYPES = {"measurable", "timebound", "player_visible"}

_PLATFORM_FAMILIES = {
    "pc": ("windows", "linux", "mac", "macos", "steam"),
    "console": ("xbox", "playstation", "ps5", "ps4", "switch", "nintendo"),
    "mobile": ("android", "ios", "mobile"),
    "vr": ("quest", "vr", "pico", "visionpro", "steamvr"),
}


# ── model ───────────────────────────────────────────────────────────────────

@dataclass
class CoreLoop:
    action: str
    feedback: str
    reward: str
    progression: str
    duration_seconds: float = 0.0

    def is_complete(self) -> bool:
        return all(bool(str(x).strip()) for x in
                   (self.action, self.feedback, self.reward, self.progression))

    def missing_parts(self) -> list[str]:
        parts = {"action": self.action, "feedback": self.feedback,
                 "reward": self.reward, "progression": self.progression}
        return sorted(k for k, v in parts.items() if not str(v).strip())


@dataclass
class Feature:
    id: str
    name: str
    description: str = ""
    supports: list[str] = field(default_factory=list)
    effort_days: float = 0.0
    core: bool = False
    must_have: bool = False


@dataclass
class Risk:
    id: str
    description: str
    severity: str = "medium"          # low | medium | high | critical
    likelihood: str = "medium"        # low | medium | high
    mitigation: str = ""


@dataclass
class Milestone:
    id: str
    name: str
    exit_criteria: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)


@dataclass
class SuccessCriterion:
    id: str
    statement: str
    metric: str = ""
    threshold: str = ""
    kind: str = "measurable"          # measurable | timebound | player_visible


@dataclass
class ConceptBrief:
    title: str
    pitch: str
    audience: list[str] = field(default_factory=list)
    platforms: list[str] = field(default_factory=list)
    core_loop: CoreLoop = field(default_factory=lambda: CoreLoop("", "", "", ""))
    features: list[Feature] = field(default_factory=list)
    risks: list[Risk] = field(default_factory=list)
    milestones: list[Milestone] = field(default_factory=list)
    success_criteria: list[SuccessCriterion] = field(default_factory=list)
    raw_idea: str = ""
    vision: str = ""

    # -- structural validation ------------------------------------------------
    def validate(self) -> None:
        if not str(self.title).strip():
            raise ConceptError("brief.title is required")
        if not str(self.pitch).strip():
            raise ConceptError("brief.pitch is required")
        seen: set[str] = set()
        for f in self.features:
            if not f.id:
                raise ConceptError("every feature needs an id")
            if f.id in seen:
                raise ConceptError(f"duplicate feature id: {f.id}")
            seen.add(f.id)
        for r in self.risks:
            if r.severity not in {"low", "medium", "high", "critical"}:
                raise ConceptError(f"risk {r.id}: bad severity {r.severity!r}")
            if r.likelihood not in {"low", "medium", "high"}:
                raise ConceptError(f"risk {r.id}: bad likelihood {r.likelihood!r}")
        mids = {m.id for m in self.milestones}
        for m in self.milestones:
            for dep in m.depends_on:
                if dep not in mids:
                    raise ConceptError(
                        f"milestone {m.id}: depends_on {dep!r} which is not a milestone")


# ── parsing ─────────────────────────────────────────────────────────────────

def _tokens(text: Any) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", str(text).lower()) if len(t) > 2}


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [p.strip() for p in value.split(",") if p.strip()]
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    return [str(value)]


def _feature(raw: dict, index: int) -> Feature:
    return Feature(
        id=str(raw.get("id") or f"F{index:03d}"),
        name=str(raw.get("name", "")),
        description=str(raw.get("description", "")),
        supports=_as_list(raw.get("supports")),
        effort_days=float(raw.get("effort_days", 0) or 0),
        core=bool(raw.get("core", False)),
        must_have=bool(raw.get("must_have", False)),
    )


def build_brief(raw: dict) -> ConceptBrief:
    """Build a validated ConceptBrief from a raw mapping."""
    if not isinstance(raw, dict):
        raise ConceptError("brief source must be a mapping")
    loop_raw = raw.get("core_loop") or {}
    if not isinstance(loop_raw, dict):
        raise ConceptError("core_loop must be a mapping")

    brief = ConceptBrief(
        title=str(raw.get("title", "")),
        pitch=str(raw.get("pitch", "")),
        audience=_as_list(raw.get("audience")),
        platforms=[p.lower() for p in _as_list(raw.get("platforms"))],
        core_loop=CoreLoop(
            action=str(loop_raw.get("action", "")),
            feedback=str(loop_raw.get("feedback", "")),
            reward=str(loop_raw.get("reward", "")),
            progression=str(loop_raw.get("progression", "")),
            duration_seconds=float(loop_raw.get("duration_seconds", 0) or 0),
        ),
        features=[_feature(f, i) for i, f in enumerate(raw.get("features") or [], 1)],
        risks=[
            Risk(
                id=str(r.get("id") or f"R{i:03d}"),
                description=str(r.get("description", "")),
                severity=str(r.get("severity", "medium")).lower(),
                likelihood=str(r.get("likelihood", "medium")).lower(),
                mitigation=str(r.get("mitigation", "")),
            )
            for i, r in enumerate(raw.get("risks") or [], 1)
        ],
        milestones=[
            Milestone(
                id=str(m.get("id") or f"M{i:03d}"),
                name=str(m.get("name", "")),
                exit_criteria=_as_list(m.get("exit_criteria")),
                depends_on=_as_list(m.get("depends_on")),
            )
            for i, m in enumerate(raw.get("milestones") or [], 1)
        ],
        success_criteria=[
            SuccessCriterion(
                id=str(s.get("id") or f"S{i:03d}"),
                statement=str(s.get("statement", "")),
                metric=str(s.get("metric", "")),
                threshold=str(s.get("threshold", "")),
                kind=str(s.get("kind", "measurable")).lower(),
            )
            for i, s in enumerate(raw.get("success_criteria") or [], 1)
        ],
        raw_idea=str(raw.get("raw_idea", "")),
        vision=str(raw.get("vision", "")),
    )
    brief.validate()
    return brief


# ── contradiction detection ─────────────────────────────────────────────────

@dataclass
class Contradiction:
    code: str
    field: str
    detail: str
    severity: str = "high"

    def as_dict(self) -> dict:
        return asdict(self)


def _platform_family(name: str) -> str | None:
    low = name.lower()
    for family, members in _PLATFORM_FAMILIES.items():
        if any(m in low for m in members):
            return family
    return None


def detect_contradictions(brief: ConceptBrief) -> list[Contradiction]:
    """Find brief fields that disagree with one another."""
    out: list[Contradiction] = []

    # 1. Pitch promises something the core loop never does.
    pitch_tokens = _tokens(brief.pitch) | _tokens(brief.vision)
    loop_tokens = _tokens(" ".join([
        brief.core_loop.action, brief.core_loop.feedback,
        brief.core_loop.reward, brief.core_loop.progression,
    ]))
    promised = {t for t in CORE_VERBS if t in pitch_tokens}
    performed = {t for t in CORE_VERBS if t in loop_tokens}
    if promised - performed:
        out.append(Contradiction(
            "pitch_loop_mismatch", "core_loop",
            f"pitch promises {sorted(promised - performed)} but the core loop "
            f"never contains them",
        ))

    # 2. Platform targets wider than the evidence supports (VR + PC together).
    families = {_platform_family(p) for p in brief.platforms} - {None}
    if "vr" in families and "pc" in families and not any(
            f.must_have and "vr" in _tokens(f.description) for f in brief.features):
        out.append(Contradiction(
            "platform_scope_clash", "platforms",
            "targets both VR and PC with no VR-must-have feature justifying the "
            "extra platform surface",
        ))

    # 3. Core loop claims to be complete but is not.
    if not brief.core_loop.is_complete():
        out.append(Contradiction(
            "incomplete_core_loop", "core_loop",
            f"core loop is missing {brief.core_loop.missing_parts()}",
            severity="critical",
        ))

    # 4. A feature marked must_have supports nothing and is not core.
    for f in brief.features:
        if f.must_have and not f.supports and not f.core:
            out.append(Contradiction(
                "orphan_must_have", f"features[{f.id}]",
                f"feature {f.id} is must_have but supports no core-loop part",
            ))

    # 5. Milestone cycle in dependencies.
    deps = {m.id: m.depends_on for m in brief.milestones}
    for start in deps:
        seen, stack = {start}, [start]
        while stack:
            cur = stack.pop()
            for nxt in deps.get(cur, []):
                if nxt == start:
                    out.append(Contradiction(
                        "milestone_cycle", f"milestones[{start}]",
                        f"milestone dependency cycle through {nxt}", "medium"))
                    stack = []
                    break
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
            else:
                continue
            break

    # 6. Critical risk with no mitigation.
    for r in brief.risks:
        if r.severity == "critical" and not r.mitigation.strip():
            out.append(Contradiction(
                "unmitigated_critical_risk", f"risks[{r.id}]",
                f"critical risk {r.id} has no mitigation",
            ))

    return out


# ── scope control ───────────────────────────────────────────────────────────

@dataclass
class ScopeFinding:
    code: str
    field: str
    detail: str
    impact_days: float = 0.0
    severity: str = "medium"

    def as_dict(self) -> dict:
        return asdict(self)


def assess_scope(brief: ConceptBrief, budget_days: float) -> list[ScopeFinding]:
    """Flag uncontrolled scope against an effort budget.

    budget_days is the team's real capacity. Anything that pushes the plan past
    it is uncontrolled scope, named per feature so it can be cut deliberately
    rather than discovered late.
    """
    out: list[ScopeFinding] = []
    if budget_days <= 0:
        raise ConceptError("budget_days must be positive")

    committed = sum(f.effort_days for f in brief.features if f.must_have)
    optional = sum(f.effort_days for f in brief.features if not f.must_have)
    total = committed + optional

    if committed > budget_days:
        out.append(ScopeFinding(
            "committed_exceeds_budget", "committed",
            f"must-have work is {committed:g} days against a {budget_days:g} day "
            f"budget — over by {committed - budget_days:g} days",
            round(committed - budget_days, 2), "critical"))

    for f in brief.features:
        if not f.must_have and f.effort_days > budget_days * 0.15:
            out.append(ScopeFinding(
                "fat_optional_feature", f"features[{f.id}]",
                f"optional feature {f.id} costs {f.effort_days:g} days "
                f"(>15% of the {budget_days:g} day budget) for no core-loop support",
                round(f.effort_days, 2), "high"))

    peripheral = [f for f in brief.features
                  if _tokens(f.name) & PERIPHERAL_MARKERS]
    peripheral_days = sum(f.effort_days for f in peripheral)
    if peripheral and peripheral_days > budget_days * 0.10:
        out.append(ScopeFinding(
            "peripheral_dominates", "features",
            f"peripheral features {[f.id for f in peripheral]} cost "
            f"{peripheral_days:g} days, over 10% of budget",
            round(peripheral_days, 2), "high"))

    if total > budget_days * 1.5:
        out.append(ScopeFinding(
            "plan_unrealistic", "features",
            f"total planned work {total:g} days is more than 1.5x the "
            f"{budget_days:g} day budget",
            round(total - budget_days, 2), "high"))

    return out


def missing_success_criteria(brief: ConceptBrief) -> list[str]:
    """Names of the success-criterion kinds the brief never states."""
    if not brief.success_criteria:
        return sorted(SUCCESS_CRITERIA_TYPES)
    present = {c.kind for c in brief.success_criteria}
    missing = SUCCESS_CRITERIA_TYPES - present
    for c in brief.success_criteria:
        if c.kind == "measurable" and not (c.metric and c.threshold):
            missing.add("measurable")
    return sorted(missing)


# ── core-loop support ───────────────────────────────────────────────────────

def core_loop_support(brief: ConceptBrief) -> dict[str, Any]:
    """Which features carry the core experience, and which do not."""
    parts = {
        "action": brief.core_loop.action,
        "feedback": brief.core_loop.feedback,
        "reward": brief.core_loop.reward,
        "progression": brief.core_loop.progression,
    }
    part_tokens = {k: _tokens(v) for k, v in parts.items()}
    carrying: list[str] = []
    dead_weight: list[str] = []
    coverage: dict[str, list[str]] = {k: [] for k in parts}

    for f in brief.features:
        f_tokens = _tokens(f.name) | _tokens(f.description)
        named = [p for p in f.supports if p in parts]
        if not named:
            named = [k for k, toks in part_tokens.items() if f_tokens & toks]
        if f.core or named:
            carrying.append(f.id)
            for k in named:
                coverage[k].append(f.id)
        else:
            dead_weight.append(f.id)

    uncovered = sorted(k for k, ids in coverage.items() if not ids)
    return {
        "carrying_features": sorted(carrying),
        "features_not_supporting_core": sorted(dead_weight),
        "coverage_by_core_part": {k: sorted(v) for k, v in coverage.items()},
        "uncovered_core_parts": uncovered,
        "support_ratio": round(len(carrying) / len(brief.features), 4)
        if brief.features else 0.0,
    }


# ── controlled GDD ──────────────────────────────────────────────────────────

def render_gdd(brief: ConceptBrief, budget_days: float,
               contradictions: Iterable[Contradiction] = (),
               scope: Iterable[ScopeFinding] = ()) -> str:
    """Render the controlled Game Design Document."""
    cons = list(contradictions)
    sc = list(scope)
    support = core_loop_support(brief)
    missing = missing_success_criteria(brief)
    out: list[str] = []
    w = out.append

    w(f"# {brief.title} — Game Design Document")
    w("")
    w("> Generated by Pipeline 1 (Game Concept, GDD & Scope). "
      "Review every BLOCKER before committing scope.")
    w("")
    w("## Pitch")
    w("")
    w(brief.pitch or "_(none)_")
    if brief.vision:
        w("")
        w("## Vision")
        w("")
        w(brief.vision)
    w("")
    w("## Audience")
    w("")
    w("\n".join(f"- {a}" for a in brief.audience) or "_(not defined)_")
    w("")
    w("## Platforms")
    w("")
    w("\n".join(f"- {p}" for p in brief.platforms) or "_(not defined)_")
    w("")
    w("## Core Loop")
    w("")
    w(f"- **Action** — {brief.core_loop.action or '_missing_'}")
    w(f"- **Feedback** — {brief.core_loop.feedback or '_missing_'}")
    w(f"- **Reward** — {brief.core_loop.reward or '_missing_'}")
    w(f"- **Progression** — {brief.core_loop.progression or '_missing_'}")
    if brief.core_loop.duration_seconds:
        w(f"- **Loop duration** — {brief.core_loop.duration_seconds:g}s")
    w("")
    w("## Success Criteria")
    w("")
    if brief.success_criteria:
        for c in brief.success_criteria:
            detail = f" ({c.metric} ≥ {c.threshold})" if c.metric else ""
            w(f"- **{c.id}** {c.statement}{detail} _[{c.kind}]_")
    else:
        w("- _none defined_")
    if missing:
        w("")
        w(f"> Missing success-criteria kinds: {', '.join(missing)}")
    w("")
    w(f"## Feature List (budget {budget_days:g} days)")
    w("")
    w("| ID | Name | Must | Core | Days | Supports |")
    w("|----|------|------|------|------|----------|")
    for f in brief.features:
        w(f"| {f.id} | {f.name} | {'Y' if f.must_have else 'n'} | "
          f"{'Y' if f.core else 'n'} | {f.effort_days:g} | "
          f"{', '.join(f.supports) or '-'} |")
    w("")
    w("### Features that do not support the core experience")
    w("")
    if support["features_not_supporting_core"]:
        for fid in support["features_not_supporting_core"]:
            feat = next(f for f in brief.features if f.id == fid)
            w(f"- **{fid}** {feat.name} — {feat.effort_days:g} days")
    else:
        w("_every feature carries the core loop_")
    if support["uncovered_core_parts"]:
        w("")
        w(f"> Uncovered core parts: {', '.join(support['uncovered_core_parts'])}")
    w("")
    w("## Risks")
    w("")
    if brief.risks:
        w("| ID | Severity | Likelihood | Description | Mitigation |")
        w("|----|----------|------------|-------------|------------|")
        for r in brief.risks:
            w(f"| {r.id} | {r.severity} | {r.likelihood} | {r.description} | "
              f"{r.mitigation or '**none**'} |")
    else:
        w("_no risks recorded_")
    w("")
    w("## Milestones")
    w("")
    for m in brief.milestones:
        deps = f" (after {', '.join(m.depends_on)})" if m.depends_on else ""
        w(f"### {m.id} — {m.name}{deps}")
        w("")
        for c in m.exit_criteria:
            w(f"- [ ] {c}")
        w("")
    if not brief.milestones:
        w("_no milestones defined_")
        w("")
    w("## Control Findings")
    w("")
    if not cons and not sc:
        w("_no contradictions or scope problems detected_")
    else:
        for c in cons:
            w(f"- **{c.severity.upper()}** `{c.code}` ({c.field}) — {c.detail}")
        for s in sc:
            w(f"- **{s.severity.upper()}** `{s.code}` ({s.field}) — {s.detail}")
    w("")
    w("## Sign-off")
    w("")
    blockers = [c for c in cons if c.severity == "critical"] + \
               [s for s in sc if s.severity == "critical"]
    if blockers:
        w(f"**BLOCKED** — {len(blockers)} critical finding(s) must be resolved "
          f"before scope is committed.")
    else:
        w("**READY FOR REVIEW** — no critical findings. Human decision required "
          "to ship, cut, or iterate.")
    w("")
    return "\n".join(out)


# ── one-call analysis ───────────────────────────────────────────────────────

def analyse(raw: dict, budget_days: float) -> dict[str, Any]:
    """Run the whole pipeline: brief -> contradictions -> scope -> GDD."""
    brief = build_brief(raw)
    cons = detect_contradictions(brief)
    sc = assess_scope(brief, budget_days)
    support = core_loop_support(brief)
    missing = missing_success_criteria(brief)
    critical = [c for c in cons if c.severity == "critical"] + \
               [s for s in sc if s.severity == "critical"]
    return {
        "brief": json.loads(json.dumps(asdict(brief), default=str)),
        "contradictions": [c.as_dict() for c in cons],
        "scope_findings": [s.as_dict() for s in sc],
        "core_loop_support": support,
        "missing_success_criteria": missing,
        "verdict": "BLOCKED" if critical else "READY_FOR_REVIEW",
        "critical_count": len(critical),
        "gdd": render_gdd(brief, budget_days, cons, sc),
    }
