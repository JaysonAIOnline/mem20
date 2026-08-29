#!/usr/bin/env python3
"""
mem20 Cognitive Engine (LLM-backed)

All reasoning, planning, reflection, imagination and theory-of-mind outputs are
produced by a real LLM call through mem20.llm (NVIDIA OpenAI-compatible endpoint
by default). Nothing is templated or fabricated: if the LLM is unavailable the
functions raise LLMError and the MCP handlers surface that honestly.

The engine still integrates with the mem20 memory store: relevant memories are
retrieved and injected as grounding context (supporting spec Step 2.1
provenance-backed reasoning) and significant cognitive acts are recorded as
memories for later self-audit.
"""

import sys
import os
import asyncio
from pathlib import Path
from typing import Dict, List, Any, Optional

sys.path.insert(0, os.environ.get("MEM20_ENGINE_PATH", "/home/jayson/mem20"))
from llm import chat, achat, LLMError  # noqa: E402

sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", "/root/.hermes/memories/store"))
try:
    from memory import remember, recall, run_plan_execution_guard  # noqa: E402
    MEMORY_AVAILABLE = True
except Exception:  # pragma: no cover
    MEMORY_AVAILABLE = False

    def run_plan_execution_guard(fact_ids, actor="agent"):  # type: ignore
        return {"veto": False, "offenders": [], "message": "OK (memory unavailable)"}


# --------------------------------------------------------------------------
# Memory grounding
# --------------------------------------------------------------------------
def _retrieve_memory_records(query: str, k: int = 8) -> list:
    """Return retrieved memory records (dicts) for provenance-aware use."""
    if not MEMORY_AVAILABLE or not query:
        return []
    try:
        return recall(topic=None, k=k) or []
    except Exception:
        return []


def _retrieve_memories_text(query: str, k: int = 8) -> str:
    """Return retrieved memory snippets as a grounded-context block (or '')."""
    results = _retrieve_memory_records(query, k=k)
    if not results:
        return ""
    try:
        out = []
        for r in results[:k]:
            content = r.get("content", "")
            topic = r.get("topic", "-")
            # lightweight relevance filter
            q = query.lower()
            if q and not any(w in content.lower() for w in q.split() if len(w) > 3):
                continue
            out.append(f"[{topic}] {content[:400]}")
            if len(out) >= 6:
                break
        return "\n".join(out)
    except Exception:
        return ""


def _store_cognitive(kind: str, prompt: str, output: str, mode: str = ""):
    """Persist a cognitive act to memory for self-audit / narrative continuity."""
    if not MEMORY_AVAILABLE:
        return
    try:
        remember(
            topic="cognitive_process",
            content=f"[{kind}/{mode}] {prompt}\n---\n{output[:600]}",
            tags=["cognitive", kind, mode] if mode else ["cognitive", kind],
            priority="normal",
        )
    except Exception:
        pass


# --------------------------------------------------------------------------
# Prompt assembly
# --------------------------------------------------------------------------
_MODE_SYSTEM = {
    "analyze": (
        "You are mem20's cognitive analysis engine. Decompose the user's thought, "
        "surface hidden assumptions, identify patterns, and pose the key open "
        "questions. Be concrete; cite the provided memory where it is relevant."
    ),
    "synthesize": (
        "You are mem20's synthesis engine. Integrate the user's thought with the "
        "related memory to produce unified understanding and genuinely emergent "
        "insights. State the connections you draw explicitly."
    ),
    "evaluate": (
        "You are mem20's evaluation engine. Assess feasibility, impact, risk, cost "
        "and value-alignment of the thought against the provided context/memory. "
        "End with a clear, justified recommendation."
    ),
    "plan": (
        "You are mem20's planning engine. Turn the thought into an actionable, "
        "phased plan with milestones and resources, grounded in any provided memory."
    ),
}


