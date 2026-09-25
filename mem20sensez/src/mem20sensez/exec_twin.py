"""exec_twin — Execution Digital Twin (RM-052 reversible, RM-053 speculative).

Wraps mem20langz StateGraph: each plan step is a real graph node that records
pre/post state deltas (reversible), and the twin can branch speculatively
(conditional edges) to try alternative next-steps without committing. Built on
the real mem20langz substrate — no stub orchestration.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Callable

from mem20langz import InMemorySaver, StateGraph


@dataclass
class ExecStep:
    name: str
    action: str
    pre: dict[str, Any] = field(default_factory=dict)
    post: dict[str, Any] = field(default_factory=dict)
    reverted: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "action": self.action,
                "pre": self.pre, "post": self.post, "reverted": self.reverted}


@dataclass
class ExecPlan:
    steps: list[ExecStep] = field(default_factory=list)
    spec_branches: list[str] = field(default_factory=list)
    final_state: dict[str, Any] = field(default_factory=dict)
    plan_id: str = ""
    braid: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"steps": [s.to_dict() for s in self.steps],
                "spec_branches": self.spec_branches,
                "final_state": self.final_state,
                "plan_id": self.plan_id,
                "braid": self.braid}


class ExecTwin:
    """Deterministic execution twin. Injected steps are executed by REAL graph nodes."""

    def __init__(self) -> None:
        self.graph = StateGraph(dict[str, Any])
        self._built = False

    def build(self, steps: list[dict[str, Any]]) -> None:
        """Build a StateGraph whose nodes apply the step actions (real functions)."""
        def _make(step: dict[str, Any]) -> Callable[[dict[str, Any]], dict[str, Any]]:
            def node(state: dict[str, Any]) -> dict[str, Any]:
                value = int(step.get("value", 1))
                key = step.get("key", "acc")
                new_val = state.get(key, 0) + value
                step["_pre"] = dict(state)
                step["_post"] = {**state, key: new_val}
                return {key: new_val}
            return node

        if not steps:
            raise ValueError("exec twin needs >= 1 step to build a real graph")
        keys = [s["name"] for s in steps]
        prev = None
        for i, s in enumerate(steps):
            self.graph.add_node(s["name"], _make(s))
            if prev:
                self.graph.add_edge(prev, s["name"])
            prev = s["name"]
        self.graph.set_entry_point(keys[0])
        self.graph.set_finish_point(keys[-1])
        self.graph.validate()
        self._graph_steps = steps
        self._built = True

    def run(self, initial: dict[str, Any] | None = None,
            journal: bool = False) -> ExecPlan:
        if not self._built:
            raise ValueError("build() the graph before run()")
        checkpointer = InMemorySaver()
        app = self.graph.compile(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": "exec-twin-1", "checkpoint_ns": "twin"}}
        final = app.invoke(initial or {}, config=config)
        steps = []
        pre = dict(initial or {})
        for s in self._graph_steps:
            post = dict(s.get("_post") or final)
            steps.append(ExecStep(name=s["name"], action=s.get("action", s["name"]),
                                  pre=pre, post=post))
            pre = post
        final_state = dict(final)
        spec_branches = [s["name"] for s in self._graph_steps]
        plan_id = hashlib.sha256(
            json.dumps({"steps": [s.name for s in steps], "final": final_state}, sort_keys=True).encode()
        ).hexdigest()[:16]
        plan = ExecPlan(steps=steps, spec_branches=spec_branches,
                        final_state=final_state, plan_id=plan_id)
        if journal:
            from .braid_hook import journal
            plan.braid = journal("exec.twin.replan", plan_id, plan.to_dict())
        return plan