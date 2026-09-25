"""ToolLoop — the tool-callback loop (build gap #2).

Drives an agent to completion through repeated propose→execute→observe:

    propose (brain) -> action decision
      tool      -> Skills.execute -> observation fed back
      delegate  -> A2A fan-out by capability -> observation fed back
      final     -> return output
    bounded by max_iter; the plan-execution guard gates every iteration and the
    epistemic veto can block the final answer before it is persisted.

Deterministic in tests via FakeBrain + injected Skills/A2A; real runs use
CogBrain and live skills/A2A. Errors never crash the loop — they become
observations so the brain can recover.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

import time

from .guardrails import GuardrailBlocked, Guards

if TYPE_CHECKING:
    from .neural import Brain
    from .skills import Skills


@dataclass
class LoopStep:
    index: int
    action: str
    tool: str = ""
    output: str = ""
    ok: bool = True


@dataclass
class LoopResult:
    text: str
    iterations: int
    steps: list[LoopStep] = field(default_factory=list)
    blocked: bool = False
    blocked_reason: str = ""
    observations: list[str] = field(default_factory=list)
    fact_ids: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "iterations": self.iterations,
            "blocked": self.blocked,
            "blocked_reason": self.blocked_reason,
            "final_text": self.text[:400],
            "steps": [
                {"i": s.index, "action": s.action, "tool": s.tool, "ok": s.ok}
                for s in self.steps
            ],
        }


class ToolLoop:
    def __init__(self, brain: "Brain", skills: "Skills",
                 guards: Optional[Guards] = None, max_iter: int = 10,
                 a2a=None, max_rpm: int = 0,
                 max_execution_time: float = 0.0,
                 verbose: bool = False,
                 step_callback: Optional[Any] = None,
                 require_tool_before_final: bool = False) -> None:
        self.brain = brain
        self.skills = skills
        self.guards = guards or Guards()
        self.max_iter = max_iter
        self.a2a = a2a  # A2AClient-like with .fan_out(capability, message)
        self.max_rpm = max_rpm
        self.max_execution_time = max_execution_time
        self.verbose = verbose
        self.step_callback = step_callback  # step_callback(step_index, action, tool, ok)
        self.require_tool_before_final = require_tool_before_final
        self._pending_calls: list[float] = []  # for max_rpm gating

    def _throttle(self) -> None:
        """Respect max_rpm by spacing propose() calls >= 60/rpm apart."""
        if self.max_rpm <= 0:
            return
        import time
        now = time.monotonic()
        self._pending_calls = [t for t in self._pending_calls if now - t < 60.0]
        if len(self._pending_calls) >= self.max_rpm:
            wait = 60.0 / self.max_rpm
            time.sleep(wait)
        self._pending_calls.append(time.monotonic())

    def _deadline_exceeded(self, start: float) -> bool:
        if self.max_execution_time <= 0:
            return False
        import time
        return time.monotonic() - start > self.max_execution_time

    def run(self, goal: str, available_tools: Optional[str] = None,
            initial_observations: Optional[list] = None,
            fact_ids: Optional[list] = None) -> LoopResult:
        import time
        start = time.monotonic()
        observations = list(initial_observations or [])
        tool_blob = available_tools or self.skills.inventory()
        steps: list[LoopStep] = []
        final = ""
        blocked = False
        blocked_reason = ""

        for i in range(1, self.max_iter + 1):
            # hard execution deadline: stop deciding once the budget is used.
            if self._deadline_exceeded(start):
                final = ("[max_execution_time reached] " +
                         (observations[-1] if observations else "no answer produced"))
                steps.append(LoopStep(i, "final", output=final))
                break

            # plan-execution gate each iteration (cheap: registration only)
            try:
                self.guards.gate(fact_ids=fact_ids)
            except GuardrailBlocked as exc:
                blocked = True
                blocked_reason = exc.reason
                break

            self._throttle()
            proposal = self._propose(goal, tool_blob, observations,
                                     require_tool_before_final=self.require_tool_before_final)
            action = proposal.get("action", "final")

            if self.verbose:
                print(f"[loop] iter={i} action={action} "
                      f"tool={proposal.get('tool') or proposal.get('capability') or ''}")

            step = None
            if action == "final":
                final = str(proposal.get("final") or
                            (observations[-1] if observations else ""))
                # A task requiring file/material output must produce at least
                # one successful tool step before 'final' is accepted. Premature
                # final (common when an LLM collapses straight to 'done') is fed
                # back as an observation so the loop continues with tools.
                tool_success = any(
                    s.action == "tool" and s.ok for s in steps)
                if (self.require_tool_before_final and not tool_success
                        and i < self.max_iter):
                    observations.append(
                        "[guard] 'final' rejected: exit requires at least one "
                        "successful tool action (write-file or scaffold) that "
                        "produces the deliverable. Run a tool now, then final.")
                    steps.append(LoopStep(
                        i, "unknown",
                        output="[guard] final rejected (no tool step yet)"))
                    self._notify_step(i, "final-rejected", "", False)
                    continue
                step = LoopStep(i, "final", output=final)
                steps.append(step)
                self._notify_step(i, action, "", True)
                break

            if action == "tool":
                tool = str(proposal.get("tool") or "")
                arg = proposal.get("args", "")
                result = self.skills.execute(tool, arg)
                output = result.get("output", "")
                observations.append(f"[tool {tool}] {output[:400]}")
                step = LoopStep(i, "tool", tool=tool,
                                output=output, ok=result.get("ok", True))
                steps.append(step)
                self._notify_step(i, action, tool, step.ok)
                continue

            if action == "delegate":
                capability = str(proposal.get("capability") or "")
                message = str(proposal.get("message") or "")
                output = self._delegate(capability, message)
                observations.append(f"[delegate {capability}] {output[:400]}")
                step = LoopStep(i, "delegate", tool=capability, output=output)
                steps.append(step)
                self._notify_step(i, action, capability, True)
                continue

            observations.append(f"[brain] unrecognized action: {proposal}")
            step = LoopStep(i, "unknown", output=str(proposal))
            steps.append(step)
            self._notify_step(i, "unknown", "", False)

        if not final and not blocked:
            final = "[max_iter reached] " + (observations[-1] if observations else
                                             "no final answer produced")

        return LoopResult(
            text=final,
            iterations=len(steps),
            steps=steps,
            blocked=blocked,
            blocked_reason=blocked_reason,
            observations=observations,
            fact_ids=list(fact_ids or []),
        )

    # -------------------------------------------------------------- helpers
    def _notify_step(self, index: int, action: str, tool: str, ok: bool) -> None:
        if self.step_callback is None or not callable(self.step_callback):
            return
        try:
            self.step_callback(step_index=index, action=action, tool=tool, ok=ok)
        except Exception:
            pass  # a broken observer never breaks the loop

    def _propose(self, goal: str, tool_blob: str, observations: list[str],
                 require_tool_before_final: bool = False) -> dict:
        # Transient infra failures (DNS blips, provider throttling, timeouts)
        # are retried with backoff so a healthy provider re-routes. A brain
        # error is NEVER fabricated into a polite "final": that turns an
        # outage into a silently-collapsed worker. After retries are
        # exhausted the failure surfaces as "unknown" so the loop re-proposes
        # with the failure visible in PAST OBSERVATIONS.
        last_error: Optional[BaseException] = None
        for attempt in range(3):
            try:
                proposal = self.brain.propose(
                    goal, tool_blob, observations, require_tool_before_final)
            except Exception as exc:
                last_error = exc
                # Never swallow a brain failure: without this line an LLM
                # outage is invisible and the worker just emits "unknown"
                # steps until max_iter.
                print(f"[loop] brain error (attempt {attempt + 1}/3): "
                      f"{type(exc).__name__}: {exc}")
                if attempt < 2:
                    time.sleep(4 * (attempt + 1))
                continue
            if not isinstance(proposal, dict):
                return {"action": "unknown", "raw": str(proposal)}
            return proposal
        return {"action": "unknown",
                "raw": f"[brain error after retries] {type(last_error).__name__}: {last_error}"}

    def _delegate(self, capability: str, message: str) -> str:
        if self.a2a is None:
            return "[delegate skipped: no A2A client configured]"
        try:
            result = self.a2a.fan_out(capability, message)
        except Exception as exc:
            return f"[delegate error] {type(exc).__name__}: {exc}"
        if isinstance(result, dict) and result.get("results"):
            replies = [
                f"{r.get('agent')}: {r.get('reply', r.get('error', ''))[:300]}"
                for r in result["results"]
            ]
            return "; ".join(replies)
        return str(result)[:600]