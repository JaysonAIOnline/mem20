"""The iteration itself.

Order matters, and the order is the safety property: nothing is generated before
the panel has judged the current state, and nothing is accepted before fidelity
has passed. Dreams write text to braid and never touch the filesystem.

Failure handling is deliberate. Over a multi-hour run some call will fail, so:
retry with backoff, then checkpoint the lineage and pause - and say exactly where
it stopped and how to resume, because a run paused at hour three must not read as
a lost run.
"""

from __future__ import annotations

import os
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

sys.path.insert(0, "/opt/mem20")
from llm import LLMError, _load_dotenv, chat

from . import estate, ledger
from . import panel as panel_mod
from . import verdicts as v
from .lineage import Iteration, Lineage

_load_dotenv()

RETRY_ATTEMPTS = 3
RETRY_BACKOFF_S = (2, 8, 30)
#: Rough share of a panelist's context for the lineage digest. The artifact
#: itself is passed separately and in full, so this governs history only.
DIGEST_SHARE = 0.5
#: Revisions generated per iteration, each by a *different* model. One candidate
#: is a gate; several is a choice, and the recorded scores only mean something
#: when they decide the outcome.
CANDIDATES_PER_ITERATION = int(os.environ.get("MEM20DREAM_CANDIDATES", "3"))
#: A writer must be able to emit a WHOLE artifact. At the panel default of 2400
#: tokens a writer was cut off mid-artifact, and its truncated fragment was then
#: correctly rejected by the never-condenses guard - which looked like the panel
#: voting the revision down when it was really a token ceiling. Unused tokens
#: are not billed, so this is set generously.
WRITER_MAX_TOKENS = int(os.environ.get("MEM20DREAM_WRITER_TOKENS", "16000"))
#: Fidelity is a constraint, omission is the objective. So the rule is: satisfy
#: the floor, then take the candidate that most improved what was missing.
SELECTION_OBJECTIVE = "omission"


def ask(
    member: panel_mod.Panelist,
    prompt: str,
    artifact: str = "",
    max_tokens: int | None = None,
) -> tuple[str, str | None]:
    """One panelist call, retried. Returns (text, error).

    An error is returned rather than raised so one silent panelist cannot take
    down a multi-hour run; the caller decides whether the run can continue.
    """
    last_error: str | None = None
    for attempt in range(RETRY_ATTEMPTS):
        try:
            text = chat(
                [{"role": "user", "content": prompt}],
                model=member.model,
                base_url=member.resolved_base(),
                api_key=panel_mod._key_for(member.provider),
                temperature=member.temperature,
                max_tokens=max_tokens or member.max_tokens,
                timeout=180.0,
            )
            if text and text.strip():
                return text, None
            last_error = "empty reply"
        except LLMError as exc:
            last_error = f"LLMError: {str(exc)[:160]}"
        except Exception as exc:  # noqa: BLE001
            last_error = f"{type(exc).__name__}: {str(exc)[:160]}"
        if attempt < RETRY_ATTEMPTS - 1:
            time.sleep(RETRY_BACKOFF_S[min(attempt, len(RETRY_BACKOFF_S) - 1)])
    return "", last_error


def _panel_call(member: panel_mod.Panelist, build_prompt) -> tuple[dict[str, Any], str | None]:
    """Build the prompt per-panelist (so the digest fits their context), then call."""
    prompt = build_prompt(member)
    text, error = ask(member, prompt, "")
    return {"role": member.role, "model": member.model, "text": text}, error