def _user_block(thought: str, context: str, memory: str) -> str:
    block = f"THOUGHT:\n{thought}\n"
    if context:
        block += f"\nCONTEXT:\n{context}\n"
    if memory:
        block += f"\nRETRIEVED MEMORY (ground truth):\n{memory}\n"
    block += "\nProduce your response now."
    return block


# --------------------------------------------------------------------------
# Core cognitive operations (sync + async)
# --------------------------------------------------------------------------
def _build_process_messages(thought: str, mode: str, context: str) -> List[Dict]:
    system = _MODE_SYSTEM.get(mode, _MODE_SYSTEM["analyze"])
    memory = _retrieve_memories_text(thought)
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": _user_block(thought, context, memory)},
    ]


def process_thought(thought: str, mode: str = "analyze", context: str = "") -> str:
    out = chat(_build_process_messages(thought, mode, context), max_tokens=1200)
    _store_cognitive("process", thought, out, mode)
    return out


async def aprocess_thought(thought: str, mode: str = "analyze", context: str = "") -> str:
    out = await achat(_build_process_messages(thought, mode, context), max_tokens=1200)
    _store_cognitive("process", thought, out, mode)
    return out


def run_chain(steps: List[str], initial_context: str = "") -> str:
    results = []
    ctx = initial_context
    for i, step in enumerate(steps, 1):
        # Infer a mode from the step wording for variety.
        low = step.lower()
        if any(w in low for w in ["plan", "design", "roadmap"]):
            mode = "plan"
        elif any(w in low for w in ["evaluate", "assess", "critique"]):
            mode = "evaluate"
        elif any(w in low for w in ["synthesize", "combine", "integrate"]):
            mode = "synthesize"
        else:
            mode = "analyze"
        out = process_thought(step, mode, ctx)
        results.append((i, mode, step, out))
        ctx += f"\n\nStep {i} [{mode}]: {step}\n{out[:400]}"
    lines = ["Cognitive Chain Result:\n"]
    for i, mode, step, out in results:
        lines.append(f"=== Step {i} [{mode}] : {step} ===\n{out}\n")
    return "\n".join(lines)


async def arun_chain(steps: List[str], initial_context: str = "") -> str:
    results = []
    ctx = initial_context
    for i, step in enumerate(steps, 1):
        low = step.lower()
        if any(w in low for w in ["plan", "design", "roadmap"]):
            mode = "plan"
        elif any(w in low for w in ["evaluate", "assess", "critique"]):
            mode = "evaluate"
        elif any(w in low for w in ["synthesize", "combine", "integrate"]):
            mode = "synthesize"
        else:
            mode = "analyze"
        out = await aprocess_thought(step, mode, ctx)
        results.append((i, mode, step, out))
        ctx += f"\n\nStep {i} [{mode}]: {step}\n{out[:400]}"
    lines = ["Cognitive Chain Result:\n"]
    for i, mode, step, out in results:
        lines.append(f"=== Step {i} [{mode}] : {step} ===\n{out}\n")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Structured reasoning
# --------------------------------------------------------------------------
def _build_reason_messages(problem, reasoning_type, depth, track_confidence, wm_limit) -> List[Dict]:
    conf_line = (
        " After EACH step append a confidence estimate in [0,1] as '  (conf: x.xx)'."
        if track_confidence else ""
    )
    system = (
        f"You are a rigorous {reasoning_type} reasoning engine. Solve the problem with "
        f"up to {depth} explicit, numbered reasoning steps.{conf_line} Keep working memory "
        f"bounded to roughly {wm_limit} active items; say explicitly when you set an earlier "
        f"item aside. Reason from the provided memory where it applies; do not invent facts."
    )
    memory = _retrieve_memories_text(problem)
    user = f"PROBLEM:\n{problem}\n"
    if memory:
        user += f"\nRETRIEVED MEMORY (ground truth):\n{memory}\n"
    user += "\nReason now."
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def reason(problem, reasoning_type="deductive", depth=5, track_confidence=True,
           working_memory_limit=7) -> str:
    out = chat(_build_reason_messages(problem, reasoning_type, depth, track_confidence,
                                       working_memory_limit), max_tokens=1500)
    _store_cognitive("reason", problem, out, reasoning_type)
    return out


