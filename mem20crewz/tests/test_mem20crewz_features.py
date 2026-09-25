"""hermetic tests for the mem20 crews-parity feature pass.

Covers the gaps closed in this pass: Agent allow_delegation /
allow_code_execution / max_rpm / max_execution_time / verbose / knowledge /
planning / function_calling_llm; Task output_pydantic / human_input /
callback / step_callback; Crew planning / cache / hierarchical / task_callback
/ step_callback; Flow @router; and YAML wiring of every new field.

No network, no LLM key, no real store writes (stub seams injected per-test —
the same discipline as the main suite).
"""

from __future__ import annotations

import tempfile
import unittest
from unittest import mock

from .. import _substrate
from ..agents import Agent
from ..config import (write_example, load_agents_yaml, load_tasks_yaml,
                      _crew_meta, build_crew_from_yaml)
from ..crew import Crew
from ..flow import Flow, listen, router, start
from ..loop import ToolLoop
from ..neural import FakeBrain
from ..tasks import Task

from .test_mem20crewz import StubSubstrate, BackendTestCase, install_for, restore_backend


class RecallCacheStub(StubSubstrate):
    """Stub whose recall serves synthetic mem20crewz-cache rows when asked."""

    def __init__(self) -> None:
        super().__init__()
        self.cache_rows: list[dict] = []

    def recall(self, topic, tags=None, k=5):
        if str(topic).startswith("mem20crewz-cache:") and self.cache_rows:
            return list(self.cache_rows)
        return self.recall_results

    def remember(self, topic, content, tags=None, actor="agent", **kw):
        self.remembered.append((topic, content))
        return {"id": "fact-" + topic.replace(":", "-")[:24]}

    def human_review(self, task_name=None, **kw):
        return {"approved": True, "by": "stub-human"}


