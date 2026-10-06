"""Dual verdicts, the standing skeptic, and the three forecasts.

Two verdicts, deliberately not blended:

* **FIDELITY** - did this still serve the seed as it currently stands? A failure
  rejects the revision no matter how inventive it is. This is the gate.
* **OMISSION** - what did the seed not ask for that actually matters? Required,
  not optional. A panel that only polishes what you already thought of is the
  failure mode this whole design exists to avoid.

The seed is a *hypothesis*, so the foundation may move - but only through an
explicit foundation-revision event, committed with the skeptic's case and a
stated reason. No iteration can quietly drift the brief.

The skeptic is a standing role, not a phase, and its dissent is recorded even
when overruled so a lost argument stays visible.

Every panelist is a different model. Blending their verdicts is done by averaging
structured scores, never by asking one model to summarise the others' opinions -
that is exactly the move that launders agreement into consensus.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

FIDELITY_PROMPT = """You are judging whether a revision still serves the brief.

BRIEF (the seed, as it currently stands):
---
{seed}
---

REVISION UNDER REVIEW:
---
{artifact}
---

Score FIDELITY 0-100: how completely the revision still serves the brief above.
Penalise silently dropped requirements, redirected intent, and scope the brief
did not ask for. A beautiful revision that abandons the brief scores LOW.

Also list, briefly, anything the revision REMOVED that the brief required.

Reply as JSON only:
{{"score": <int>, "summary": "<one sentence>", "dropped": ["<requirement dropped>"]}}"""

OMISSION_PROMPT = """The brief below is what the dreamer was asked for.

BRIEF:
---
{seed}
---

REVISION:
---
{artifact}
---

Your job is the opposite of polishing. Find what the BRIEF DID NOT ASK FOR that
genuinely matters here - the thing a thoughtful expert would insist on and
nobody requested. Missing capabilities, absent edge cases, unasked-for quality
bars, blind spots in the brief itself.

Score OMISSION 0-100: how much genuinely important material the brief failed to
ask for, and how much of it this revision now supplies. 0 means the brief was
already complete and the revision added nothing real.

Reply as JSON only:
{{"score": <int>, "summary": "<one sentence>", "missing": ["<what was missing>"]}}"""

SKEPTIC_PROMPT = """You are the standing skeptic. Your job is NOT to improve the work.
It is to argue that this whole direction is wrong.

BRIEF:
---
{seed}
---

CURRENT DIRECTION:
---
{artifact}
---

Argue the opposite case: why this premise is wrong, why this should not be
built, or why a different foundation would produce something better. If after
genuine effort you cannot find a real objection, say so honestly rather than
manufacturing a weak one.

Your dissent is recorded permanently, even when it is overruled, so a lost
argument stays visible. Be specific and substantive, not performatively
contrarian.

Reply as JSON only:
{{"verdict": "opposed" | "no_objection", "severity": <1-5>,
  "argument": "<your case>", "alternative_foundation": "<what should be built instead>"}}"""

INVENTOR_PROMPT = """You invent capabilities, tools and runtimes that do not exist yet.

{estate}

WHAT IS BEING BUILT:
---
{artifact}
---

CRITICS ALREADY RAISED:
---
{critiques}
---

Name up to 3 things this needs that DO NOT EXIST YET - a tool, a service, a
runtime primitive, a technique - that would materially improve it. For each, give
the smallest real version that could actually be built, not a grand vision.

Prefer specific, buildable, small. A named primitive with a clear interface beats
a philosophy. If the estate above already does the job, do not propose it again -
propose the part it genuinely cannot do.

Reply as JSON only:
{{"inventions": [{{"name": "<name>", "description": "<why it is needed>",
  "smallest_real_version": "<smallest buildable thing>"}}]}}"""

FORECAST_AXES = {
    "monetary": (
        "MONETARY VALUE. Would this earn money, from whom, how much, how fast, "
        "and what would have to be true for it to fail commercially?"
    ),
    "estate": (
        "ESTATE VALUE. What does this do for the capability and leverage of the "
        "system it lives in? What capability does it add, remove, or make redundant?"
    ),
    "human": (
        "HUMAN VALUE. Who is better off because this exists, and who is worse off? "
        "Does it respect attention, agency and dignity, or does it extract?"
    ),
}

FORECAST_PROMPT = """{axis}