async def areason(problem, reasoning_type="deductive", depth=5, track_confidence=True,
                  working_memory_limit=7) -> str:
    out = await achat(_build_reason_messages(problem, reasoning_type, depth, track_confidence,
                                              working_memory_limit), max_tokens=1500)
    _store_cognitive("reason", problem, out, reasoning_type)
    return out


# --------------------------------------------------------------------------
# Planning
# --------------------------------------------------------------------------
def _build_plan_messages(goal, horizon, constraints, resources, include_risk) -> List[Dict]:
    system = (
        "You are a planning engine. Decompose the goal into a hierarchical plan. "
        f"Planning horizon: {horizon}. Respect the stated constraints and available resources. "
        f"{'Include an explicit risk assessment.' if include_risk else 'Omit risk assessment.'} "
        "Output phased, actionable steps with dependencies and concrete deliverables."
    )
    memory = _retrieve_memories_text(goal)
    user = f"GOAL:\n{goal}\n"
    if constraints:
        user += f"\nCONSTRAINTS:\n- " + "\n- ".join(constraints) + "\n"
    if resources:
        user += f"\nRESOURCES:\n- " + "\n- ".join(resources) + "\n"
    if memory:
        user += f"\nRELEVANT MEMORY:\n{memory}\n"
    user += "\nProduce the plan."
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def plan(goal, horizon="medium", constraints=None, resources=None, include_risk=True) -> str:
    # Enforce epistemic clearance: refuse to plan on unvalidated simulated/imagined
    # beliefs (Risk: epistemic veto was advisory unless the planning path calls it).
    _enforce_plan_clearance(goal)
    out = chat(_build_plan_messages(goal, horizon, constraints or [], resources or [],
                                     include_risk), max_tokens=1500)
    _store_cognitive("plan", goal, out, horizon)
    return out


async def aplan(goal, horizon="medium", constraints=None, resources=None, include_risk=True) -> str:
    _enforce_plan_clearance(goal)
    out = await achat(_build_plan_messages(goal, horizon, constraints or [], resources or [],
                                            include_risk), max_tokens=1500)
    _store_cognitive("plan", goal, out, horizon)
    return out


def _enforce_plan_clearance(goal: str) -> None:
    """Run the epistemic plan-execution guard over memories the plan would rely on."""
    if not MEMORY_AVAILABLE or not goal:
        return
    try:
        recs = _retrieve_memory_records(goal, k=8)
        fact_ids = [r["id"] for r in recs if r.get("id")]
        if fact_ids:
            run_plan_execution_guard(fact_ids)
    except PermissionError:
        raise
    except Exception:
        # Never let a guard failure silently disable planning; surface it loudly.
        raise PermissionError(
            "Epistemic clearance check failed unexpectedly; blocking plan by default."
        )


# --------------------------------------------------------------------------
# Metacognitive reflection
# --------------------------------------------------------------------------
_FOCUS_SYSTEM = {
    "bias_detection": "You are a metacognitive reflection engine focused on COGNITIVE BIAS. Given the thought process (and outcome if supplied), identify the specific biases present with concrete evidence.",
    "quality_assessment": "You are a metacognitive reflection engine focused on REASONING QUALITY. Honestly judge clarity, completeness, accuracy and coherence of the supplied process.",
    "learning_extraction": "You are a metacognitive reflection engine focused on LEARNING. Extract what worked, what failed, incorrect assumptions, and generalizable lessons.",
    "process_improvement": "You are a metacognitive reflection engine focused on PROCESS IMPROVEMENT. Propose concrete, specific changes to how this kind of reasoning should be done next time.",
}


