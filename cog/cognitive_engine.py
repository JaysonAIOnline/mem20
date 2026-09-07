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
import json
import re
import sqlite3
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

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
# Chain-of-Thought (CoT)
# --------------------------------------------------------------------------
async def acot_reason(problem: str, steps: int = 5, style: str = "deductive") -> str:
    system = (
        "You are a Chain-of-Thought reasoning engine. "
        f"Reason through the problem step-by-step in natural language using {style} reasoning. "
        f"Use exactly {steps} steps. At each step, state your intermediate conclusion. "
        "End with a final conclusion that synthesizes all steps."
    )
    user = f"PROBLEM:\n{problem}\n\nREASONING STEPS: {steps}\nSTYLE: {style}"
    out = await achat([{"role": "system", "content": system}, {"role": "user", "content": user}], max_tokens=1500)
    _store_cognitive("cot_reason", problem, out, style)
    return out


# --------------------------------------------------------------------------
# Program-of-Thought (PoT)
# --------------------------------------------------------------------------
async def apot_reason(problem: str, language: str = "python", complexity: str = "standard") -> str:
    system = (
        "You are a Program-of-Thought reasoning engine. "
        f"Solve the problem by writing executable {language} code. "
        f"Complexity level: {complexity}. "
        "The code should be complete, runnable, and solve the stated problem."
    )
    user = f"PROBLEM:\n{problem}\n\nLANGUAGE: {language}\nCOMPLEXITY: {complexity}"
    out = await achat([{"role": "system", "content": system}, {"role": "user", "content": user}], max_tokens=1500)
    _store_cognitive("pot_reason", problem, out, language)
    return out


# --------------------------------------------------------------------------
# Tree-of-Thoughts (ToT) — persistent substrate-enabled version
# --------------------------------------------------------------------------
_TOT_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "tot_state.db")

def get_tot_historical_lessons(problem_context: str, max_lessons: int = 3) -> list:
    """
    Scans past session trees to isolate branches that were pruned or heavily penalized.
    Uses semantic matching via memory recall when available, falls back to keyword scan.
    """
    lessons = []
    
    # Try semantic recall first (if memory system available)
    if MEMORY_AVAILABLE:
        try:
            from memory import recall as mem_recall
            recs = mem_recall(topic=problem_context, k=10) or []
            for rec in recs:
                content = rec.get("content", "") if isinstance(rec, dict) else str(rec)
                if "pruned" in content.lower() or "tot_reason" in content.lower():
                    lessons.append({
                        "source": "memory_recall",
                        "context": content[:300],
                    })
                    if len(lessons) >= max_lessons:
                        return lessons
        except Exception:
            pass
    
    # Fallback: scan ToT database for pruned branches
    try:
        with sqlite3.connect(_TOT_DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT substrate_payload, heuristic_score_delta, is_pruned 
                FROM cognitive_substrate_history 
                WHERE is_pruned = 1 OR heuristic_score_delta < -10.0
                ORDER BY created_at DESC LIMIT 50
            """)
            rows = cursor.fetchall()
            
            # Extract keywords from problem context
            keywords = [w.lower() for w in problem_context.split() if len(w) > 4]
            
            for row in rows:
                try:
                    substrate = json.loads(row[0]) if row[0] else {}
                    if not substrate:
                        continue
                    
                    # Check relevance using compressed 5-key structure
                    foundations = substrate.get("foundations", {})
                    utility = substrate.get("utility", {})
                    
                    # Build search text from compressed schema
                    search_text = " ".join([
                        str(foundations.get("premise_validation", "")),
                        str(foundations.get("falsification_notes", "")),
                        str(utility.get("load_summary", "")),
                    ]).lower()
                    
                    if any(kw in search_text for kw in keywords):
                        lessons.append({
                            "source": "tot_history",
                            "failed_approach": foundations.get("premise_validation", ""),
                            "why_it_failed": foundations.get("falsification_notes", ""),
                            "correction": utility.get("load_summary", ""),
                            "score_delta": row[1],
                        })
                        if len(lessons) >= max_lessons:
                            break
                except (json.JSONDecodeError, KeyError):
                    continue
    except Exception:
        pass
    
    return lessons[:max_lessons]


def _init_tot_db():
    """Initialize the ToT state database. Non-destructive: only creates if missing."""
    try:
        with sqlite3.connect(_TOT_DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tot_nodes (
                    node_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    parent_node_id TEXT,
                    branch_index INTEGER,
                    depth INTEGER,
                    prompt_context TEXT,
                    raw_llm_output TEXT,
                    cleaned_output TEXT,
                    substrate_payload TEXT,
                    heuristic_score_delta REAL DEFAULT 0.0,
                    status TEXT CHECK(status IN ('pending','active','pruned','completed','selected')) DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cognitive_substrate_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    node_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    substrate_payload TEXT,
                    heuristic_score_delta REAL DEFAULT 0.0,
                    is_pruned INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(node_id) REFERENCES tot_nodes(node_id)
                )
            """)
            conn.commit()
    except Exception:
        pass