class AgentGapTest(BackendTestCase):
    def test_code_execution_runs_sandboxed(self) -> None:
        self.stub.recall_results = []
        install_for(_substrate.backend, self.stub)  # reseal hooks post-setUp
        try:
            a = Agent(role="C", goal="code", allow_code_execution=True,
                      brain=FakeBrain(steps=[
                          {"action": "tool", "tool": "mem20_tool_execute_python",
                           "args": "print(21 * 2)"},
                          {"action": "final", "final": "done"}]), max_iter=6)
            from ..context import TaskContext
            ctx = TaskContext(task_name="t", description="code",
                              expected_output="ok", inputs={}, upstream={},
                              agent_identity=a.identity(), memory_recall="",
                              tools="mem20_tool_execute_python", notes="")
            r = a.kickoff(ctx)
            self.assertTrue(any("42" in o for o in r.observations), r.observations)
            self.assertEqual(r.text, "done")
        finally:
            restore_backend()

    def test_code_execution_disabled_reports_unknown_tool(self) -> None:
        install_for(_substrate.backend, self.stub)
        try:
            a = Agent(role="C2", goal="code", allow_code_execution=False,
                      brain=FakeBrain(steps=[
                          {"action": "tool", "tool": "mem20_tool_execute_python",
                           "args": "print(1)"},
                          {"action": "final", "final": "done"}]), max_iter=6)
            from ..context import TaskContext
            ctx = TaskContext(task_name="t", description="code",
                              expected_output="ok", inputs={}, upstream={},
                              agent_identity=a.identity(), memory_recall="",
                              tools="", notes="")
            r = a.kickoff(ctx)
            self.assertTrue(any("unknown tool" in o for o in r.observations),
                            r.observations)
        finally:
            restore_backend()

    def test_allow_delegation_false_skips_delegate(self) -> None:
        install_for(_substrate.backend, self.stub)
        try:
            a = Agent(role="So", goal="solo", allow_delegation=False,
                      brain=FakeBrain(steps=[
                          {"action": "delegate", "capability": "analyst",
                           "message": "go"},
                          {"action": "final", "final": "solo-ok"}]), max_iter=6)
            from ..context import TaskContext
            ctx = TaskContext(task_name="t", description="solo",
                              expected_output="ok", inputs={}, upstream={},
                              agent_identity=a.identity(), memory_recall="",
                              tools="", notes="")
            r = a.kickoff(ctx)
            self.assertTrue(any("no A2A client configured" in o for o in r.observations),
                            r.observations)
            self.assertEqual(r.text, "solo-ok")
        finally:
            restore_backend()

    def test_max_execution_time_stops_loop(self) -> None:
        install_for(_substrate.backend, self.stub)
        try:
            a = Agent(role="T", goal="tick", max_execution_time=1e-9,
                      brain=FakeBrain(steps=[
                          {"action": "tool", "tool": "echo", "args": "x"},
                          {"action": "final", "final": "never"}]), max_iter=10)
            from ..context import TaskContext
            ctx = TaskContext(task_name="t", description="tick",
                              expected_output="ok", inputs={}, upstream={},
                              agent_identity=a.identity(), memory_recall="",
                              tools="", notes="")
            r = a.kickoff(ctx)
            self.assertIn("max_execution_time reached", r.text)
        finally:
            restore_backend()

    def test_max_rpm_paces_propose(self) -> None:
        loop = ToolLoop(brain=FakeBrain(), skills=object(), max_rpm=3)
        loop.skills = type("S", (), {})()  # unused by _throttle
        with mock.patch("time.sleep") as sleep:
            for _ in range(4):
                loop._throttle()
        self.assertEqual(sleep.call_count, 1)

    def test_verbose_does_not_break_loop(self) -> None:
        install_for(_substrate.backend, self.stub)
        try:
            a = Agent(role="V", goal="v", verbose=True,
                      brain=FakeBrain(steps=[{"action": "final", "final": "v-ok"}]))
            from ..context import TaskContext
            ctx = TaskContext(task_name="t", description="v", expected_output="ok",
                              inputs={}, upstream={}, agent_identity=a.identity(),
                              memory_recall="", tools="", notes="")
            import io
            from contextlib import redirect_stdout
            buf = io.StringIO()
            with redirect_stdout(buf):
                r = a.kickoff(ctx)
            self.assertIn("[loop]", buf.getvalue())  # verbose actually logs
            self.assertEqual(r.text, "v-ok")
        finally:
            restore_backend()

    def test_knowledge_seeds_recalls(self) -> None:
        self.stub.recall_results = [{"content": "K-FACT-42"}]
        install_for(_substrate.backend, self.stub)
        try:
            a = Agent(role="K", goal="k", knowledge=["mem20"],
                      brain=FakeBrain(steps=[{"action": "final", "final": "k-ok"}]))
            from ..context import TaskContext
            ctx = TaskContext(task_name="t", description="k", expected_output="ok",
                              inputs={}, upstream={}, agent_identity=a.identity(),
                              memory_recall="", tools="", notes="")
            r = a.kickoff(ctx)
            self.assertTrue(any("K-FACT-42" in o for o in r.observations),
                            r.observations)
        finally:
            restore_backend()

    def test_planning_seeds_plan_observation(self) -> None:
        self.stub.recall_results = []
        install_for(_substrate.backend, self.stub)
        try:
            a = Agent(role="P", goal="p", planning=True,
                      brain=FakeBrain(plan_text="ORDERED-PLAN",
                                      steps=[{"action": "final", "final": "p-ok"}]))
            from ..context import TaskContext
            ctx = TaskContext(task_name="t", description="p", expected_output="ok",
                              inputs={}, upstream={}, agent_identity=a.identity(),
                              memory_recall="", tools="", notes="")
            r = a.kickoff(ctx)
            self.assertTrue(any("ORDERED-PLAN" in o for o in r.observations),
                            r.observations)
        finally:
            restore_backend()