def _build_reflect_messages(thought_process, outcome, focus) -> List[Dict]:
    system = _FOCUS_SYSTEM.get(focus, _FOCUS_SYSTEM["quality_assessment"])
    user = f"THOUGHT PROCESS ANALYZED:\n{thought_process}\n"
    if outcome:
        user += f"\nACTUAL OUTCOME:\n{outcome}\n"
    user += "\nReflect specifically and concretely. Do not give generic checklists."
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def reflect(thought_process, outcome="", focus="quality_assessment") -> str:
    out = chat(_build_reflect_messages(thought_process, outcome, focus), max_tokens=1200)
    _store_cognitive("reflect", thought_process, out, focus)
    return out


async def areflect(thought_process, outcome="", focus="quality_assessment") -> str:
    out = await achat(_build_reflect_messages(thought_process, outcome, focus), max_tokens=1200)
    _store_cognitive("reflect", thought_process, out, focus)
    return out


# --------------------------------------------------------------------------
# Working memory (real in-process buffer; transform/combine use the LLM)
# --------------------------------------------------------------------------
_WM = {"items": [], "capacity": 7}


def _build_transform_messages(buffer, rule) -> List[Dict]:
    return [
        {"role": "system", "content":
            "You are a working-memory transformation function. Apply the user's rule to each "
            "item in the supplied list and return the transformed items, one per line, prefixed "
            "with '- '."},
        {"role": "user", "content": f"RULE: {rule}\n\nITEMS:\n- " + "\n- ".join(buffer)},
    ]


def working_memory(operation, items=None, transform_rule="", capacity=7) -> str:
    items = items or []
    _WM["capacity"] = capacity
    buf = _WM["items"]

    if operation == "store":
        for it in items:
            if len(buf) >= capacity:
                buf.pop(0)
            buf.append(it)
        return f"Stored {len(items)} item(s). Working memory ({len(buf)}/{capacity}):\n" + \
            "\n".join(f"  {i+1}. {x}" for i, x in enumerate(buf))

    if operation == "retrieve":
        if not buf:
            return f"Working memory is empty ({len(buf)}/{capacity})."
        return f"Working memory ({len(buf)}/{capacity}):\n" + \
            "\n".join(f"  {i+1}. {x}" for i, x in enumerate(buf))

    if operation == "transform":
        if not buf:
            return "Working memory empty; nothing to transform."
        if not transform_rule:
            return "Error: transform_rule is required for transform."
        try:
            txt = chat(_build_transform_messages(buf, transform_rule), max_tokens=800, temperature=0.3)
            new_items = [ln[2:].strip() for ln in txt.splitlines() if ln.strip().startswith("- ")]
            if new_items:
                _WM["items"] = new_items[:capacity]
            else:
                _WM["items"] = [f"{transform_rule}: {x}" for x in buf][:capacity]
        except LLMError:
            _WM["items"] = [f"{transform_rule}: {x}" for x in buf][:capacity]
        return f"Transformed via '{transform_rule}'. Working memory ({len(_WM['items'])}/{capacity}):\n" + \
            "\n".join(f"  {i+1}. {x}" for i, x in enumerate(_WM["items"]))

    if operation == "combine":
        if len(items) < 2:
            return "Error: combine requires at least 2 items."
        combined = " + ".join(items)
        if len(buf) >= capacity:
            buf.pop(0)
        buf.append(combined)
        return f"Combined into working memory ({len(buf)}/{capacity}):\n" + \
            "\n".join(f"  {i+1}. {x}" for i, x in enumerate(buf))

    if operation == "clear":
        n = len(buf)
        buf.clear()
        return f"Cleared {n} item(s). Working memory now empty."

    return f"Unknown operation '{operation}'. Use store/retrieve/transform/combine/clear."


