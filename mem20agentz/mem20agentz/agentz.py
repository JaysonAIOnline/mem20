"""agentz — the core agent loop (sub-phase 2.2).

A conversational tool-calling loop with the same strict action contract the
cleanroom already uses: the brain proposes one action at a time —
tool / delegate / final — and observations feed back until the goal is
complete. Reuses the mem20 substrate through the same sealed Backend so
everything runs hermetic under tests and native against the real ledger.

Toolsets: "skills" (mem20 procedural skills inventory) and/or "none" (pure
chat). Approvals: auto | ask | deny (one-shot forces "auto").
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Callable, Optional

from ._substrate import Backend, get_backend
from .profiles import Profiles

CONTRACT = (
    "You are the reasoning core of the mem20 agent platform. You are carrying "
    "on a conversation with the user and may use tools. Decide the NEXT action.\n"
    'Reply ONLY with a JSON object, one of three shapes:\n'
    '  {"action": "tool",   "tool": "<name>", "args": "<string arg>"}\n'
    '  {"action": "final",  "final": "<your reply to the user>"}\n'
    "Choose \"final\" when you can answer, even partially. Never invent tools: "
    "only the tools in the inventory below may be referenced. A \"final\" "
    "message should be written as a direct reply to the user."
)

TOOLSET_SKILLS = "skills"
TOOLSET_NONE = "none"


def _parse_action(raw: str) -> dict:
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return {"action": "final", "final": raw.strip()}
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        obj = {}
    if not isinstance(obj, dict):
        return {"action": "final", "final": raw.strip()}
    action = str(obj.get("action") or "final").lower()
    if action == "tool":
        tool = obj.get("tool")
        if tool:
            return {"action": "tool", "tool": str(tool),
                    "args": str(obj.get("args") or "")}
    if action == "final":
        return {"action": "final",
                "final": str(obj.get("final") or "").strip()}
    return {"action": "final", "final": raw.strip()}


class Brain:
    """LLM reasoning core; propose() decodes the strict-JSON action contract."""

    name = "mem20agentz"

    def __init__(self, backend: Optional[Backend] = None,
                 model: Optional[str] = None) -> None:
        self._b = backend or get_backend()
        self.model = model

    def propose(self, goal: str, tools_blob: str,
                observations: list[str]) -> dict:
        obs_blob = "\n".join(f"[step {i}] {o[:300]}"
                             for i, o in enumerate(observations[-6:]))
        user = (
            f"{goal}\n\nAVAILABLE TOOLS:\n{tools_blob}\n\n"
            f"PAST OBSERVATIONS:\n{obs_blob}\n\n"
            "Decide the next action (strict JSON only)."
        )
        raw = self._b.llm_chat([{"role": "system", "content": CONTRACT},
                                {"role": "user", "content": user}],
                               model=self.model, max_tokens=1400)
        return _parse_action(raw)


class Toolbox:
    """Tool inventory + executor over mem20 procedural skills."""

    def __init__(self, backend: Optional[Backend] = None,
                 toolsets: tuple = (TOOLSET_SKILLS,)) -> None:
        self._b = backend or get_backend()
        self._toolsets = toolsets or (TOOLSET_SKILLS,)

    def inventory(self) -> str:
        if TOOLSET_NONE in self._toolsets and TOOLSET_SKILLS not in self._toolsets:
            return "(no tools available)"
        entries = []
        for skill in self._b.procedural_list(category=""):
            name = skill.get("name") or skill.get("skill") or ""
            desc = skill.get("description") or ""
            if name:
                entries.append(f"- {name}: {desc}")
        return "\n".join(entries) or "(no tools available)"

    def execute(self, name: str, args: str) -> dict:
        return self._b.procedural_execute(name, {"arg": args, "raw": args})


@dataclass
class Step:
    index: int
    action: str
    tool: str = ""
    output: str = ""


@dataclass
class AgentResult:
    text: str
    steps: list[Step] = field(default_factory=list)
    blocked: bool = False
    reason: str = ""


class AgentCore:
    """One conversational run: prior context + prompt -> final reply."""

    def __init__(self, backend: Optional[Backend] = None,
                 profile: str = "mem20", model: Optional[str] = None,
                 approvals: str = "auto", max_iter: int = 6,
                 toolsets: tuple = (TOOLSET_SKILLS,),
                 approve_tool: Optional[Callable[[str, str], bool]] = None,
                 history: Optional[list[dict]] = None,
                 hook_registry=None) -> None:
        self._b = backend or get_backend()
        self.profile = profile
        self.model = model
        self.approvals = approvals
        self.max_iter = max_iter
        self.toolsets = toolsets
        self.approve_tool = approve_tool
        self.history = list(history or [])
        self.hook_registry = hook_registry
        self.brain = Brain(backend, model)
        self.toolbox = Toolbox(backend, toolsets)

    # -------------------------------------------------------------- system
    def _system_blob(self) -> str:
        prof = Profiles(self._b).ensure(self.profile)
        lines = [f"Profile: {self.profile}"]
        if prof.identity:
            lines.append(f"You are: {prof.identity}")
        if prof.capabilities:
            lines.append(f"Capabilities: {', '.join(prof.capabilities)}")
        if prof.values:
            lines.append(f"Values: {', '.join(prof.values)}")
        return "\n".join(lines)

    def _prior_messages(self) -> list[dict]:
        return [{"role": m.get("role", "user"), "content": m.get("content", "")}
                for m in self.history[-20:]]

    def _goal_with_history(self, prompt: str) -> str:
        turns = self._prior_messages()
        if not turns:
            return prompt
        block = "\n".join(
            f"[{m['role']}] {m['content'][:800]}" for m in turns)
        return (f"PREVIOUS CONVERSATION (continue naturally from here):\n"
                f"{block}\n\nUSER:\n{prompt}")

    # ----------------------------------------------------------------- run
    def run(self, prompt: str) -> AgentResult:
        goal = self._goal_with_history(prompt)
        observations: list[str] = []
        steps: list[Step] = []
        final = ""
        blocked = False
        reason = ""

        self._fire("run_start", {"profile": self.profile, "goal": goal[:200]})
        try:
            result = self._loop(goal, observations, steps, final, blocked,
                                reason)
        finally:
            self._fire("session_end", {"profile": self.profile,
                                       "steps": len(steps)})
        return result

    def _loop(self, goal, observations, steps, final, blocked, reason):
        for i in range(1, self.max_iter + 1):
            proposal = self._propose(goal, observations)
            action = proposal.get("action", "final")
            if action == "final":
                final = str(proposal.get("final") or
                            (observations[-1] if observations else ""))
                steps.append(Step(i, "final", output=final))
                break
            if action == "tool":
                tool = str(proposal.get("tool") or "")
                args = str(proposal.get("args") or "")
                if not self._tool_allowed(tool, args):
                    blocked = True
                    reason = f"tool '{tool}' denied by approvals policy"
                    steps.append(Step(i, "blocked", tool=tool, output=reason))
                    break
                if tool not in self._tool_names():
                    observations.append(
                        f"[brain] tool not in inventory: {tool}")
                    steps.append(Step(i, "unknown", tool=tool,
                                      output="not in inventory"))
                    continue
                self._fire("before_tool", {"tool": tool, "args": args[:200]})
                result = self.toolbox.execute(tool, args)
                output = result.get("output") or str(result.get("ok"))
                observations.append(f"[tool {tool}] {str(output)[:400]}")
                steps.append(Step(i, "tool", tool=tool, output=output))
                self._fire("after_tool", {"tool": tool,
                                          "truncated": str(output)[:200]})
                continue
            observations.append(f"[brain] unrecognized action: {proposal}")
            steps.append(Step(i, "unknown", output=str(proposal)))

        if not final and not blocked:
            final = "[max_iter reached] " + (
                observations[-1] if observations else "no final answer produced")
            if steps:
                steps[-1].output += "\n(max_iter)"
        return AgentResult(text=final, steps=steps, blocked=blocked,
                           reason=reason)

    # -------------------------------------------------------------- helpers
    def _fire(self, event: str, payload: dict) -> None:
        if self.hook_registry is None:
            return
        try:
            self.hook_registry.fire(event, payload)
        except Exception:  # noqa: BLE001  hooks never break the loop
            pass

    def _propose(self, prompt: str, observations: list[str]) -> dict:
        try:
            return self.brain.propose(prompt, self.toolbox.inventory(),
                                      observations)
        except Exception as exc:  # noqa: BLE001
            return {"action": "final",
                    "final": f"[brain error] {type(exc).__name__}: {exc}"}

    def _tool_names(self) -> list[str]:
        if TOOLSET_SKILLS not in self.toolsets:
            return []
        return [s.get("name") or s.get("skill") or ""
                for s in self._b.procedural_list(category="")]

    def _tool_allowed(self, tool: str, args: str) -> bool:
        if self.approvals == "deny":
            return False
        if self.approvals == "ask":
            if self.approve_tool is None:
                return False
            return bool(self.approve_tool(tool, args))
        return True


def persist_turn(backend: Backend, profile: str, session_id: str,
                 user: str, reply: str) -> list[str]:
    """Record user + assistant turns into the session transcript. Returns
    the ledger ids, or [] when nothing could be written (sealed)."""
    ids = []
    try:
        ids.append(backend.session_append(profile, session_id, "user", user)
                   .get("id", ""))
        ids.append(backend.session_append(profile, session_id, "assistant",
                                          reply).get("id", ""))
    except Exception:  # noqa: BLE001  (sealed backend in tests)
        pass
    return [i for i in ids if i]