def run_iteration(lineage: Lineage, iteration_n: int) -> Iteration:
    """One full cycle: critique, verdict, invent, forecast, then accept or reject."""
    members = panel_mod.panel()
    seed = lineage.foundation or lineage.seed
    previous = lineage.current_artifact()
    # Measured once per iteration: what is really installed, and what is only
    # claimed. An inventor that does not know this just reinvents the tool that
    # is already on disk.
    try:
        estate_text = estate.context_block()
    except Exception as exc:  # noqa: BLE001 - awareness must never stop a dream
        estate_text = f"ESTATE: unavailable ({type(exc).__name__}: {exc}). Assume nothing."

    def prompt_with_digest(template: str) -> Any:
        def build(member: panel_mod.Panelist) -> str:
            digest = lineage.lineage_digest(int(member.context * DIGEST_SHARE))
            return template.format(
                seed=seed, artifact=previous, digest=digest, estate=estate_text
            )

        return build

    critiques: list[dict[str, Any]] = []
    errors: list[str] = []

    # --- 1. the panel critiques the current state, in parallel ------------
    critics = [m for m in members if m.role in panel_mod.CRITIC_ROLES]
    if not critics:
        raise LLMError("no funded panel members; cannot dream honestly")

    with ThreadPoolExecutor(max_workers=len(critics)) as pool:
        results = list(
            pool.map(
                lambda m: _panel_call(m, prompt_with_digest(v.FIDELITY_PROMPT)),
                critics,
            )
        )
    for member, (payload, error) in zip(critics, results, strict=False):
        if error:
            errors.append(f"{member.role}: {error}")
            continue
        critiques.append({**payload, "kind": "critique", "text": payload["text"][:4000]})

    # If not one panelist answered, there is no dream here - only a failed call.
    # Committing an empty iteration would manufacture an iteration that never
    # happened, and a run of them (an idle timer through a DNS outage) writes a
    # lineage of hollow nodes into the ledger. Abort instead, so the caller
    # checkpoints and pauses, which is what a total provider failure deserves.
    if not critiques and errors:
        raise LLMError(
            f"no panelist answered; {len(errors)} call(s) failed: "
            + "; ".join(e[:180] for e in errors[:3])
        )

    # --- 2. omission of the CURRENT state, as input to the revision -------
    # This is the "what is missing" list that drives synthesis. It is *not* the
    # recorded score: judging the pre-revision state can never demonstrate that
    # the revision improved anything, which would make the score history
    # meaningless. The recorded omission is judged on the candidate, below.
    omission_input: dict[str, Any] = {}
    omission_member = next((m for m in critics if m.role == "product"), critics[-1])
    om_text, om_err = ask(
        omission_member,
        v.OMISSION_PROMPT.format(seed=seed, artifact=previous, digest=""),
        "",
    )
    if om_err:
        errors.append(f"omission/{omission_member.role}: {om_err}")
    omission_input = (
        v.aggregate_omission([v.omission_verdict(om_text)])
        if om_text
        else {"score": 0, "summary": f"omission verdict unavailable: {om_err}", "missing": []}
    )
    omission_input["judged_by"] = f"{omission_member.role} via {omission_member.model}"

    # Fidelity is judged later, against the candidate revision, not here.

    # --- 3. the skeptic, permanently --------------------------------------
    skeptic_member = panel_mod.by_role("skeptic")
    skeptic: dict[str, Any] = {"verdict": "unavailable", "argument": ""}
    if skeptic_member:
        sk_text, sk_err = ask(
            skeptic_member, v.SKEPTIC_PROMPT.format(seed=seed, artifact=previous), ""
        )
        if sk_err:
            errors.append(f"skeptic: {sk_err}")
        elif sk_text:
            skeptic = v.skeptic_verdict(sk_text).as_dict()
            critiques.append(
                {"role": "skeptic", "model": skeptic_member.model, "kind": "skeptic",
                 "text": sk_text[:4000], "verdict": skeptic}
            )

    # --- 4. the three forecasts, rubrics fixed at seed time ---------------
    forecast: dict[str, Any] = {}
    axis_member = omission_member
    for axis, description in v.FORECAST_AXES.items():
        text, err = ask(
            axis_member,
            v.FORECAST_PROMPT.format(axis=description, artifact=previous),
            "",
        )
        if err:
            errors.append(f"forecast/{axis}: {err}")
            forecast[axis] = {"score": 0, "summary": f"unavailable: {err}"}
        else:
            forecast[axis] = v.forecast_verdict(text).as_dict()

    # --- 5. invention, from what the panel actually found -----------------
    invented: list[dict[str, str]] = []
    inventor = panel_mod.by_role("systems_inventor")
    if inventor:
        joined = "\n".join(f"- {c.get('role')}: {c.get('text','')[:600]}" for c in critiques)[:6000]
        inv_text, inv_err = ask(
            inventor,
            v.INVENTOR_PROMPT.format(
                artifact=previous, critiques=joined, estate=estate_text
            ),
            "",
        )
        if inv_err:
            errors.append(f"inventor: {inv_err}")
        else:
            invented = v.inventions_from(inv_text)

    # --- 6. the dreamer evolves -------------------------------------------
    evolved = _evolve_dreamer(lineage, omission_input, skeptic, iteration_n)

    # --- 7. synthesise a candidate, then gate the CANDIDATE ---------------
    # The gate must judge the new revision, not the previous artifact. Judging
    # the previous state deadlocks: if fidelity is scored on what we already
    # have, a rejected revision never advances the artifact, so the next
    # iteration scores the same unchanged artifact and can never escape.
    #
    # Iteration 1 is the baseline: the artifact IS the brief, so there is nothing
    # to gate and nothing to synthesise yet.
    if iteration_n == 1:
        iteration = Iteration(
            n=1,
            artifact=previous,
            fidelity={
                "score": 100.0,
                "summary": "baseline: the artifact is the brief, so fidelity is definitional",
                "dropped": [],
                "panelists": 0,
            },
            omission=omission_input,
            forecast=forecast,
            critiques=critiques + ([{"role": "skeptic", "verdict": skeptic}] if skeptic else []),
            inventions_added=[i["name"] for i in invented],
            dreamer_evolved=evolved,
            accepted=True,
        )
        if errors:
            iteration.critiques.append(
                {"role": "system", "kind": "errors", "text": "; ".join(errors)[:1500]}
            )
        for item in invented:
            lineage.inventions.add(
                item["name"], item.get("description", ""),
                item.get("smallest_real_version", ""), iteration_n,
            )
        return iteration

    # --- 7. generate several candidates, score them all, then CHOOSE ---------
    # Fidelity is the constraint, omission is the objective. The objective is
    # ratcheted so it can never move backwards, which is what makes the recorded
    # improvement real rather than incidental.
    writers = panel_mod.panel()
    writers = writers[:CANDIDATES_PER_ITERATION] or writers[:1]

    def _gen(item: tuple[int, panel_mod.Panelist]) -> tuple[panel_mod.Panelist, str, str | None]:
        idx, writer = item
        text, err = _generate_candidate(
            lineage, writer, critiques, omission_input, invented, iteration_n, idx
        )
        return writer, text, err

    with ThreadPoolExecutor(max_workers=len(writers)) as pool:
        generated = list(pool.map(_gen, enumerate(writers, start=1)))

    best_so_far = 0.0
    for prior in lineage.score_history:
        value = prior.get("omission")
        if isinstance(value, (int, float)):
            best_so_far = max(best_so_far, float(value))

    scored: list[dict[str, Any]] = []
    for writer, text, err in generated:
        if err or not text:
            errors.append(f"candidate/{writer.role}: {err or 'empty revision'}")
            continue
        result = _score_candidate(text, writer, seed, previous)
        result["text"] = text
        scored.append(result)

    selection = _select(scored, previous, seed)

    if selection["chosen"] is None:
        fidelity = {
            "score": 0.0,
            "summary": f"no candidate adopted: {selection['reason']}",
            "dropped": [],
            "panelists": len(scored),
        }
        omission = dict(omission_input)
        accepted = False
        rejection = f"rejected: {selection['reason']}"
    else:
        winner = selection["chosen"]
        genesis = bool(selection.get("genesis"))
        if genesis:
            # A candidate this far from the incumbent is not a revision of this
            # lineage. Adopt it wholesale and say so in the record, so the
            # lineage's history shows where it stopped being the same thing.
            # The prior artifact is not discarded: it stays in the braid chain
            # and in the superseded field, because a dream that erases its own
            # past cannot be audited.
            lineage.superseded = {
                "artifact": lineage.artifact,
                "at_iteration": iteration_n,
                "divergence": winner.get("divergence_score"),
                "reason": selection["reason"],
            }
        lineage.artifact = winner["text"]
        fidelity = dict(winner["fidelity"])
        omission = dict(winner["omission"])
        omission["previous_score"] = omission_input.get("score")
        omission["delta"] = round(
            float(omission.get("score", 0)) - float(omission_input.get("score", 0)), 1
        )
        # Adopted, because it opened ground the lineage had not occupied.
        accepted = True
        rejection = ""

    # The full selection record: every candidate, its scores, and why it lost.
    selection_record = {
        "reason": selection["reason"],
        "genesis": bool(selection.get("genesis")),
        "supersedes_lineage": bool(selection.get("supersedes_lineage")),
        "candidates": [
            {k: val for k, val in c.items() if k != "text"} for c in scored
        ],
    }


    iteration = Iteration(
        n=iteration_n,
        artifact=lineage.current_artifact(),
        fidelity=fidelity,
        omission=omission,
        forecast=forecast,
        critiques=critiques + ([{"role": "skeptic", "verdict": skeptic}] if skeptic else []),
        inventions_added=[i["name"] for i in invented],
        dreamer_evolved=evolved,
        accepted=accepted,
        rejection_reason=rejection,
        selection=selection_record,
    )
    if errors:
        iteration.critiques.append({"role": "system", "kind": "errors", "text": "; ".join(errors)[:1500]})
    for item in invented:
        lineage.inventions.add(
            item["name"], item.get("description", ""),
            item.get("smallest_real_version", ""), iteration_n,
        )
    return iteration