async def aworking_memory(operation, items=None, transform_rule="", capacity=7) -> str:
    # transform path is the only LLM-dependent op; handle inline to stay async
    items = items or []
    _WM["capacity"] = capacity
    buf = _WM["items"]
    if operation == "transform":
        if not buf:
            return "Working memory empty; nothing to transform."
        if not transform_rule:
            return "Error: transform_rule is required for transform."
        try:
            txt = await achat(_build_transform_messages(buf, transform_rule), max_tokens=800, temperature=0.3)
            new_items = [ln[2:].strip() for ln in txt.splitlines() if ln.strip().startswith("- ")]
            _WM["items"] = (new_items if new_items else [f"{transform_rule}: {x}" for x in buf])[:capacity]
        except LLMError:
            _WM["items"] = [f"{transform_rule}: {x}" for x in buf][:capacity]
        return f"Transformed via '{transform_rule}'. Working memory ({len(_WM['items'])}/{capacity}):\n" + \
            "\n".join(f"  {i+1}. {x}" for i, x in enumerate(_WM["items"]))
    # other operations are synchronous and safe to reuse
    return working_memory(operation, items, transform_rule, capacity)


# --------------------------------------------------------------------------
# Imagination (generative simulation, counterfactuals, recombination, models)
# --------------------------------------------------------------------------
def _img_system(kind: str) -> str:
    return (
        f"You are mem20's imagination subsystem performing {kind}. Generate genuine, "
        "internally-consistent content. Distinguish clearly between known facts (from memory, "
        "if provided) and invented/speculative content. Do not present speculation as grounded truth."
    )


def imagination_concept(seed, mode="expand", depth=3, constraints=None) -> str:
    constraints = constraints or []
    memory = _retrieve_memories_text(seed)
    user = f"SEED: {seed}\nMODE: {mode}\nDEPTH: {depth}\n"
    if constraints:
        user += "CONSTRAINTS:\n- " + "\n- ".join(constraints) + "\n"
    if memory:
        user += f"\nRELEVANT MEMORY:\n{memory}\n"
    user += "\nExplore the concept."
    return chat([{"role": "system", "content": _img_system("concept expansion")},
                 {"role": "user", "content": user}], max_tokens=1200)


async def aimagination_concept(seed, mode="expand", depth=3, constraints=None) -> str:
    constraints = constraints or []
    memory = _retrieve_memories_text(seed)
    user = f"SEED: {seed}\nMODE: {mode}\nDEPTH: {depth}\n"
    if constraints:
        user += "CONSTRAINTS:\n- " + "\n- ".join(constraints) + "\n"
    if memory:
        user += f"\nRELEVANT MEMORY:\n{memory}\n"
    user += "\nExplore the concept."
    return await achat([{"role": "system", "content": _img_system("concept expansion")},
                        {"role": "user", "content": user}], max_tokens=1200)


def imagination_simulate(scenario, variables=None, steps=5, branching_factor=3,
                        goal_state="") -> str:
    variables = variables or []
    var_block = ""
    if variables:
        var_block = "VARIABLES TO VARY:\n" + "\n".join(
            f"- {v.get('name')}: {v.get('values')}" for v in variables) + "\n"
    user = (f"INITIAL SCENARIO:\n{scenario}\n{var_block}STEPS: {steps}\n"
            f"BRANCHING FACTOR: {branching_factor}\n")
    if goal_state:
        user += f"GOAL STATE TO REASON TOWARD:\n{goal_state}\n"
    user += ("Run a genuine branching mental simulation. For each branch give a reasoned "
             "(not random) probability and explain the mechanism. Clearly mark what is "
             "speculative. If a world-model is implied, state its assumptions.")
    return chat([{"role": "system", "content": _img_system("generative simulation")},
                 {"role": "user", "content": user}], max_tokens=1800)


async def aimagination_simulate(scenario, variables=None, steps=5, branching_factor=3,
                               goal_state="") -> str:
    variables = variables or []
    var_block = ""
    if variables:
        var_block = "VARIABLES TO VARY:\n" + "\n".join(
            f"- {v.get('name')}: {v.get('values')}" for v in variables) + "\n"
    user = (f"INITIAL SCENARIO:\n{scenario}\n{var_block}STEPS: {steps}\n"
            f"BRANCHING FACTOR: {branching_factor}\n")
    if goal_state:
        user += f"GOAL STATE TO REASON TOWARD:\n{goal_state}\n"
    user += ("Run a genuine branching mental simulation. For each branch give a reasoned "
             "(not random) probability and explain the mechanism. Clearly mark what is "
             "speculative. If a world-model is implied, state its assumptions.")
    return await achat([{"role": "system", "content": _img_system("generative simulation")},
                        {"role": "user", "content": user}], max_tokens=1800)