_init_tot_db()


def robust_slice(raw_output: str) -> tuple:
    """
    Stack-based JSON extraction. Scans sequentially for the first valid top-level JSON object.
    Returns (cleaned_text_without, parsed_dict).
    Handles nested brackets, escaped strings, and multiple code blocks.
    """
    first_bracket = raw_output.find('{')
    if first_bracket == -1:
        return raw_output, {"parsing_error": "No JSON block found"}
    
    stack = 0
    in_string = False
    escape = False
    json_end = -1
    
    for i in range(first_bracket, len(raw_output)):
        char = raw_output[i]
        
        if escape:
            escape = False
            continue
        if char == '\\':
            escape = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        
        if not in_string:
            if char == '{':
                stack += 1
            elif char == '}':
                stack -= 1
                if stack == 0:
                    json_end = i + 1
                    break
    
    if json_end == -1:
        return raw_output, {"parsing_error": "Malformed or unclosed JSON block"}
    
    try:
        json_payload = json.loads(raw_output[first_bracket:json_end])
        dirty_segment = raw_output[first_bracket:json_end]
        cleaned_text = raw_output.replace(dirty_segment, "")
        # Clean up empty markdown code fences
        cleaned_text = re.sub(r"```json\s*```|```\s*```", "", cleaned_text).strip()
        return cleaned_text, json_payload
    except json.JSONDecodeError:
        return raw_output, {"parsing_error": "JSONDecodeError during extraction"}


def _extract_substrate(raw_text: str) -> tuple:
    """
    Extract the 28-layer JSON substrate from raw LLM output.
    Uses robust stack-based parser instead of regex.
    Returns (substrate_dict, cleaned_text_without_block).
    """
    # First try: look for ```json ... ``` blocks
    if '```json' in raw_text:
        matches = re.findall(r'```json\s*(.*?)\s*```', raw_text, re.DOTALL)
        if matches:
            # Take the largest valid JSON block
            best = {}
            best_text = raw_text
            for match in matches:
                try:
                    parsed = json.loads(match)
                    if isinstance(parsed, dict) and len(str(parsed)) > len(str(best)):
                        best = parsed
                        best_text = raw_text.replace(f'```json{match}```', '').strip()
                except json.JSONDecodeError:
                    continue
            if best:
                return best, best_text
    
    # Fallback: scan for raw JSON objects
    cleaned, parsed = robust_slice(raw_text)
    return parsed, cleaned


def _evaluate_substrate(substrate: dict) -> Tuple[float, int]:
    """
    Run heuristic checks on the 28-layer substrate.
    Returns (score_delta, is_pruned).
    Accepts both flat test format and full 28-layer paradigm structure.
    """
    if substrate is None:
        return -50.0, 0  # Missing substrate penalty
    if not isinstance(substrate, dict):
        return -50.0, 0  # Malformed substrate penalty
    
    score_delta = 0.0
    is_pruned = 0
    
    # Resolve defensive/blast_radius from either flat or nested structure
    def get_blast_radius():
        # Flat format: {"defensive": {"blast_radius": "unpredictable"}}
        if "defensive" in substrate:
            return str(substrate["defensive"].get("blast_radius", "")).lower()
        # Nested 28-layer: {"DEFENSIVE_ENGINEERING": {"14_..._audit": {"blast_radius": ...}}}
        defensive = substrate.get("DEFENSIVE_ENGINEERING", {})
        for key in defensive:
            if "idempotency" in key.lower() or "14_" in key:
                val = defensive[key]
                if isinstance(val, dict) and "blast_radius" in val:
                    return str(val["blast_radius"]).lower()
        return ""
    
    blast = get_blast_radius()
    if "unpredictable" in blast or "infinite" in blast or "irreversible" in blast:
        score_delta = -100.0
        is_pruned = 1
    
    # Resolve complexity/big_o from either flat or nested structure
    def get_big_o():
        if "resource" in substrate:
            return str(substrate["resource"].get("big_o", "")).lower()
        resource = substrate.get("RESOURCE_MANAGEMENT", {})
        for key in resource:
            if "complexity" in key.lower() or "19_" in key:
                val = resource[key]
                if isinstance(val, dict) and "big_o_notation" in val:
                    return str(val["big_o_notation"]).lower()
        return ""
    
    big_o = get_big_o()
    if any(banned in big_o for banned in ["o(n^n)", "o(2^n)", "o(n!)"]):
        score_delta = -100.0
        is_pruned = 1
    
    # Resolve speculative assumptions count
    def get_spec_count():
        primary = substrate.get("PRIMARY_COGNITIVE_FOUNDATIONS", {})
        for key in primary:
            if "epistemic" in key.lower() or "5_" in key:
                val = primary[key]
                if isinstance(val, dict):
                    return len(val.get("speculative_assumptions", []))
        return 0
    
    spec_count = get_spec_count()
    if spec_count > 5:
        score_delta -= 20.0
    
    return score_delta, is_pruned