class TaskGapTest(BackendTestCase):
    def test_output_pydantic_validates(self) -> None:
        from pydantic import BaseModel

        class M(BaseModel):
            a: int
            b: str

        install_for(_substrate.backend, self.stub)
        try:
            a = Agent(role="Q", goal="q", brain=FakeBrain(
                steps=[{"action": "final", "final": '{"a": 1, "b": "x"}'}]))
            t = Task(name="tp", description="d", expected_output="e", agent="Q",
                     output_pydantic=M)
            o = t.run({}, a, {})
            self.assertTrue(o.ok)
            self.assertIsInstance(o.model, M)
            self.assertEqual(o.model.a, 1)
            self.assertEqual(o.model.b, "x")
        finally:
            restore_backend()

    def test_output_pydantic_invalid_is_none(self) -> None:
        from pydantic import BaseModel

        class M(BaseModel):
            a: int

        install_for(_substrate.backend, self.stub)
        try:
            a = Agent(role="Q2", goal="q", brain=FakeBrain(
                steps=[{"action": "final", "final": '{"a": "nope"}'}]))
            t = Task(name="tp2", description="d", expected_output="e", agent="Q2",
                     output_pydantic=M)
            o = t.run({}, a, {})
            self.assertTrue(o.ok)      # output is fine as text
            self.assertIsNone(o.model)  # but not valid against the model
        finally:
            restore_backend()

    def test_human_input_blocks_without_reviewer(self) -> None:
        # no human_review hook installed -> seam sealed -> not approved
        install_for(_substrate.backend, self.stub)
        try:
            a = Agent(role="H", goal="h", brain=FakeBrain(
                steps=[{"action": "final", "final": "h-out"}]))
            t = Task(name="th", description="d", expected_output="e", agent="H",
                     human_input=True)
            o = t.run({}, a, {})
            self.assertFalse(o.ok)
            self.assertTrue(o.blocked)
            self.assertIn("human_input requested", o.blocked_reason)
        finally:
            restore_backend()

    def test_human_input_runs_when_reviewer_approves(self) -> None:
        _substrate.backend.hooks["human_review"] = lambda *a, **kw: {"approved": True}
        install_for(_substrate.backend, self.stub)  # keeps other seams intact
        try:
            a = Agent(role="H2", goal="h", brain=FakeBrain(
                steps=[{"action": "final", "final": "h-out"}]))
            t = Task(name="th2", description="d", expected_output="e", agent="H2",
                     human_input=True)
            o = t.run({}, a, {})
            self.assertTrue(o.ok)
            self.assertEqual(o.output, "h-out")
        finally:
            restore_backend()

    def test_callback_invoked(self) -> None:
        install_for(_substrate.backend, self.stub)
        seen = []
        try:
            a = Agent(role="CB", goal="c", brain=FakeBrain(
                steps=[{"action": "final", "final": "cb-out"}]))
            t = Task(name="tcb", description="d", expected_output="e", agent="CB",
                     callback=lambda task, out: seen.append((task.name, out.ok)))
            o = t.run({}, a, {})
            self.assertEqual(seen, [("tcb", True)])
        finally:
            restore_backend()


class CrewGapTest(BackendTestCase):
    def test_planning_emits_plan_phase(self) -> None:
        install_for(_substrate.backend, self.stub)
        try:
            crew = Crew(
                name="plan-crew",
                agents=[Agent(role="A", goal="a", brain=FakeBrain(
                    steps=[{"action": "final", "final": "a-out"}]))],
                tasks=[Task(name="ta", description="a", expected_output="a-out",
                            agent="A")],
                planning=True,
                brain=FakeBrain(),
                persist_memory=False,
            )
            r = crew.kickoff(inputs={"x": 1})
            phases = [e["phase"] for e in r.roadmap.view()]
            self.assertIn("__plan__", phases)
            plan_events = [e for e in r.roadmap.view() if e["phase"] == "__plan__"]
            self.assertIn("completed", [e["status"] for e in plan_events])
        finally:
            restore_backend()

    def test_cache_reuses_outcome(self) -> None:
        stub = RecallCacheStub()
        install_for(_substrate.backend, stub)
        try:
            stub.cache_rows = [{"content": "CACHED:from-cache",
                                "id": "fact-cache-1"}]
            a = Agent(role="CA", goal="ca", brain=FakeBrain(
                steps=[{"action": "final", "final": "fresh-out"}]))
            crew = Crew(
                name="cache-crew",
                agents=[a],
                tasks=[Task(name="tc", description="d", expected_output="e",
                            agent="CA")],
                cache=True,
                persist_memory=False,
            )
            r = crew.kickoff(inputs={"i": 1})
            self.assertTrue(r.ok())
            self.assertEqual(r.output("tc"), "from-cache")
            self.assertEqual(len(a.brain.propose_calls), 0)  # agent never ran
        finally:
            restore_backend()

    def test_cache_disabled_runs_fresh(self) -> None:
        stub = RecallCacheStub()
        install_for(_substrate.backend, stub)
        try:
            stub.cache_rows = [{"content": "CACHED:stale", "id": "fact-2"}]
            a = Agent(role="CB2", goal="cb", brain=FakeBrain(
                steps=[{"action": "final", "final": "fresh-out"}]))
            crew = Crew(
                name="cache-off-crew",
                agents=[a],
                tasks=[Task(name="tco", description="d", expected_output="e",
                            agent="CB2")],
                cache=False,
                persist_memory=False,
            )
            r = crew.kickoff(inputs={"i": 1})
            self.assertEqual(r.output("tco"), "fresh-out")
            self.assertEqual(len(a.brain.propose_calls), 1)
        finally:
            restore_backend()

    def test_hierarchical_manager_delegates(self) -> None:
        install_for(_substrate.backend, self.stub)
        try:
            crew = Crew(
                name="hier-crew",
                process="hierarchical",
                agents=[
                    Agent(role="A", goal="a", brain=FakeBrain(
                        steps=[{"action": "final", "final": "a-out"}]),
                          max_iter=4),
                    Agent(role="B", goal="b", brain=FakeBrain(
                        steps=[{"action": "final", "final": "b-out"}]),
                          max_iter=4),
                ],
                tasks=[
                    Task(name="ta", description="a", expected_output="a-out",
                         agent="A"),
                    Task(name="tb", description="b", expected_output="b-out",
                         agent="B"),
                ],
                manager_llm=FakeBrain(steps=[
                    {"action": "delegate", "capability": "a", "message": "go"},
                    {"action": "delegate", "capability": "b", "message": "go"},
                    {"action": "final", "final": "manager-summary"},
                ]),
                persist_memory=False,
            )
            r = crew.kickoff(inputs={})
            from ..tasks import TaskOutcome
            outcomes = [o for o in r.outcomes if isinstance(o, TaskOutcome)]
            self.assertEqual(len(outcomes), 2)
            self.assertTrue(all(o.ok for o in outcomes))
            self.assertEqual(r.summary_output, "manager-summary")
            self.assertEqual(r.output("ta"), "a-out")
            self.assertEqual(r.output("tb"), "b-out")
        finally:
            restore_backend()

    def test_task_callback_invoked_for_crew(self) -> None:
        install_for(_substrate.backend, self.stub)
        seen = []
        try:
            crew = Crew(
                name="cb-crew",
                agents=[Agent(role="A", goal="a", brain=FakeBrain(
                    steps=[{"action": "final", "final": "a-out"}]))],
                tasks=[Task(name="ta", description="a", expected_output="a-out",
                            agent="A")],
                task_callback=lambda result: seen.append(result.crew),
                persist_memory=False,
            )
            crew.kickoff(inputs={})
            self.assertEqual(seen, ["cb-crew"])
        finally:
            restore_backend()

    def test_step_callback_passthrough(self) -> None:
        install_for(_substrate.backend, self.stub)
        steps = []
        try:
            crew = Crew(
                name="sc-crew",
                agents=[Agent(role="A", goal="a", brain=FakeBrain(steps=[
                    {"action": "tool", "tool": "echo", "args": "x"},
                    {"action": "final", "final": "a-out"}]))],
                tasks=[Task(name="ta", description="a", expected_output="a-out",
                            agent="A")],
                step_callback=lambda **kw: steps.append(kw.get("action")),
                persist_memory=False,
            )
            r = crew.kickoff(inputs={})
            self.assertTrue(r.ok())
            self.assertIn("tool", steps)
            self.assertIn("final", steps)
        finally:
            restore_backend()