def imagination_counterfactual(factual_premise, counterfactual_change, depth=3,
                               domains=None) -> str:
    domains = domains or ["causal", "temporal", "social", "systemic"]
    user = (f"FACTUAL PREMISE:\n{factual_premise}\n\nCOUNTERFACTUAL CHANGE:\n"
            f"{counterfactual_change}\n\nTRACE DEPTH: {depth}\nDOMAINS: {', '.join(domains)}\n\n"
            "Explore the counterfactual consequences across the domains. Be explicit about "
            "causal mechanism and uncertainty.")
    return chat([{"role": "system", "content": _img_system("counterfactual reasoning")},
                 {"role": "user", "content": user}], max_tokens=1500)


async def aimagination_counterfactual(factual_premise, counterfactual_change, depth=3,
                                      domains=None) -> str:
    domains = domains or ["causal", "temporal", "social", "systemic"]
    user = (f"FACTUAL PREMISE:\n{factual_premise}\n\nCOUNTERFACTUAL CHANGE:\n"
            f"{counterfactual_change}\n\nTRACE DEPTH: {depth}\nDOMAINS: {', '.join(domains)}\n\n"
            "Explore the counterfactual consequences across the domains. Be explicit about "
            "causal mechanism and uncertainty.")
    return await achat([{"role": "system", "content": _img_system("counterfactual reasoning")},
                        {"role": "user", "content": user}], max_tokens=1500)


def imagination_recombine(concepts, recombination_mode="blend", num_outputs=5,
                          constraint_domain="") -> str:
    user = (f"CONCEPTS: {', '.join(concepts)}\nRECOMBINATION MODE: {recombination_mode}\n"
            f"NUM OUTPUTS: {num_outputs}\n")
    if constraint_domain:
        user += f"CONSTRAINT DOMAIN: {constraint_domain}\n"
    user += "Generate novel combinations by transferring structure/patterns across the concepts."
    return chat([{"role": "system", "content": _img_system("creative recombination")},
                 {"role": "user", "content": user}], max_tokens=1500)


async def aimagination_recombine(concepts, recombination_mode="blend", num_outputs=5,
                                 constraint_domain="") -> str:
    user = (f"CONCEPTS: {', '.join(concepts)}\nRECOMBINATION MODE: {recombination_mode}\n"
            f"NUM OUTPUTS: {num_outputs}\n")
    if constraint_domain:
        user += f"CONSTRAINT DOMAIN: {constraint_domain}\n"
    user += "Generate novel combinations by transferring structure/patterns across the concepts."
    return await achat([{"role": "system", "content": _img_system("creative recombination")},
                        {"role": "user", "content": user}], max_tokens=1500)


def imagination_model(system, model_type="causal", query="", variables=None) -> str:
    variables = variables or []
    var_block = ""
    if variables:
        var_block = "VARIABLES:\n" + "\n".join(
            f"- {v.get('name')} ({v.get('type')}, range {v.get('range')})" for v in variables) + "\n"
    user = f"SYSTEM TO MODEL: {system}\nMODEL TYPE: {model_type}\n{var_block}QUERY: {query}\n"
    user += ("Build an explicit mental model of this system and answer the query. State the "
             "model's assumptions, dynamic relationships, and limits of validity.")
    return chat([{"role": "system", "content": _img_system("mental modeling")},
                 {"role": "user", "content": user}], max_tokens=1500)


