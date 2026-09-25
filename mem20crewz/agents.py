"""Agent — self-model + namespace.

Every mem20crewz Agent is bound to the mem20 substrate as:
- a SelfModel identity (role/goal/backstory + capabilities + values)
- a memory namespace (topic tag used for namespaced recall + persistence)

Agent.kickoff() is the single-agent execution primitive (mem20 crews parity): it runs
the ToolLoop against a goal derived from the task context.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Any, Optional

from ._substrate import backend as sub
from .guardrails import Guards
from .loop import ToolLoop, LoopResult
from .skills import Skills


def slug(text: str) -> str:
    """Stable, filesystem-friendly namespace slug."""
    cleaned = "".join(c.lower() if c.isalnum() else "-" for c in text)
    cleaned = "-".join(cleaned.split("-"))
    tag = hashlib.sha1(cleaned.encode()).hexdigest()[:8]
    return f"{cleaned[:24] or 'agent'}-{tag}"


def _python_runner(snippet: str) -> str:
    """Sandboxed code execution: run `snippet` in a fresh python subprocess.

    Isolation: separate process + tempdir (chdir), no inherited stdin, bounded
    wall time, stdin/network intentionally not exposed. Returns stdout+stderr.
    """
    timeout = 30
    with tempfile.TemporaryDirectory(prefix="mem20-exec-") as td:
        src = os.path.join(td, "snippet.py")
        with open(src, "w", encoding="utf-8") as fh:
            fh.write(snippet)
        env = {k: v for k, v in os.environ.items()}
        # strip secrets so a run can never leak keys into output/cwd
        for k in list(env):
            if any(seed in k.upper() for seed in ("KEY", "TOKEN", "SECRET", "PASSWORD")):
                env.pop(k, None)
        try:
            proc = subprocess.run(
                [sys.executable, src],
                capture_output=True, text=True, timeout=timeout,
                cwd=td, env=env,
            )
            out = proc.stdout.strip()
            if proc.returncode != 0:
                err = (proc.stderr or "").strip() or f"exit {proc.returncode}"
                if out:
                    return f"{out}\n[stderr] {err}"[:2000]
                return f"[exit {proc.returncode}] {err}"[:2000]
            return out or "[ok]"
        except subprocess.TimeoutExpired:
            return f"[code execution timed out after {timeout}s]"
        except Exception as exc:
            return f"[code execution error] {type(exc).__name__}: {exc}"


@dataclass
class Agent:
    role: str
    goal: str
    backstory: str = ""
    capabilities: list[str] = field(default_factory=list)
    values: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    max_iter: int = 10
    guardrails: bool = True
    namespace: Optional[str] = None
    llm: str = "cog"  # brain selection hint: "cog" for real, else a Brain instance
    brain: Any = field(default=None, repr=False)
    a2a: Any = field(default=None, repr=False)  # A2AClient-like (delegation)
    allow_delegation: bool = True
    allow_code_execution: bool = False
    max_rpm: int = 0            # requests per minute cap (0 = unlimited)
    max_execution_time: float = 0.0  # hard deadline in seconds (0 = unlimited)
    verbose: bool = False
    knowledge: list[str] = field(default_factory=list)  # memory topics to load
    planning: bool = False       # run a planning phase before kickoff
    function_calling_llm: Any = field(default=None, repr=False)  # brain used for propose()

    def __post_init__(self) -> None:
        if self.namespace is None:
            self.namespace = slug(self.role)
        if not self.capabilities:
            self.capabilities = ["plan", "reason", "reflect", "self-model", "memory"]
        if not self.values:
            self.values = ["no workarounds", "proper root-cause fixes", "use mem20 substrate"]
        if not self.tools:
            self.tools = []

    # ------------------------------------------------------------- identity
    def identity(self) -> dict:
        return {
            "role": self.role,
            "goal": self.goal,
            "backstory": self.backstory,
            "capabilities": ", ".join(self.capabilities),
            "values": ", ".join(self.values),
            "namespace": self.namespace,
            "max_iter": self.max_iter,
            "max_rpm": self.max_rpm,
            "max_execution_time": self.max_execution_time,
            "allow_delegation": self.allow_delegation,
            "allow_code_execution": self.allow_code_execution,
            "planning": self.planning,
            "knowledge": ", ".join(self.knowledge) or "(none)",
            "tools": ", ".join(
                t if isinstance(t, str) else getattr(t, "__name__", "callable")
                for t in self.tools) or "none bound",
        }

    def persist_identity(self, actor: str = "agent") -> dict:
        """Write this agent's self-model into mem20 memory (namespaced)."""
        return sub.remember(
            topic=self.namespace,
            content=(
                f"Agent identity [{self.role}]: goal='{self.goal}'; "
                f"backstory='{self.backstory}'; capabilities={self.capabilities}; "
                f"values={self.values}"
            ),
            tags=["mem20crewz", "agent", self.namespace],
            actor=actor, epistemic_status="observed",
            source=f"mem20crewz:agent:{self.namespace}",
        )

    # ------------------------------------------------------------- execution
    def kickoff(self, task_context: Any, *, guards: Optional[Guards] = None,
                max_iter: Optional[int] = None,
                step_callback: Optional[Any] = None) -> LoopResult:
        """Run the tool loop for this agent against a TaskContext.

        The goal handed to the brain is the assembled task prompt; the tool
        inventory the brain may call is the agent's bound tools.
        """
        skills = Skills()
        for t in self.tools:
            if callable(t):
                skills.add_callable(getattr(t, "__name__", "callable"), t)
            else:
                skills.add_procedural(str(t))
        skills.load_procedural_inventory()

        # code-execution: only when the agent explicitly allows it; the tool is
        # the sandboxed mem20 python runner (runs a snippet in a subprocess).
        if self.allow_code_execution:
            skills.add_callable(
                "mem20_tool_execute_python",
                _python_runner,
                description="Run a python snippet in a sandboxed subprocess "
                            "and return its stdout (code execution tool).")

        # knowledge: seed the loop with recalls for each configured topic.
        initial = []
        if self.knowledge:
            for topic in self.knowledge:
                try:
                    rows = sub.recall(topic=topic, k=3)
                except Exception:
                    rows = []
                snippets = [r.get("content", r.get("fact", ""))[:300]
                            for r in rows if isinstance(r, dict)]
                if snippets:
                    initial.append(f"[knowledge:{topic}] " + " | ".join(snippets))

        # planning: run the brain's plan first and hand it to the loop as an
        # observation so the agent acts on an explicit plan when enabled.
        goal = task_context.prompt() if hasattr(task_context, "prompt") else str(task_context)
        brain = self._resolve_brain()
        if self.planning:
            try:
                plan = brain.plan(goal)
                if plan:
                    initial.append(f"[plan] {plan[:600]}")
            except Exception as exc:
                initial.append(f"[plan error] {type(exc).__name__}: {exc}")

        g = guards or Guards(actor=self.namespace, enforce_plan=self.guardrails)
        loop = ToolLoop(brain=brain, skills=skills, guards=g,
                        max_iter=max_iter or self.max_iter,
                        a2a=self.a2a if self.allow_delegation else None,
                        max_rpm=self.max_rpm,
                        max_execution_time=self.max_execution_time,
                        verbose=self.verbose,
                        step_callback=step_callback)
        return loop.run(goal=goal, initial_observations=initial,
                        available_tools=skills.inventory())

    def _resolve_brain(self):
        """brain for propose() comes from function_calling_llm if provided,
        else the agent's own brain (default CogBrain)."""
        proposed = self.function_calling_llm
        if proposed is not None:
            return proposed
        return self.brain or self._default_brain()

    def _default_brain(self):
        from .neural import CogBrain
        return CogBrain()

    # ----------------------------------------------------------- convenience
    def to_dict(self) -> dict:
        return {
            "role": self.role, "goal": self.goal, "backstory": self.backstory,
            "capabilities": self.capabilities, "values": self.values,
            "tools": [t if isinstance(t, str) else getattr(t, "__name__", "callable")
                      for t in self.tools],
            "max_iter": self.max_iter, "guardrails": self.guardrails,
            "namespace": self.namespace, "llm": self.llm,
            "allow_delegation": self.allow_delegation,
            "allow_code_execution": self.allow_code_execution,
            "max_rpm": self.max_rpm,
            "max_execution_time": self.max_execution_time,
            "verbose": self.verbose,
            "knowledge": list(self.knowledge),
            "planning": self.planning,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Agent":
        return cls(
            role=data["role"], goal=data["goal"], backstory=data.get("backstory", ""),
            capabilities=list(data.get("capabilities", [])),
            values=list(data.get("values", [])),
            tools=list(data.get("tools", [])),
            max_iter=int(data.get("max_iter", 10)),
            guardrails=bool(data.get("guardrails", True)),
            namespace=data.get("namespace"),
            llm=data.get("llm", "cog"),
            allow_delegation=bool(data.get("allow_delegation", True)),
            allow_code_execution=bool(data.get("allow_code_execution", False)),
            max_rpm=int(data.get("max_rpm", 0)),
            max_execution_time=float(data.get("max_execution_time", 0.0)),
            verbose=bool(data.get("verbose", False)),
            knowledge=list(data.get("knowledge", []) or []),
            planning=bool(data.get("planning", False)),
        )