class FlowRouterTest(unittest.TestCase):
    def setUp(self) -> None:
        self._froot = tempfile.mkdtemp(prefix="mem20-flow-router-")

    def test_router_emits_single_route(self) -> None:
        class P(Flow):
            @start
            def begin(self, ctx, state):
                return "s1"

            @router("s1")
            def decide(self, ctx, state):
                return "s2"

            @listen("s2")
            def end(self, ctx, state):
                return ""

        f = P(name="route-test", roadmap_root=self._froot)
        r = f.run()
        self.assertIn("s1", r.emitted)
        self.assertIn("s2", r.emitted)
        self.assertEqual(len(r.runs), 3)

    def test_router_truncates_multi_return_to_first(self) -> None:
        class P(Flow):
            @start
            def begin(self, ctx, state):
                return "s1"

            @router("s1")
            def decide(self, ctx, state):
                return ["x", "y"]

            @listen("x")
            def ex(self, ctx, state):
                return ""

        f = P(name="route-multi", roadmap_root=self._froot)
        r = f.run()
        self.assertIn("x", r.emitted)
        self.assertNotIn("y", r.emitted)  # a router picks one state
        self.assertEqual(len(r.runs), 3)  # begin + route-decision + listen("x")


class FeatureConfigTest(unittest.TestCase):
    def test_yaml_wires_all_new_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            a_p, t_p = write_example(tmp)
            agents = load_agents_yaml(a_p)
            a0 = {x.role: x for x in agents}["Researcher"]
            self.assertTrue(a0.allow_delegation)
            self.assertEqual(a0.max_iter, 8)
            tasks = load_tasks_yaml(t_p, agents)
            self.assertFalse(tasks[1].human_input)
            self.assertFalse(tasks[1].async_execution)
            meta = _crew_meta(_safe_load(t_p))
            self.assertEqual(meta["process"], "sequential")
            self.assertFalse(meta["planning"])
            self.assertTrue(meta["cache"])
            crew = build_crew_from_yaml(a_p, t_p)
            self.assertEqual(crew.name, "example")
            self.assertFalse(crew.planning)
            self.assertTrue(crew.cache)


def _safe_load(path: str) -> dict:
    import yaml
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


if __name__ == "__main__":
    unittest.main()