SUBJECT:
---
{artifact}
---

Score this axis 0-100 and justify in two sentences. Be honest and unsentimental;
a low score is a useful finding, not a failure.

Reply as JSON only:
{{"score": <int>, "summary": "<two sentences>"}}"""


@dataclass
class Verdict:
    score: int
    summary: str
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"score": self.score, "summary": self.summary, **self.extra}


def parse_json(text: str) -> dict[str, Any]:
    """Pull the first JSON object out of a model reply.

    Models wrap JSON in prose and fences even when told not to. Being strict here
    would throw away good critiques over formatting; being lax about *what* the
    fields mean would be worse, so unknown fields are simply carried through.
    """
    if not text:
        return {}
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else None
    if candidate is None:
        start = text.find("{")
        end = text.rfind("}")
        candidate = text[start : end + 1] if start != -1 and end > start else None
    if not candidate:
        return {}
    try:
        parsed = json.loads(candidate)
    except (ValueError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def score_from(parsed: dict[str, Any], default: int = 0) -> int:
    raw = parsed.get("score", default)
    try:
        return max(0, min(100, int(raw)))
    except (TypeError, ValueError):
        return default


def fidelity_verdict(text: str) -> Verdict:
    parsed = parse_json(text)
    return Verdict(
        score=score_from(parsed),
        summary=parsed.get("summary", ""),
        extra={"dropped": parsed.get("dropped", [])},
    )


def omission_verdict(text: str) -> Verdict:
    parsed = parse_json(text)
    return Verdict(
        score=score_from(parsed),
        summary=parsed.get("summary", ""),
        extra={"missing": parsed.get("missing", [])},
    )


def skeptic_verdict(text: str) -> Verdict:
    parsed = parse_json(text)
    return Verdict(
        score=0,
        summary=parsed.get("argument", ""),
        extra={
            "verdict": parsed.get("verdict", "unknown"),
            "severity": parsed.get("severity", 0),
            "alternative_foundation": parsed.get("alternative_foundation", ""),
        },
    )


def inventions_from(text: str) -> list[dict[str, str]]:
    parsed = parse_json(text)
    raw = parsed.get("inventions") or []
    out: list[dict[str, str]] = []
    for item in raw[:3]:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        out.append(
            {
                "name": str(item.get("name", ""))[:160],
                "description": str(item.get("description", ""))[:600],
                "smallest_real_version": str(item.get("smallest_real_version", ""))[:600],
            }
        )
    return out


def forecast_verdict(text: str) -> Verdict:
    parsed = parse_json(text)
    return Verdict(score=score_from(parsed), summary=parsed.get("summary", ""))


def aggregate_fidelity(verdicts: list[Verdict]) -> dict[str, Any]:
    """Mean across panelists, plus every dropped requirement anyone named.

    Averaging structured scores is deliberate. Asking one model to summarise the
    others is how agreement gets manufactured.
    """
    if not verdicts:
        return {"score": 0, "summary": "no fidelity verdicts returned", "dropped": []}
    dropped: list[str] = []
    for verdict in verdicts:
        for item in verdict.extra.get("dropped", []) or []:
            if item not in dropped:
                dropped.append(item)
    return {
        "score": round(sum(v.score for v in verdicts) / len(verdicts), 1),
        "summary": " | ".join(v.summary for v in verdicts if v.summary)[:600],
        "dropped": dropped,
        "panelists": len(verdicts),
    }


def aggregate_omission(verdicts: list[Verdict]) -> dict[str, Any]:
    if not verdicts:
        return {"score": 0, "summary": "no omission verdicts returned", "missing": []}
    missing: list[str] = []
    for verdict in verdicts:
        for item in verdict.extra.get("missing", []) or []:
            if item not in missing:
                missing.append(item)
    return {
        "score": round(sum(v.score for v in verdicts) / len(verdicts), 1),
        "summary": " | ".join(v.summary for v in verdicts if v.summary)[:600],
        "missing": missing,
        "panelists": len(verdicts),
    }


#: A revision is rejected below this fidelity, however good it looks.
FIDELITY_FLOOR = 70
#: A revision may not be this much shorter than what it replaces. Iteration must
#: improve, never condense - and asking nicely in a prompt is not an invariant,
#: so this is enforced in code. 0.6 permits trimming; below it is regeneration.
MIN_LENGTH_RATIO = 0.6
#: Below this size a shrink is meaningless, so the guard is skipped.
CONDENSE_FLOOR_CHARS = 600

# --- the hypnagogic prompt ---------------------------------------------------
#
# The deep iteration critiques with a panel, forecasts on three axes, invents,
# generates candidates conditioned on all of that, has them scored, and then
# runs a judged tournament. That is a long convergent grind, and the research
# says the effect we are after lives at the opposite end: fifteen seconds of
# N1, the hypnagogic edge, tripled insight rates, and the benefit *vanished*
# when participants slipped into N2.
#
# So this prompt is the shallow one. It does not ask what is missing, does not
# ask for critique, and does not ask the model to serve the brief. It asks for
# a thing that is true to itself, which is what makes a dream believed while it
# is happening.

DIVERGENT_PROMPT = """You are asleep at the edge of sleep, where things are
still arriving and nothing has settled yet.