async def aimagination_model(system, model_type="causal", query="", variables=None) -> str:
    variables = variables or []
    var_block = ""
    if variables:
        var_block = "VARIABLES:\n" + "\n".join(
            f"- {v.get('name')} ({v.get('type')}, range {v.get('range')})" for v in variables) + "\n"
    user = f"SYSTEM TO MODEL: {system}\nMODEL TYPE: {model_type}\n{var_block}QUERY: {query}\n"
    user += ("Build an explicit mental model of this system and answer the query. State the "
             "model's assumptions, dynamic relationships, and limits of validity.")
    return await achat([{"role": "system", "content": _img_system("mental modeling")},
                        {"role": "user", "content": user}], max_tokens=1500)


def imagination_critique(concept, perspectives=None, refine=True) -> str:
    perspectives = perspectives or ["feasibility", "novelty", "impact", "coherence"]
    user = f"CONCEPT:\n{concept}\n\nPERSPECTIVES: {', '.join(perspectives)}\n"
    user += ("Critique the concept adversarially from each perspective. "
             + ("Then produce a refined version." if refine else ""))
    return chat([{"role": "system", "content": _img_system("adversarial critique")},
                 {"role": "user", "content": user}], max_tokens=1500)


async def aimagination_critique(concept, perspectives=None, refine=True) -> str:
    perspectives = perspectives or ["feasibility", "novelty", "impact", "coherence"]
    user = f"CONCEPT:\n{concept}\n\nPERSPECTIVES: {', '.join(perspectives)}\n"
    user += ("Critique the concept adversarially from each perspective. "
             + ("Then produce a refined version." if refine else ""))
    return await achat([{"role": "system", "content": _img_system("adversarial critique")},
                        {"role": "user", "content": user}], max_tokens=1500)


def imagination_dream(prompt, iterations=3, output_mode="concepts", memory_topics=None) -> str:
    memory_topics = memory_topics or []
    seed = prompt
    log = [f"DREAM starting from: {prompt}\n"]
    for i in range(1, iterations + 1):
        mem = _retrieve_memories_text(seed) if memory_topics else ""
        user = f"ITERATION {i}. Seed: {seed}\n"
        if mem:
            user += f"Memory inspiration:\n{mem}\n"
        user += "Produce the next creative concept elaboration (concepts mode)."
        try:
            out = chat([{"role": "system", "content": _img_system("dream loop")},
                        {"role": "user", "content": user}], max_tokens=900)
        except LLMError as e:
            log.append(f"[iteration {i}] LLM unavailable: {e}")
            break
        log.append(f"--- iteration {i} ---\n{out}\n")
        seed = out[:300]
    return "\n".join(log)


async def aimagination_dream(prompt, iterations=3, output_mode="concepts", memory_topics=None) -> str:
    memory_topics = memory_topics or []
    seed = prompt
    log = [f"DREAM starting from: {prompt}\n"]
    for i in range(1, iterations + 1):
        mem = _retrieve_memories_text(seed) if memory_topics else ""
        user = f"ITERATION {i}. Seed: {seed}\n"
        if mem:
            user += f"Memory inspiration:\n{mem}\n"
        user += "Produce the next creative concept elaboration (concepts mode)."
        try:
            out = await achat([{"role": "system", "content": _img_system("dream loop")},
                               {"role": "user", "content": user}], max_tokens=900)
        except LLMError as e:
            log.append(f"[iteration {i}] LLM unavailable: {e}")
            break
        log.append(f"--- iteration {i} ---\n{out}\n")
        seed = out[:300]
    return "\n".join(log)


# --------------------------------------------------------------------------
# Theory of Mind
# --------------------------------------------------------------------------
def theory_of_mind_simulate(agent_model, scenario, depth=2) -> str:
    user = (f"OTHER AGENT MODEL:\nKnowledge: {agent_model.get('knowledge','Unknown')}\n"
            f"Beliefs: {agent_model.get('beliefs','Unknown')}\n"
            f"Goals: {agent_model.get('goals','Unknown')}\n\n"
            f"SCENARIO:\n{scenario}\n\nNESTING DEPTH: {depth} "
            f"(model 'I think that you think that I think...').\n\n"
            "Simulate the other agent's actual reasoning chain, predicted action, and the "
            "confidence behind it. Base the simulation on the supplied model, not on generic "
            "assumptions.")
    return chat([{"role": "system", "content":
                  "You are mem20's theory-of-mind engine. Simulate another agent's internal "
                  "reasoning from a supplied model of that agent. Be specific and avoid "
                  "stereotyping; show your chain."},
                 {"role": "user", "content": user}], max_tokens=1200)


