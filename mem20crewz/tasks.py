"""Task — description/expected_output/context + execution to a result.

A Task names an agent, says what to do and what "done" looks like, and can
carry structured output contracts (output_json schema, output_file target).
run() assembles the context (gap #1), executes via the agent's kickoff (gap #2),
then persists the output to mem20 memory and/or disk.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from ._substrate import backend as sub
from .context import assemble as assemble_context
from .guardrails import GuardrailBlocked, Guards

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "runtime", "outputs")


@dataclass
class TaskOutcome:
    task_name: str
    agent: str
    ok: bool
    output: str
    blocked: bool = False
    blocked_reason: str = ""
    iterations: int = 0
    context: Optional[dict] = None
    json_output: Optional[dict] = None
    model: Any = None            # output_pydantic instance when validated
    saved_to: Optional[str] = None
    memory_id: Optional[str] = None
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "task": self.task_name, "agent": self.agent, "ok": self.ok,
            "output": self.output[:2000], "blocked": self.blocked,
            "blocked_reason": self.blocked_reason, "iterations": self.iterations,
            "context": self.context, "json_output": self.json_output,
            "saved_to": self.saved_to, "memory_id": self.memory_id, "ts": self.ts,
        }


@dataclass
class Task:
    name: str
    description: str
    expected_output: str
    agent: str = ""           # name of the assigned agent (resolved by Crew)
    context: list = field(default_factory=list)   # upstream task names
    output_file: Optional[str] = None
    output_json: Any = False       # True | dict schema {keys: types}
    output_pydantic: Any = None    # a pydantic model class to validate against
    human_input: bool = False      # request human review before execution
    async_execution: bool = False  # run concurrently; joined before use
    callback: Any = None           # task_callback(step, outcome) after the run
    step_callback: Any = None      # step_callback(step) per loop iteration
    guardrails: bool = True
    persist_output: bool = True
    notes: str = ""

    # ------------------------------------------------------------- execution
    def run(self, crew_state: dict, agent, inputs: dict,
            guards: Optional[Guards] = None) -> TaskOutcome:
        """Assemble context, execute, persist. Never raises on task failure."""
        if self.human_input and not self._human_approved():
            return TaskOutcome(task_name=self.name,
                               agent=agent.role if agent else "",
                               ok=False, output="", blocked=True,
                               blocked_reason="human_input requested; review not approved",
                               context=None)
        outcome = self._execute(crew_state, agent, inputs, guards)
        if outcome.ok and self.persist_output:
            outcome.memory_id = self._persist_memory(agent, outcome)
        self._persist_disk(outcome)
        if self.callback is not None:
            try:
                self.callback(self, outcome)
            except Exception as exc:
                outcome.output += f"\n[task_callback error] {type(exc).__name__}: {exc}"
        return outcome

    def _human_approved(self) -> bool:
        """Ask the human-review seam; hermetic tests inject a hook via substrate.
        Default (no hook): defer — treat a missing reviewer as not approved so we
        never pretend a human signed off."""
        try:
            sub.human_review(task_name=self.name)
        except Exception:
            return False
        return True

    # ------------------------------------------------------------------ core
    def _execute(self, crew_state: dict, agent, inputs: dict,
                 guards: Optional[Guards]) -> TaskOutcome:
        upstream = {name: crew_state.get(name) for name in self.context
                    if name in crew_state}
        ctx = assemble_context(self, agent, upstream, inputs)
        g = guards
        if agent is not None and self.guardrails:
            g = g or Guards(actor=agent.namespace, enforce_plan=self.guardrails)
        try:
            result = agent.kickoff(ctx, guards=g, step_callback=self.step_callback)
        except GuardrailBlocked as exc:
            return TaskOutcome(task_name=self.name, agent=agent.role if agent else "",
                               ok=False, output="", blocked=True,
                               blocked_reason=exc.reason, context=ctx.to_dict())
        json_out = self._coerce_json(result.text)
        o = TaskOutcome(
            task_name=self.name,
            agent=agent.role if agent else "",
            ok=not result.blocked,
            output=result.text,
            blocked=result.blocked,
            blocked_reason=result.blocked_reason,
            iterations=result.iterations,
            context=ctx.to_dict(),
            json_output=json_out,
            model=self._coerce_model(result.text),
        )
        return o

    # -------------------------------------------------------------- persistence
    def _coerce_model(self, text: str) -> Any:
        """Validate the raw output against output_pydantic (a pydantic model).
        Returns a model instance on success, None if invalid or not configured."""
        model = self.output_pydantic
        if not model:
            return None
        try:
            obj = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return None
        if not isinstance(obj, dict):
            return None
        try:
            return model.model_validate(obj)
        except Exception:
            return None

    def _coerce_json(self, text: str) -> Optional[dict]:
        if not self.output_json:
            return None
        try:
            obj = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return None
        if not isinstance(obj, dict):
            return None
        if isinstance(self.output_json, dict):
            missing = [k for k in self.output_json if not isinstance(obj.get(k), self.output_json[k])]
            obj["_schema_missing_or_bad"] = missing
        return obj

    def _persist_memory(self, agent, outcome: TaskOutcome) -> Optional[str]:
        try:
            r = sub.remember(
                topic=agent.namespace if agent else self.name,
                content=(f"task:{self.name} ok -> {outcome.output[:600]}"),
                tags=["mem20crewz", "task", self.name,
                      (agent.namespace if agent else "crew")],
                actor=(agent.namespace if agent else "crew"),
                epistemic_status=("observed" if outcome.ok else "hypothesis"),
                source=f"mem20crewz:task:{self.name}",
            )
            return r.get("id") or r.get("fact_id")
        except Exception:
            return None

    def _persist_disk(self, outcome: TaskOutcome) -> None:
        path = self.output_file
        if path:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            if outcome.json_output is not None:
                with open(path, "w", encoding="utf-8") as fh:
                    json.dump(outcome.json_output, fh, indent=2)
                    outcome.saved_to = path
            else:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(outcome.output)
                    outcome.saved_to = path

    def to_dict(self) -> dict:
        return {
            "name": self.name, "description": self.description,
            "expected_output": self.expected_output, "agent": self.agent,
            "context": list(self.context), "output_file": self.output_file,
            "output_json": self.output_json, "guardrails": self.guardrails,
            "persist_output": self.persist_output, "notes": self.notes,
            "human_input": self.human_input,
            "async_execution": self.async_execution,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        return cls(
            name=data["name"], description=data["description"],
            expected_output=data.get("expected_output", ""),
            agent=data.get("agent", ""), context=list(data.get("context", [])),
            output_file=data.get("output_file"),
            output_json=data.get("output_json", False),
            guardrails=bool(data.get("guardrails", True)),
            persist_output=bool(data.get("persist_output", True)),
            notes=data.get("notes", ""),
            human_input=bool(data.get("human_input", False)),
            async_execution=bool(data.get("async_execution", False)),
        )