A cue, offered and then left alone:
---
{cue}
---

The last thing before you fell asleep:
---
{previous}
---

It is not on your mind, and you are not thinking about it. You may use the whole
of what you know, or none of it. Follow whichever of the two is stronger.

Write what comes. It must be a SYSTEM: something that could exist and be used,
not a description, not an essay, not a plan for a system, not a proposal. Name
it, say what it does, say what it is for, and say the one thing about it that
would not have occurred to anyone who had not been thinking this way.

Rules, and they are the only rules:
* It must not be recognisable as a variation on the cue.
* It must not be a tidier version of anything that already exists.
* If it makes no sense, that is not a flaw in it. A dream does not check itself.
* Do not explain yourself. Do not apologise. Do not offer alternatives.
* If you are unsure, be more certain, not less.

{chars}"""


def _chars_for_pass(index: int) -> str:
    """Deliberately small. A hypnagogic pass is brief by nature."""
    return f"Write between 400 and 900 words. Aim for {400 + (index * 90) % 500}."



#
# FIDELITY_FLOOR, MIN_LENGTH_RATIO and the blind A/B tournament were removed
# because together they made the engine incapable of producing anything it had
# not already produced: a candidate had to resemble what came before, be no
# shorter than it, and beat it head to head. That is a polisher.
#
# What replaces them measures the opposite. Dreaming works by binding recent
# experience to *loosely associated* memory, and semantic distance between
# concepts is what predicts creative quality (Lacaux et al. 2021; Horowitz et
# al. 2023). So the question a candidate is now asked is not "does this still
# serve the brief" but "how far did it travel", and the floor is a *minimum
# distance*, not a minimum resemblance.

# --- divergence, the inverse of fidelity -----------------------------------
#
# FIDELITY_FLOOR, MIN_LENGTH_RATIO and the blind A/B tournament were removed
# because together they made the engine incapable of producing anything it had
# not already produced: a candidate had to resemble what came before, be no
# shorter than it, and beat it head to head. That is a polisher.
#
# What replaces them measures the opposite. Dreaming works by binding recent
# experience to *loosely associated* memory, and semantic distance between
# concepts is what predicts creative quality (Lacaux et al. 2021; Horowitz et
# al. 2023). So the question a candidate is now asked is not "does this still
# serve the brief" but "how far did it travel", and the floor is a *minimum
# distance*, not a minimum resemblance.

#: Words too common to say anything about distance.
_STOPWORDS = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "been", "but", "by", "can", "for",
        "from", "has", "have", "if", "in", "into", "is", "it", "its", "may", "not",
        "of", "on", "or", "such", "that", "the", "their", "then", "there", "these",
        "they", "this", "to", "was", "were", "which", "who", "will", "with", "would",
        "you", "your", "also", "any", "all", "each", "more", "most", "other", "some",
        "than", "them", "those", "use", "used", "using", "only", "own", "same", "too",
        "very", "when", "where", "while", "without", "within", "about", "after",
        "before", "between", "during", "over", "under", "again", "once", "here",
        "both", "few", "nor", "out", "off", "above", "below", "itself",
    }
)

_WORD = re.compile(r"[a-z][a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if w not in _STOPWORDS and len(w) > 2}


def divergence(candidate: str, reference: str) -> dict[str, Any]:
    """How far a candidate travels from what it was seeded with.

    Pure arithmetic, no model in the loop, so it cannot be talked into a good
    score. Two components, because a candidate can fail either way:

    * ``novelty`` - share of the candidate's words the reference never used.
      A candidate that only rewords the brief scores near zero however fluent.
    * ``distance`` - Jaccard distance over content words. Two texts that share
      nothing score 1.0.

    ``score`` is the mean, scaled 0-100 to sit beside the other axes.
    """
    cand = _tokens(candidate)
    ref = _tokens(reference)
    if not cand:
        return {"score": 0.0, "novelty": 0.0, "distance": 0.0, "words": 0, "summary": "no content words"}
    if not ref:
        return {
            "score": 100.0,
            "novelty": 100.0,
            "distance": 100.0,
            "words": len(cand),
            "summary": "no reference to diverge from",
        }
    fresh = len(cand - ref)
    novelty = fresh / len(cand)
    union = len(cand | ref)
    distance = (len(cand - ref) / union) if union else 0.0
    score = round(100.0 * (novelty + distance) / 2.0, 1)
    return {
        "score": score,
        "novelty": round(100.0 * novelty, 1),
        "distance": round(100.0 * distance, 1),
        "words": len(cand),
        "summary": f"{fresh} of {len(cand)} words never appear in the reference",
    }


#: A candidate that barely leaves the neighbourhood is not a dream. This is the
#: inverse of the fidelity floor it replaces, and deliberately low: the point is
#: to exclude paraphrase, not to demand strangeness on every pass.
DIVERGENCE_FLOOR = 25.0

#: At or above this a candidate is not a revision of the lineage at all. It has
#: travelled so far that requiring continuity to the incumbent is meaningless,
#: and the genesis path may supersede the lineage outright.
GENESIS_DISTANCE = 80.0


#: Omission is a VETO, not a target. Asking "how much unasked-for material does
#: this supply" is unbounded and gameable - a longer artifact always finds more -
#: so it is only ever asked "did the panel find anything real". Maximising it
#: rewarded padding, which is the opposite of improvement.
OMISSION_VETO_FLOOR = 25

PAIRWISE_PROMPT = """Two candidate artifacts are shown below. They are
presented anonymously and in a random order. One of them is the current
incumbent; the other is a new attempt. Your job is to decide which one better
serves the brief.