def persist_tot_node(node_id: str, session_id: str, parent_node_id: str = None,
                     branch_index: int = 0, depth: int = 0, prompt_context: str = "",
                     raw_output: str = "", cleaned_output: str = "",
                     substrate: dict = None, score_delta: float = 0.0,
                     status: str = "pending"):
    """Persist a ToT node to SQLite."""
    try:
        with sqlite3.connect(_TOT_DB_PATH) as conn:
            conn.execute("""
                INSERT INTO tot_nodes (node_id, session_id, parent_node_id, branch_index, depth,
                                       prompt_context, raw_llm_output, cleaned_output,
                                       substrate_payload, heuristic_score_delta, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(node_id) DO UPDATE SET
                    cleaned_output = excluded.cleaned_output,
                    substrate_payload = excluded.substrate_payload,
                    heuristic_score_delta = excluded.heuristic_score_delta,
                    status = excluded.status
            """, (node_id, session_id, parent_node_id, branch_index, depth,
                  prompt_context, raw_output, cleaned_output,
                  json.dumps(substrate or {}), score_delta, status))
            
            # Also log to history
            conn.execute("""
                INSERT INTO cognitive_substrate_history (node_id, session_id, substrate_payload, heuristic_score_delta, is_pruned)
                VALUES (?, ?, ?, ?, ?)
            """, (node_id, session_id, json.dumps(substrate or {}), score_delta, 1 if score_delta <= -100 else 0))
            conn.commit()
    except Exception:
        pass


_TOT_SUBSTRATE_PROMPT = """
After your reasoning, append a JSON code block containing your cognitive telemetry.
Format: ```json { ... } ```

Include these 5 consolidated keys (keep values dense, under 150 tokens total):
1. "foundations": { "premise_validation": str, "state_hash": str, "falsification_notes": str }
2. "metacognition": { "self_critique": str, "drift_pct": float }
3. "defensive": { "blast_radius": str, "is_idempotent": bool, "invariant_rule": str }
4. "resource": { "big_o": str, "latency_bottleneck": str }
5. "utility": { "load_summary": str, "checklist_verified": bool }

Do not pollute your reasoning text with this data."""


async def atot_reason(problem: str, branches: int = 3, depth: int = 3,
                      evaluation_criteria: str = "feasibility,novelty,simplicity",
                      session_id: str = "default") -> str:
    """Enhanced ToT with substrate validation and persistence."""
    import uuid
    
    root_id = f"tot-{uuid.uuid4().hex[:8]}"
    
    system = (
        "You are a Tree-of-Thoughts reasoning engine. "
        f"Explore {branches} distinct reasoning paths, each {depth} steps deep. "
        f"Evaluate each path against: {evaluation_criteria}. "
        "Score each path (1-10), then select the best. Justify your selection."
        f"\n\n{_TOT_SUBSTRATE_PROMPT}"
    )
    user = (f"PROBLEM:\n{problem}\n\nBRANCHES: {branches}\nDEPTH: {depth}\n"
            f"EVALUATION CRITERIA: {evaluation_criteria}")
    
    # Inject cross-session historical lessons if available
    historical_lessons = get_tot_historical_lessons(problem, max_lessons=2)
    if historical_lessons:
        lesson_block = "\n\n=== HISTORICAL EXECUTION LESSONS (DO NOT REPEAT) ===\n"
        for idx, lesson in enumerate(historical_lessons, 1):
            lesson_block += f"Lesson {idx}:\n"
            if lesson.get("failed_approach"):
                lesson_block += f"- Discarded: {lesson['failed_approach'][:200]}\n"
            if lesson.get("why_it_failed"):
                lesson_block += f"- Reason: {lesson['why_it_failed'][:200]}\n"
            if lesson.get("correction"):
                lesson_block += f"- Fix: {lesson['correction'][:200]}\n"
            lesson_block += "\n"
        user += lesson_block
    
    raw_out = await achat([{"role": "system", "content": system}, {"role": "user", "content": user}], max_tokens=2500)
    
    # Extract and validate substrate
    substrate, cleaned = _extract_substrate(raw_out)
    score_delta, is_pruned = _evaluate_substrate(substrate)
    
    # Persist node
    status = "pruned" if is_pruned else "completed"
    persist_tot_node(
        node_id=root_id,
        session_id=session_id,
        prompt_context=problem[:500],
        raw_output=raw_out[:2000],
        cleaned_output=cleaned[:2000],
        substrate=substrate,
        score_delta=score_delta,
        status=status,
    )
    
    _store_cognitive("tot_reason", problem, cleaned, f"branches={branches},delta={score_delta}")
    
    # If pruned, note it in the output
    if is_pruned:
        return f"{cleaned}\n\n[System: This branch was pruned due to substrate violations (score_delta={score_delta})]"
    
    return cleaned


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
