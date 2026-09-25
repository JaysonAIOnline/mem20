"""Cognitive brain for mem20crewz agents.

- Brain: protocol. Agent reasoning goes through this so tests can be
  deterministic (FakeBrain) while production runs real cog (CogBrain).
- CogBrain: real path. plan/reason/reflect/tot use the mem20 cog engine;
  propose() uses llm.chat with a strict JSON action contract for the
  tool-callback loop. Uses mem20 llm which RAISES LLMError with no key —
  we NEVER fabricate a completion.
- FakeBrain: scripted, deterministic. Used only in tests / demo-fake.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Optional

from ._substrate import backend as sub


class BrainError(RuntimeError):
    """Raised when the brain cannot produce a valid decision."""


class Brain:
    """Protocol for agent reasoning."""

    name = "brain"

    def plan(self, goal: str, constraints: Optional[list] = None,
             resources: Optional[list] = None) -> str:
        raise NotImplementedError

    def reason(self, problem: str, reasoning_type: str = "deductive",
               depth: int = 5) -> str:
        raise NotImplementedError

    def reflect(self, thought_process: str, outcome: str = "") -> str:
        raise NotImplementedError

    def tot(self, problem: str, branches: int = 3, depth: int = 3) -> str:
        raise NotImplementedError

    def propose(self, goal: str, tools_blob: str,
                observations: list[str],
                require_tool_before_final: bool = False) -> dict:
        """Return one action decision:
        {"action": "tool", "tool": name, "args": ...}
        {"action": "delegate", "capability": ..., "message": ...}
        {"action": "final", "final": output_text}
        """
        raise NotImplementedError


class CogBrain(Brain):
    """Real reasoning over the mem20 cog engine + llm.chat."""

    name = "cog"

    def plan(self, goal: str, constraints: Optional[list] = None,
             resources: Optional[list] = None) -> str:
        return sub.cog.plan(
            goal=goal, horizon="medium",
            constraints=constraints or [], resources=resources or [],
            include_risk=True,
        )

    def reason(self, problem: str, reasoning_type: str = "deductive",
               depth: int = 5) -> str:
        return sub.cog.reason(problem, reasoning_type=reasoning_type, depth=depth)

    def reflect(self, thought_process: str, outcome: str = "") -> str:
        return sub.cog.reflect(thought_process, outcome=outcome)

    def tot(self, problem: str, branches: int = 3, depth: int = 3) -> str:
        # beam_search keeps the top-K reasoning paths open — the ToT-style engine.
        return sub.cog.beam_search(problem, beam_width=branches, depth=depth)

    def propose(self, goal: str, tools_blob: str,
                observations: list[str],
                require_tool_before_final: bool = False) -> dict:
        contract = (
            'You are the reasoning core of an agent. Decide the NEXT action.\n'
            'Reply ONLY with a JSON object, one of three shapes:\n'
            '  {"action": "tool",   "tool": "<name>", "args": "<string arg>"}\n'
            '  {"action": "delegate", "capability": "<capability>", "message": "<task>"}\n'
            '  {"action": "final",  "final": "<your final answer text>"}\n'
            'Choose "final" only when the goal is complete. Never invent tools: '
            'only the tools in the inventory below may be referenced.\n'
            'IMPORTANT: Output the JSON as PLAIN TEXT in the message body. '
            'Do NOT emit a function/tool call and do not wrap the JSON in '
            'code fences. The tool name is a protocol string, not a real '
            'function to invoke.'
        )
        if require_tool_before_final:
            contract += (
                '\nEXIT GUARD ARMED: the loop REJECTS "final" until at least one '
                'tool has run successfully and its output appears in PAST '
                'OBSERVATIONS. As the very first action you MUST pick a "tool" '
                'action from the inventory — do not propose "final" before doing '
                'real work, it will be rejected and you will waste steps.'
            )
        obs_blob = "\n".join(f"[step {i}] {o[:300]}" for i, o in enumerate(observations[-6:]))
        user = (
            f"GOAL:\n{goal}\n\nAVAILABLE TOOLS:\n{tools_blob}\n\n"
            f"PAST OBSERVATIONS:\n{obs_blob}\n\nDecide the next action (strict JSON only)."
        )
        # The action carries the DELIVERABLE inside args for content-producing
        # tools (e.g. write-file with a full asset description). A small cap
        # truncates that JSON mid-string, so every proposal parses as
        # "unknown" and the worker burns all iterations without writing a file.
        # Budget generously and allow env override for larger phases.
        try:
            budget = int(os.environ.get("MEM20CREWZ_PROPOSE_MAX_TOKENS", "4096"))
        except ValueError:
            budget = 4096
        raw = sub.llm.chat([{"role": "system", "content": contract},
                            {"role": "user", "content": user}], max_tokens=budget)
        return _parse_action(raw)


def _parse_action(raw: Optional[str]) -> dict:
    """Tolerant JSON-action parser over an LLM reply.

    Returns one of {"action": "tool"|"delegate"|"final"|"unknown"}. A reply
    that cannot be read as a valid action is NEVER fabricated into "final" —
    it becomes "unknown" so the loop re-proposes (with feedback) instead of
    burning the premature-final guard on throttled/garbled output.
    """
    if not raw:
        return {"action": "unknown", "raw": ""}
    # Try the raw text first: a thinking-wrapped reply may carry the whole
    # JSON action inside the <thinking> section, which stripping would delete.
    for candidate in _json_candidates(raw):
        obj = _candidate_obj(candidate)
        if obj is not None:
            return _action_from_obj(obj, raw)
    text = _strip_thinking(raw)
    for candidate in _json_candidates(text):
        obj = _candidate_obj(candidate)
        if obj is not None:
            return _action_from_obj(obj, text)
    m = re.search(r"\{.*\}", text, re.DOTALL)
    obj = _candidate_obj(m.group(0)) if m else None
    if obj is not None:
        return _action_from_obj(obj, text)
    return {"action": "unknown", "raw": (raw or "").strip()}


def _candidate_obj(candidate: str) -> Optional[dict]:
    try:
        obj = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    if isinstance(obj, dict) and str(obj.get("action") or "").lower() in (
            "tool", "delegate", "final"):
        return obj
    return None


def _strip_thinking(raw: str) -> str:
    """Remove reasoning/thinking sections so only the real answer remains."""
    for left, right in (("<thinking>", "</thinking>"),
                        ("\u003cthinking\u003e", "\u003c/thinking\u003e"),
                        ("[thinking]", "[/thinking]")):
        while True:
            a = raw.find(left)
            b = raw.find(right, a + len(left))
            if a == -1 or b == -1:
                break
            raw = raw[:a] + raw[b + len(right):] if b > a else raw
    return raw


def _json_candidates(text: str) -> list[str]:
    """Non-greedy JSON object candidates from outer to inner braces."""
    out: list[str] = []
    start = 0
    while True:
        a = text.find("{", start)
        if a == -1:
            break
        depth = 0
        for i in range(a, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    out.append(text[a:i + 1])
                    start = i + 1
                    break
        else:
            break
    return out


def _action_from_obj(obj: dict, text: str) -> dict:
    if not isinstance(obj, dict):
        return {"action": "unknown", "raw": text.strip()}
    action = str(obj.get("action") or "").lower()
    if action == "tool":
        tool = obj.get("tool")
        if tool:
            args = obj.get("args", "")
            # Models may return args as a JSON object ({"path","content"})
            # rather than the protocol string. Skills.execute does str(arg),
            # which would turn a dict into a Python repr and corrupt the tool
            # payload; serialize it back to JSON text here so both shapes work.
            if not isinstance(args, str):
                args = json.dumps(args, ensure_ascii=False)
            return {"action": "tool", "tool": str(tool), "args": args}
    if action == "delegate":
        cap = obj.get("capability")
        if cap:
            return {"action": "delegate", "capability": str(cap),
                    "message": str(obj.get("message") or goal_msg(obj))}
    if action in ("tool", "delegate"):
        # explicit *intent* but missing the payload -> not a usable action
        return {"action": "unknown", "raw": text.strip()}
    if action == "final":
        return {"action": "final", "final": str(
            obj.get("final") or obj.get("message") or text.strip())}
    return {"action": "unknown", "raw": text.strip()}


def goal_msg(obj: dict) -> str:
    return str(obj.get("message") or obj.get("final") or "")


class FakeBrain(Brain):
    """Deterministic, scripted brain for tests / offline demo.

    ``steps`` is a list of action dicts consumed one per propose() call; the
    final element is repeated if the loop needs more iterations.
    """

    name = "fake"

    def __init__(self, plan_text: str = "plan", reason_text: str = "reason",
                 reflect_text: str = "reflect", tot_text: str = "tot",
                 steps: Optional[list[dict]] = None) -> None:
        self.plan_text = plan_text
        self.reason_text = reason_text
        self.reflect_text = reflect_text
        self.tot_text = tot_text
        self.steps = steps or [{"action": "final", "final": "done (fake)"}]
        self.propose_calls: list[tuple] = []

    def plan(self, goal: str, constraints: Optional[list] = None,
             resources: Optional[list] = None) -> str:
        return self.plan_text

    def reason(self, problem: str, reasoning_type: str = "deductive",
               depth: int = 5) -> str:
        return self.reason_text

    def reflect(self, thought_process: str, outcome: str = "") -> str:
        return self.reflect_text

    def tot(self, problem: str, branches: int = 3, depth: int = 3) -> str:
        return self.tot_text

    def propose(self, goal: str, tools_blob: str,
                observations: list[str],
                require_tool_before_final: bool = False) -> dict:
        self.propose_calls.append((goal, tools_blob, list(observations)))
        n = min(len(self.propose_calls) - 1, len(self.steps) - 1)
        chosen = dict(self.steps[n])
        if chosen.get("action") == "final" and not chosen.get("final"):
            chosen["final"] = ("done (fake) after %d observations" % len(observations))
        return chosen