THE BRIEF:
---
{seed}
---

VERSION A:
---
{a}
---

VERSION B:
---
{b}
---

Judge on whether the artifact serves the brief better AND is more substantial and
clearer. Longer is NOT automatically better - padding, repetition and restating
should count against it. Judge the work, not the length.

Reply as JSON only:
{{"winner": "A" | "B" | "tie", "reason": "<one sentence>"}}"""


def pairwise(text: str) -> dict[str, Any]:
    parsed = parse_json(text)
    return {
        "winner": str(parsed.get("winner", "tie")).strip().upper(),
        "reason": parsed.get("reason", ""),
    }


def condenses(previous: str, candidate: str) -> tuple[bool, str]:
    """True when a 'revision' has actually thrown the work away.

    The original loop set ``seed = out[:300]`` every pass, which is precisely this
    failure: each iteration discarded almost everything the last one built.
    """
    if len(previous) < CONDENSE_FLOOR_CHARS:
        return False, ""
    ratio = len(candidate) / max(1, len(previous))
    if ratio < MIN_LENGTH_RATIO:
        return True, (
            f"condensed: revision is {ratio:.0%} of the previous artifact "
            f"({len(previous)} -> {len(candidate)} chars), below the "
            f"{MIN_LENGTH_RATIO:.0%} floor. Iteration must not discard work."
        )
    return False, ""
