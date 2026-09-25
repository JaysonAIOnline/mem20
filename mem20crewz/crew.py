"""Crew — multi-agent collaboration. A Crew.kickoff() IS a roadmap run.

Sequential execution: tasks run in order, each task's output feeds the next
task's `context` list (task-context assembly, gap #1). Each task is a roadmap
phase; results carry per-task provenance. Optional delegation surface for
agents that fan out to A2A peers.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

from ._substrate import backend as sub
from .agents import Agent
from .guardrails import Guards
from .roadmap import Roadmap
from .tasks import Task, TaskOutcome


@dataclass
class CrewResult:
    crew: str
    inputs: dict
    outcomes: list = field(default_factory=list)
    roadmap: Optional[Roadmap] = None
    started: float = field(default_factory=time.time)
    summary_output: str = ""

    def ok(self) -> bool:
        return all(o.ok for o in self.outcomes if isinstance(o, TaskOutcome))

    def output(self, task_name: str) -> Optional[str]:
        for o in self.outcomes:
            if o.task_name == task_name and isinstance(o, TaskOutcome):
                return o.output
        return None

    def to_dict(self) -> dict:
        return {
            "crew": self.crew, "inputs": self.inputs,
            "outcomes": [o.to_dict() for o in self.outcomes],
            "ok": self.ok(),
            "summary_output": self.summary_output[:2000],
            "roadmap_path": self.roadmap.path if self.roadmap else None,
            "roadmap": self.roadmap.view() if self.roadmap else [],
        }


class Crew:
    def __init__(self, name: str, agents: list[Agent], tasks: list[Task],
                 process: str = "sequential", roadmap: bool = True,
                 persist_memory: bool = True, brain=None, guards: Optional[Guards] = None,
                 a2a=None, planning: bool = False, cache: bool = True,
                 verbose: bool = False, manager_agent: Optional[Agent] = None,
                 manager_llm: Any = None,
                 task_callback: Any = None, step_callback: Any = None) -> None:
        self.name = name
        self.agents = {a.role: a for a in agents}
        self.agents.update({a.namespace: a for a in agents})
        self.tasks = tasks
        self.process = process
        self.roadmap_enabled = roadmap
        self.persist_memory = persist_memory
        self.brain = brain
        self.guards = guards
        self.a2a = a2a
        self.planning = planning
        self.cache = cache
        self.verbose = verbose
        self.manager_agent = manager_agent
        self.manager_llm = manager_llm
        self.task_callback = task_callback
        self.step_callback = step_callback

    # ------------------------------------------------------------------ run
    def kickoff(self, inputs: Optional[dict] = None) -> CrewResult:
        inputs = inputs or {}
        if self.persist_memory:
            for a in self.agents.values():
                try:
                    a.persist_identity()
                except Exception:
                    pass
            # every agent inherits the crew's delegation surface unless it has one
            if self.a2a is not None:
                for a in self.agents.values():
                    if a.a2a is None:
                        a.a2a = self.a2a
        roster = self.agents
        guards = self.guards or Guards(actor=self.name)
        rmap = Roadmap(self.name) if self.roadmap_enabled else None
        result = CrewResult(crew=self.name, inputs=inputs, roadmap=rmap)

        # planning: emit a plan phase into the roadmap before executing tasks.
        if rmap:
            rmap.running("__plan__")
        if self.planning:
            plan_text = self._make_plan(inputs)
            if rmap:
                rmap.done("__plan__", output=(plan_text or "")[:300])
        elif rmap:
            rmap.done("__plan__", output="(planning disabled)")

        # resolve agent for a task by role or namespace.
        def resolve(task: Task) -> Optional[Agent]:
            if not task.agent:
                return None
            return roster.get(task.agent)

        state: dict[str, Any] = {}

        # hierarchical: a manager agent distributes work to the owner agents via
        # the internal delegation surface; each delegation actually executes the
        # owner agent's task and records a TaskOutcome for provenance.
        tasks = list(self.tasks)
        if self.process == "hierarchical":
            return self._run_hierarchical(tasks, roster, resolve, state,
                                          inputs, guards, rmap, result)

        # sequential with cache + optional parallel async tasks.
        from concurrent.futures import ThreadPoolExecutor
        executor = ThreadPoolExecutor(max_workers=max(4, len(tasks)))
        pending: list[tuple[Task, Any]] = []  # (task, future or None)

        for task in tasks:
            agent = resolve(task)
            if rmap:
                rmap.running(task.name)
            if task.async_execution:
                # resolve any previously-submitted async deps this task needs first
                self._join_needed(task, pending, state, result, rmap)
                fut = executor.submit(
                    self._run_task, task, agent, dict(state), inputs, guards)
                pending.append((task, fut))
                continue
            # resolve async deps this task depends on
            self._join_needed(task, pending, state, result, rmap)
            cached = self._cached(task, inputs)
            if cached is not None:
                outcome = cached
            else:
                outcome = self._run_task(task, agent, state, inputs, guards)
                self._cache_store(task, inputs, outcome)
            state[task.name] = outcome.output if outcome.ok else ""
            result.outcomes.append(outcome)
            if rmap:
                if outcome.blocked or not outcome.ok:
                    rmap.blocked(task.name,
                                 reason=outcome.blocked_reason or "task failed")
                else:
                    rmap.done(task.name, output=outcome.output[:300])

        for task, fut in pending:
            outcome = fut.result()
            state[task.name] = outcome.output if outcome.ok else ""
            result.outcomes.append(outcome)
            if rmap:
                if outcome.blocked or not outcome.ok:
                    rmap.blocked(task.name,
                                 reason=outcome.blocked_reason or "task failed")
                else:
                    rmap.done(task.name, output=outcome.output[:300])
        executor.shutdown(wait=True)

        self._invoke_task_callback(result)
        if self.guards and self.guards.sweep_after:
            self.guards.sweep()
        return result

    # -------------------------------------------------------------- planning
    def _make_plan(self, inputs: dict) -> str:
        brain = self._crew_brain()
        goal = "; ".join(
            f"{t.agent or 'member'} -> {t.expected_output}"
            for t in self.tasks) or self.name
        try:
            plan = brain.plan(goal, constraints=["complete every task"])
        except Exception as exc:
            return f"[plan error] {type(exc).__name__}: {exc}"
        return str(plan)[:4000]

    def _crew_brain(self):
        if self.brain is not None:
            return self.brain
        from .neural import CogBrain
        return CogBrain()

    def _manager_brain(self):
        llm = self.manager_llm
        if isinstance(llm, Agent):
            return llm.brain or self._crew_brain()
        if llm is not None:
            return llm
        return self._crew_brain()

    # ---------------------------------------------------------- hierarchical
    def _run_hierarchical(self, tasks, roster, resolve, state, inputs,
                          guards, rmap, result) -> CrewResult:
        """A manager agent distributes task work through the internal delegation
        surface; each delegation runs the owner agent's task and records a
        TaskOutcome so provenance is identical to a sequential crew run."""
        for task in tasks:
            if resolve(task) is None:
                raise ValueError(f"hierarchical task '{task.name}' needs an agent")

        manager = self.manager_agent or Agent(
            role=f"manager-{self.name}", goal=self.name,
            brain=self._manager_brain(),
            max_iter=max(20, len(tasks) * 4), allow_delegation=True)

        from .context import TaskContext
        mctx = TaskContext(
            task_name="manager", description=(
                f"Run the crew '{self.name}' as a manager: delegate every task "
                "below to the owner agent by capability, then write a final "
                f"summary.\n\nTASKS:\n" + "\n".join(
                    f"- {t.agent} shall {t.description}" for t in tasks)),
            expected_output="manager summary after all tasks are delegated",
            inputs=inputs, upstream={}, agent_identity=manager.identity(),
            memory_recall="", tools=manager.identity()["tools"],
            notes=f"process={self.process}")

        fanout = _CrewFanOut(self, tasks, resolve, state, inputs, guards,
                             rmap, result)
        manager.a2a = fanout

        loop_out = manager.kickoff(mctx, guards=guards)
        summary = loop_out.text

        # tasks not delegated by the manager are recorded as blocked (honest).
        for task in tasks:
            if task.name in fanout.done:
                continue
            if rmap:
                rmap.blocked(task.name, reason="manager did not delegate this task")
            result.outcomes.append(TaskOutcome(
                task_name=task.name, agent=resolve(task).role if resolve(task) else "",
                ok=False, output="", blocked=True,
                blocked_reason="manager did not delegate this task"))

        result.summary_output = summary
        result.outcomes = [o for o in result.outcomes if o.ok] + \
                          [o for o in result.outcomes if not o.ok]
        self._invoke_task_callback(result)
        if self.guards and self.guards.sweep_after:
            self.guards.sweep()
        return result

    # ------------------------------------------------------------- async join
    def _join_needed(self, task: Task, pending: list, state: dict,
                     result: CrewResult, rmap) -> None:
        """Block until every in-flight async task this task depends on is done."""
        deps = set(task.context or [])
        if not deps:
            return
        for t, fut in list(pending):
            if t.name in deps:
                outcome = fut.result()
                if outcome.ok:
                    state[t.name] = outcome.output
                result.outcomes.append(outcome)
                if rmap:
                    if outcome.blocked or not outcome.ok:
                        rmap.blocked(t.name, reason=outcome.blocked_reason or "task failed")
                    else:
                        rmap.done(t.name, output=outcome.output[:300])
                pending.remove((t, fut))

    # ---------------------------------------------------------------- caching
    def _cache_name(self, task: Task, inputs: dict) -> str:
        import hashlib, json
        payload = json.dumps({
            "name": task.name, "description": task.description,
            "expected_output": task.expected_output, "agent": task.agent,
            "output_file": task.output_file, "inputs": inputs,
            "process": self.process,
        }, sort_keys=True, default=str)
        return hashlib.sha1(payload.encode()).hexdigest()[:20]

    def _cached(self, task: Task, inputs: dict) -> Optional[TaskOutcome]:
        if not self.cache:
            return None
        try:
            rows = sub.recall(topic=f"mem20crewz-cache:{self._cache_name(task, inputs)}",
                              k=1)
        except Exception:
            return None
        for r in rows or []:
            if not isinstance(r, dict):
                continue
            content = r.get("content", "") or ""
            if content.startswith("CACHED:"):
                return TaskOutcome(
                    task_name=task.name,
                    agent=task.agent or "",
                    ok=True,
                    output=content[len("CACHED:"):][:6000],
                    memory_id=r.get("id") or r.get("fact_id"),
                )
        return None

    def _cache_store(self, task: Task, inputs: dict, outcome: TaskOutcome) -> None:
        if not self.cache or not outcome.ok:
            return
        try:
            sub.remember(
                topic=f"mem20crewz-cache:{self._cache_name(task, inputs)}",
                content=f"CACHED:{outcome.output[:4000]}",
                tags=["mem20crewz", "cache", self.name],
                actor=self.name, epistemic_status="observed",
                source=f"mem20crewz:cache:{self.name}")
        except Exception:
            pass

    # ------------------------------------------------------------ callbacks
    def _invoke_task_callback(self, result: CrewResult) -> None:
        if self.task_callback is None:
            return
        try:
            self.task_callback(result)
        except Exception:
            pass

    def _run_task(self, task: Task, agent: Optional[Agent], state: dict,
                  inputs: dict, guards: Guards) -> TaskOutcome:
        if agent is None:
            # no dedicated agent: fall back to a self-model-less task run
            # executed by a default "member" brain + generic skills.
            agent = Agent(role=f"member-{task.name}", goal=task.expected_output,
                          tools=[], max_iter=8)
            self.agents[task.name] = agent
        if self.step_callback is not None and task.step_callback is None:
            task.step_callback = self.step_callback
        return task.run(state, agent, inputs, guards=guards)

    # ----------------------------------------------------------------- util
    def agents_list(self) -> list[Agent]:
        return list({id(a): a for a in self.agents.values()}.values())


class _CrewFanOut:
    """Internal delegation surface for hierarchical crews.

    Each delegate(capability, message) resolves the owner agent for the first
    not-yet-delegated task assigned to that role, runs it, records the outcome,
    and returns the reply — so the manager's loop observes real sub-agent work.
    """

    def __init__(self, crew: "Crew", tasks, resolve, state, inputs,
                 guards, rmap, result) -> None:
        self.crew = crew
        self.tasks = list(tasks)
        self.resolve = resolve
        self.state = state
        self.inputs = inputs
        self.guards = guards
        self.rmap = rmap
        self.result = result
        self.done: set[str] = set()

    def fan_out(self, capability: str, message: str) -> dict:
        cap = capability.strip().lower()
        for task in self.tasks:
            if task.name in self.done:
                continue
            owner = self.resolve(task)
            owner_role = owner.role.lower() if owner else ""
            if cap not in (owner_role, task.agent.lower(),
                           getattr(owner, "namespace", "").lower()):
                continue
            outcome = self.crew._run_task(task, owner, self.state, self.inputs,
                                          self.guards)
            self.done.add(task.name)
            self.state[task.name] = outcome.output if outcome.ok else ""
            self.result.outcomes.append(outcome)
            if self.rmap:
                if outcome.blocked or not outcome.ok:
                    self.rmap.blocked(task.name, reason=outcome.blocked_reason or "failed")
                else:
                    self.rmap.done(task.name, output=outcome.output[:300])
            return {"results": [{"agent": (owner.role if owner else "?"),
                                 "reply": outcome.output[:3000]}]}
        return {"results": [{"agent": "manager", "reply":
            f"[delegation skipped: no outstanding task matches capability '{capability}']"}]}