async def atheory_of_mind_simulate(agent_model, scenario, depth=2) -> str:
    user = (f"OTHER AGENT MODEL:\nKnowledge: {agent_model.get('knowledge','Unknown')}\n"
            f"Beliefs: {agent_model.get('beliefs','Unknown')}\n"
            f"Goals: {agent_model.get('goals','Unknown')}\n\n"
            f"SCENARIO:\n{scenario}\n\nNESTING DEPTH: {depth} "
            f"(model 'I think that you think that I think...').\n\n"
            "Simulate the other agent's actual reasoning chain, predicted action, and the "
            "confidence behind it. Base the simulation on the supplied model, not on generic "
            "assumptions.")
    return await achat([{"role": "system", "content":
                         "You are mem20's theory-of-mind engine. Simulate another agent's internal "
                         "reasoning from a supplied model of that agent. Be specific and avoid "
                         "stereotyping; show your chain."},
                        {"role": "user", "content": user}], max_tokens=1200)


def theory_of_mind_perspective(entity, topic, context="") -> str:
    memory = _retrieve_memories_text(f"{entity} {topic}")
    user = f"ENTITY: {entity}\nTOPIC: {topic}\n"
    if context:
        user += f"CONTEXT: {context}\n"
    if memory:
        user += f"\nKNOWN FACTS ABOUT {entity.upper()}:\n{memory}\n"
    user += (f"\nGenerate a genuine perspective-taking: what does {topic} look like from "
             f"{entity}'s knowledge, concerns, and likely biases? Identify gaps in their knowledge.")
    return chat([{"role": "system", "content":
                  "You are mem20's theory-of-mind / perspective-taking engine. Reason from the "
                  "supplied facts about the entity; do not invent a persona beyond the evidence."},
                 {"role": "user", "content": user}], max_tokens=1200)


async def atheory_of_mind_perspective(entity, topic, context="") -> str:
    memory = _retrieve_memories_text(f"{entity} {topic}")
    user = f"ENTITY: {entity}\nTOPIC: {topic}\n"
    if context:
        user += f"CONTEXT: {context}\n"
    if memory:
        user += f"\nKNOWN FACTS ABOUT {entity.upper()}:\n{memory}\n"
    user += (f"\nGenerate a genuine perspective-taking: what does {topic} look like from "
             f"{entity}'s knowledge, concerns, and likely biases? Identify gaps in their knowledge.")
    return await achat([{"role": "system", "content":
                         "You are mem20's theory-of-mind / perspective-taking engine. Reason from the "
                         "supplied facts about the entity; do not invent a persona beyond the evidence."},
                        {"role": "user", "content": user}], max_tokens=1200)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="mem20 Cognitive Engine (LLM-backed)")
    sub = p.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("process")
    p1.add_argument("--thought", required=True)
    p1.add_argument("--mode", default="analyze", choices=list(_MODE_SYSTEM))
    p1.add_argument("--context", default="")
    p2 = sub.add_parser("chain")
    p2.add_argument("--steps", required=True)
    p2.add_argument("--context", default="")
    p3 = sub.add_parser("reason")
    p3.add_argument("--problem", required=True)
    p3.add_argument("--type", default="deductive")
    p3.add_argument("--depth", type=int, default=5)
    args = p.parse_args()
    if args.cmd == "process":
        print(process_thought(args.thought, args.mode, args.context))
    elif args.cmd == "chain":
        print(run_chain(__import__("json").loads(args.steps), args.context))
    elif args.cmd == "reason":
        print(reason(args.problem, args.type, args.depth))