def nap_pass(
    lineage: Lineage,
    cue: str,
    pass_n: int,
    breadth: int | None = None,
) -> dict[str, Any]:
    """One hypnagogic pass: many candidates, no panel round, arithmetic judging.

    This is the shallow shape the research points at. The deep iteration is a
    long convergent grind - critique, forecast, invent, condition, score, then a
    judged tournament - and the creative effect we are chasing lives at the
    opposite end of sleep, where it is brief, frequent and unjudged.

    What this pass drops: the critique round, the three forecast axes, the
    invention spawn, the digest, and every model-as-judge call. What it keeps:
    one model per candidate so the generations stay genuinely different, the
    divergence floor so a paraphrase cannot pass as a dream, the genesis path,
    braid commit, and the refusal to run unfunded.
    """
    members = panel_mod.panel()
    if not members:
        raise LLMError("no funded panel members; cannot dream honestly")

    width = breadth or len(members)
    writers = (members * ((width // len(members)) + 1))[:width]
    previous = lineage.current_artifact()

    def build(member: panel_mod.Panelist, index: int) -> str:
        head = previous[:1200] if previous else ""
        return v.DIVERGENT_PROMPT.format(
            cue=cue, previous=head, chars=v._chars_for_pass(index)
        )

    with ThreadPoolExecutor(max_workers=len(writers)) as pool:
        results = list(
            pool.map(
                lambda item: _panel_call(item[1], lambda m, i=item[0]: build(m, i)),
                list(enumerate(writers)),
            )
        )

    candidates: list[dict[str, Any]] = []
    errors: list[str] = []
    for index, (reply, err) in enumerate(results):
        if err or not reply:
            errors.append(f"writer {index}: {err or 'empty reply'}")
            continue
        text = reply.get("text") if isinstance(reply, dict) else str(reply)
        if not text or len(text.strip()) < 200:
            errors.append(f"writer {index}: reply too short to be a dream")
            continue
        travelled = v.divergence(text, previous or cue)
        candidates.append(
            {
                "writer": f"{writers[index].role} via {writers[index].model}",
                "text": text,
                "divergence": travelled,
                "divergence_score": travelled["score"],
                "genesis": travelled["score"] >= v.GENESIS_DISTANCE,
                "eligible": travelled["score"] >= v.DIVERGENCE_FLOOR,
            }
        )

    if not candidates:
        return {
            "pass": pass_n,
            "accepted": False,
            "reason": "every writer failed or returned nothing dreamable",
            "errors": errors,
            "candidates": [],
        }

    winner = max(candidates, key=lambda c: c["divergence_score"])
    if not winner["eligible"]:
        furthest = max(candidates, key=lambda c: c["divergence_score"])
        return {
            "pass": pass_n,
            "accepted": False,
            "reason": (
                f"nothing travelled: furthest was {furthest['divergence_score']}, "
                f"below the divergence floor of {v.DIVERGENCE_FLOOR}"
            ),
            "errors": errors,
            "candidates": [{k: c[k] for k in ("writer", "divergence_score", "genesis")} for c in candidates],
        }

    genesis = bool(winner["genesis"])
    if genesis:
        lineage.superseded = {
            "artifact": lineage.artifact,
            "at_pass": pass_n,
            "divergence": winner["divergence_score"],
            "reason": f"pass {pass_n} travelled {winner['divergence_score']}",
        }
    lineage.artifact = winner["text"]

    iteration = Iteration(
        n=len(lineage.iterations) + 1,
        artifact=lineage.current_artifact(),
        fidelity={"score": winner["divergence_score"], "summary": "divergence, not fidelity"},
        omission={"score": 0.0, "summary": "not judged: this pass is shallow by design", "missing": []},
        forecast={},
        critiques=[
            {"role": "nap", "kind": "cue", "text": cue},
            {
                "role": "nap",
                "kind": "divergence",
                "text": f"{winner['writer']} travelled {winner['divergence_score']} "
                f"(genesis={genesis})",
            },
        ],
        inventions_added=[],
        dreamer_evolved=False,
        accepted=True,
        rejection_reason="",
        selection={
            "reason": (
                f"{winner['writer']} travelled furthest of {len(candidates)} "
                f"({winner['divergence_score']})"
            ),
            "genesis": genesis,
            "supersedes_lineage": genesis,
            "pass": pass_n,
            "candidates": [
                {k: c[k] for k in ("writer", "divergence_score", "genesis", "eligible")}
                for c in candidates
            ],
        },
    )
    if errors:
        iteration.critiques.append({"role": "system", "kind": "errors", "text": "; ".join(errors)[:1500]})
    lineage.record(iteration)
    committed = ledger.commit_iteration(lineage, iteration)
    if committed.get("committed"):
        lineage.braid_cids.append(str(committed.get("cid", "")))
    else:
        lineage.uncommitted.append({"at_pass": pass_n, "reason": committed.get("reason", "")})
    lineage.save()

    return {
        "pass": pass_n,
        "accepted": True,
        "genesis": genesis,
        "reason": iteration.selection["reason"],
        "divergence": winner["divergence_score"],
        "writer": winner["writer"],
        "candidates": len(candidates),
        "errors": errors,
        "braid": bool(committed.get("committed")),
        "artifact_chars": len(lineage.current_artifact()),
    }


def nap(
    cue: str,
    passes: int = 8,
    breadth: int = 6,
    lineage: Lineage | None = None,
) -> dict[str, Any]:
    """Run several shallow passes on one lineage, keeping every keeper.

    Each pass starts from whatever the previous one left, so the lineage drifts
    rather than restarting - and because a pass may supersede outright, the
    drift is allowed to become a jump.
    """
    lineage = lineage or new_dream(cue, kind="idle_idea", foundation=cue)
    results = []
    for pass_n in range(1, passes + 1):
        result = nap_pass(lineage, cue, pass_n, breadth=breadth)
        results.append(result)
        if not result["accepted"]:
            break
    return {
        "dream_id": lineage.dream_id,
        "cue": cue,
        "passes_run": len(results),
        "accepted": sum(1 for r in results if r["accepted"]),
        "genesis": any(r.get("genesis") for r in results),
        "results": results,
        "artifact_chars": len(lineage.current_artifact()),
        "iterations": len(lineage.iterations),
    }


def _generate_candidate(
    lineage: Lineage,
    writer: panel_mod.Panelist,
    critiques: list[dict[str, Any]],
    omission: dict[str, Any],
    invented: list[dict[str, str]],
    iteration_n: int,
    index: int,
) -> tuple[str, str | None]:
    joined = "\n\n".join(
        f"[{c.get('role')} via {c.get('model')}]\n{c.get('text','')[:3000]}" for c in critiques
    )[:24000]
    missing = "\n".join(f"- {m}" for m in omission.get("missing", [])[:12])
    invent = "\n".join(f"- {i['name']}: {i.get('smallest_real_version','')}" for i in invented)
    history = "\n".join(
        f"  iter {c['n']} (accepted={c.get('accepted')}): {c.get('change','')[:180]}"
        for c in lineage.changelog[-6:]
    )

    prompt = f"""You are REVISING an existing artifact in place. This is revision
{index} of {CANDIDATES_PER_ITERATION} independent attempts at iteration {iteration_n} of a
continuing process. Another model is attempting the same revision; aim for the
strongest result, not the safest one.

THE BRIEF (must still be served):
---
{lineage.foundation or lineage.seed}
---

THE ARTIFACT AS IT STANDS NOW (edit THIS, do not replace it):
---
{lineage.current_artifact()[:24000]}
---

WHAT PREVIOUS ITERATIONS CHANGED (so you do not undo their work):
{history or '- (this is the first revision)'}

EXPERT CRITIQUE (each critique from a different model):
{joined}

WHAT THE CRITIQUE SAYS WAS NEVER ASKED FOR:
{missing or '- (none named)'}

THINGS INVENTED THAT DO NOT EXIST YET (reference where relevant, do not fake them):
{invent or '- (none)'}

RULES FOR THIS REVISION - these matter more than anything else above:
1. START from the artifact above and EDIT IT. Preserve its structure, its depth
   and everything that already works. Do not restart from scratch.
2. Do not LOSE content. If the current artifact contains sections, examples or
   detail that are not contradicted by the critique, they must still be there in
   your output. Length must stay broadly the same or grow. If your output is
   radically shorter than the input, you have condensed instead of revised.
3. Change only what the critique actually demands, and add what it says was missing.
4. Keep every requirement from the brief.
5. Never invent a capability you cannot describe concretely.
6. Do not pad. If the artifact grew last iteration by restating itself, cut that
   padding and spend the words on substance instead.

Reply with the full revised artifact and nothing else.
"""
    text, error = ask(writer, prompt, "", max_tokens=WRITER_MAX_TOKENS)
    return (text.strip() if text else ""), error


def _score_candidate(
    candidate: str,
    writer: panel_mod.Panelist,
    seed: str,
    previous: str,
) -> dict[str, Any]:
    """Judge one candidate on both axes, using models that did not write it.

    Eligibility is now *divergence from the incumbent*, not fidelity to it and
    not length relative to it. A revision that rewords the brief scores zero
    however well it is written; one that opens new ground is eligible however
    little it resembles what came before.
    """
    members = panel_mod.panel()
    judges = [m for m in members if m.model != writer.model]
    fid_judge = next((m for m in judges if m.role != "product"), judges[0])
    om_judge = next((m for m in judges if m.role == "product"), judges[-1])
    if om_judge.model == writer.model:
        om_judge = fid_judge

    fid_text, fid_err = ask(fid_judge, v.FIDELITY_PROMPT.format(seed=seed, artifact=candidate, digest=""), "")
    om_text, om_err = ask(om_judge, v.OMISSION_PROMPT.format(seed=seed, artifact=candidate, digest=""), "")

    fidelity = (
        v.aggregate_fidelity([v.fidelity_verdict(fid_text)])
        if fid_text
        else {"score": 0.0, "summary": f"fidelity judge unavailable: {fid_err}", "dropped": []}
    )
    omission = (
        v.aggregate_omission([v.omission_verdict(om_text)])
        if om_text
        else {"score": 0.0, "summary": f"omission judge unavailable: {om_err}", "missing": []}
    )
    fidelity["judged_by"] = f"{fid_judge.role} via {fid_judge.model}"
    omission["judged_by"] = f"{om_judge.role} via {om_judge.model}"

    travelled = v.divergence(candidate, previous or seed)
    from_seed = v.divergence(candidate, seed)
    genesis = travelled["score"] >= v.GENESIS_DISTANCE
    return {
        "writer": f"{writer.role} via {writer.model}",
        "length": len(candidate),
        "fidelity": fidelity,
        "omission": omission,
        "fidelity_score": float(fidelity.get("score", 0)),
        "omission_score": float(omission.get("score", 0)),
        "divergence": travelled,
        "divergence_score": travelled["score"],
        "divergence_from_seed": from_seed,
        "genesis": genesis,
        "eligible": travelled["score"] >= v.DIVERGENCE_FLOOR,
        "objective": float(omission.get("score", 0)),
    }


#: Preferred pairwise judges, strongest first. The arbiter decides whether
#: anything improved, so a weak judge silently freezes the dream: routed to the
#: 7B skeptic, the incumbent won every contest regardless of candidate quality.
#: A judge that cannot tell two artifacts apart returns "incumbent stands" every
#: time, which looks like convergence and is actually blindness.
JUDGE_PREFERENCE = (
    "command-a-plus-05-2026",
    "command-a-reasoning-08-2025",
    "openai/gpt-oss-120b",
    "c4ai-aya-expanse-32b",
    "command-a-03-2025",
    "qwen/qwen3.6-27b",
    "openai/gpt-oss-20b",
    "allam-2-7b",
)


def _choose_judge(exclude_model: str) -> panel_mod.Panelist | None:
    """Strongest available model that did not write the artifact being judged."""
    members = panel_mod.panel()
    by_model = {m.model: m for m in members}
    for model in JUDGE_PREFERENCE:
        if model != exclude_model and model in by_model:
            return by_model[model]
    for member in members:
        if member.model != exclude_model:
            return member
    return None


def _pairwise(incumbent: str, candidate: str, writer: panel_mod.Panelist, seed: str) -> dict[str, Any]:
    """Blind comparison of the incumbent against one candidate.

    Both are shown anonymously in a randomised order and judged by a strong model
    that wrote neither. This is what selection maximises, because "is the idea
    better" is the question the panel is otherwise unable to answer about itself
    - a model grading its own output on a self-reported 0-100 is grading its own
    homework. A blind A/B is the cheapest honest substitute, and the one that
    cannot be satisfied by writing more words.
    """
    judge = _choose_judge(writer.model)
    if judge is None:
        return {"winner": "tie", "reason": "no judge available", "judged_by": "none"}

    # Deterministic-but-varied order so a position bias cannot be farmed by
    # always presenting the incumbent first.
    incumbent_first = (len(candidate) + len(seed)) % 2 == 0
    a, b = (incumbent, candidate) if incumbent_first else (candidate, incumbent)
    text, error = ask(
        judge,
        v.PAIRWISE_PROMPT.format(seed=seed, a=a[:18000], b=b[:18000]),
        "",
        max_tokens=900,
    )
    if error or not text:
        return {
            "winner": "tie",
            "reason": f"judge unavailable: {error}",
            "judged_by": f"{judge.role} via {judge.model}",
        }

    verdict = v.pairwise(text)
    winner = verdict["winner"]
    if winner == "tie":
        outcome = "tie"
    else:
        chose_incumbent = (winner == "A") == incumbent_first
        outcome = "incumbent" if chose_incumbent else "candidate"
    return {
        "winner": outcome,
        "reason": verdict["reason"],
        "judged_by": f"{judge.role} via {judge.model}",
        "order": "incumbent_first" if incumbent_first else "candidate_first",
    }


def _select(scored: list[dict[str, Any]], incumbent: str, seed: str) -> dict[str, Any]:
    """Choose the candidate that opened the most territory.

    The blind tournament is gone. It required a candidate to *beat the
    incumbent*, which guaranteed the artifact could only ever be a refinement of
    itself: an engine with no legal way to become something else cannot produce
    the unprecedented, however it is seeded.

    What remains is honest rather than convergent:

    * a candidate that barely leaves the neighbourhood is ineligible, so
      paraphrasing the brief is not mistaken for progress;
    * the omission veto is kept, because it is the one guard that *demands*
      novelty - an iteration that found nothing real did no work;
    * the winner is the candidate that travelled furthest, and the pairwise
      comparison is still run and recorded as evidence, but it no longer vetoes.
    """
    eligible = [c for c in scored if c["eligible"]]
    if not eligible:
        return {
            "chosen": None,
            "reason": (
                f"no candidate travelled: all {len(scored)} stayed within "
                f"{v.DIVERGENCE_FLOOR} of the incumbent, so none of them is a dream"
            ),
            "contests": [],
        }

    vetoed = [c for c in eligible if float(c["omission_score"]) < v.OMISSION_VETO_FLOOR]
    pool = [c for c in eligible if float(c["omission_score"]) >= v.OMISSION_VETO_FLOOR]
    if not pool:
        return {
            "chosen": None,
            "reason": (
                f"all {len(eligible)} candidates vetoed: omission below "
                f"{v.OMISSION_VETO_FLOOR}, so the panel found nothing genuinely new"
            ),
            "contests": [],
            "vetoed": [c["writer"] for c in vetoed],
        }

    contests: list[dict[str, Any]] = []
    for candidate in pool:
        result = _pairwise(incumbent, candidate["text"], _writer_of(candidate), seed)
        candidate["pairwise"] = result
        contests.append({"candidate": candidate["writer"], "evidence_only": True, **result})

    winner = max(pool, key=lambda c: (float(c["divergence_score"]), float(c["omission_score"])))
    genesis = bool(winner.get("genesis"))
    return {
        "chosen": winner,
        "genesis": genesis,
        "reason": (
            f"{winner['writer']} travelled furthest "
            f"(divergence {winner['divergence_score']}, omission {winner['omission_score']})"
            + (
                f"; at or above the genesis distance of {v.GENESIS_DISTANCE} it is not a "
                f"revision of this lineage and may supersede it outright"
                if genesis
                else ""
            )
        ),
        "contests": contests,
        "supersedes_lineage": genesis,
    }


def _writer_of(candidate: dict[str, Any]) -> panel_mod.Panelist:
    """Recover the Panelist that produced a candidate, for judge exclusion."""
    model = str(candidate.get("writer", "")).split(" via ")[-1]
    return next((m for m in panel_mod.panel() if m.model == model), panel_mod.panel()[0])


def _evolve_dreamer(
    lineage: Lineage, omission: dict[str, Any], skeptic: dict[str, Any], iteration_n: int
) -> bool:
    """Self-improvement: the dreamer gets better at dreaming this lineage.

    Config and technique-library evolution only, per lineage, never global.
    Real weight retraining is a later, separate step and depends on compute we
    do not have on this host.
    """
    before = len(lineage.dreamer.techniques) + len(lineage.dreamer.guidance)
    for item in omission.get("missing", [])[:3]:
        lineage.dreamer.add_technique(f"watch for: {item}")
    if skeptic.get("verdict") == "opposed" and skeptic.get("alternative_foundation"):
        lineage.dreamer.guidance.append(
            f"the skeptic has argued the foundation should change: "
            f"{str(skeptic['alternative_foundation'])[:180]}"
        )
    lineage.dreamer.evolved_at_iteration = iteration_n
    after = len(lineage.dreamer.techniques) + len(lineage.dreamer.guidance)
    return after > before


def new_dream(seed: str, kind: str = "active", foundation: str = "") -> Lineage:
    dream_id = f"dream-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    lineage = Lineage(
        dream_id=dream_id,
        seed=seed,
        kind=kind,
        foundation=foundation or seed,
        artifact=seed,
    )
    lineage.save()
    return lineage


def revise_foundation(lineage: Lineage, new_foundation: str, reason: str, skeptic_case: str) -> None:
    """The only path by which the brief may change. Always explicit, always logged."""
    lineage.foundation_revisions.append(
        {
            "at": time.time(),
            "from": lineage.foundation,
            "to": new_foundation,
            "reason": reason,
            "skeptic_case": skeptic_case,
        }
    )
    lineage.foundation = new_foundation
    lineage.save()
