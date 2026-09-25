"""mem20crewz test suite — hermetic + deterministic.

No network, no LLM key, no mem20 store writes (vetted: guards use stub seams
unless MEM20CREWZ_BACKEND=native). Backend hooks are injected per-test.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .. import _substrate
from .._substrate import Backend
from ..agents import Agent
from ..a2a import A2AClient, _extract_text, _unwrap
from ..config import (write_example, load_agents_yaml, load_tasks_yaml,
                      build_crew, build_crew_from_yaml)
from ..context import TaskContext, assemble, interpolate
from ..crew import Crew
from ..flow import Flow, FlowResult, listen, listen_once, start
from ..guardrails import GuardrailBlocked, Guards
from ..loop import ToolLoop
from ..neural import Brain, CogBrain, FakeBrain
from ..roadmap import Roadmap
from ..skills import Skills
from ..tasks import Task

TOPIC = "mem20crewz-unit"


HOOKS = ("recall", "remember", "procedural_list", "procedural_get",
         "procedural_execute", "plan_guard", "veto", "quarantine")


class StubSubstrate:
    def __init__(self) -> None:
        self.recall_results = []
        self.planned_blocks = False
        self.vetoed = False
        self.procedural_skills = {
            "echo": {"name": "echo", "description": "echo back the arg",
                     "steps": ["echo the argument"]},
        }
        self.remembered = []

    def recall(self, topic, tags=None, k=5):
        return self.recall_results

    def remember(self, topic, content, tags=None, actor="agent"):
        self.remembered.append((topic, content))
        return {"id": "fact-" + uuid.uuid4().hex[:8]}

    def procedural_list(self, category=None):
        return [{"name": n, "description": v.get("description", "")}
                for n, v in self.procedural_skills.items()]

    def procedural_get(self, name):
        return self.procedural_skills.get(name)

    def procedural_execute(self, name, context=None):
        if name == "echo":
            return {"ok": True, "output": "echo:" + str((context or {}).get("arg", ""))}
        return {"ok": False, "output": "unknown", "error": "no skill"}

    def plan_guard(self, fact_ids, actor=None):
        if self.planned_blocks:
            return {"blocked": True, "reason": "plan blocked (stub)"}
        return {"blocked": False}

    def veto(self, fact_ids, actor=None):
        if self.vetoed:
            return {"vetoed": True, "reason": "rests on simulated beliefs (stub)"}
        return {"vetoed": False, "reason": ""}

    def quarantine(self, actor=None):
        return {"quarantined": []}


class BackendTestCase(unittest.TestCase):
    """Seals the SHARED singleton backend (the one modules bind via
    `from ._substrate import backend as sub`) and injects stub hooks.
    Restores both after each test so no real store is ever touched."""

    def setUp(self) -> None:
        b = _substrate.backend
        self._orig_use = b.use_substrate
        self._orig_hooks = {k: v for k, v in b.hooks.items()}
        b.use_substrate = False
        b.hooks = {}
        self.stub = StubSubstrate()
        install_stub(self.stub)

    def tearDown(self) -> None:
        b = _substrate.backend
        b.hooks = self._orig_hooks
        b.use_substrate = self._orig_use


def install_stub(stub: StubSubstrate) -> None:
    install_for(_substrate.backend, stub)


def install_for(backend, stub: StubSubstrate) -> None:
    for key in HOOKS:
        backend.hooks[key] = getattr(stub, key)


def set_stub(stub: StubSubstrate) -> None:
    install_stub(stub)


def restore_backend() -> None:
    from .. import _substrate as sub
    sub.backend.hooks = {}
    sub.backend.use_substrate = sub._BACKEND != "fake"


class SubstrateTest(unittest.TestCase):
    def test_lazy_imports(self) -> None:
        b = _substrate.Backend(use_substrate=False)
        self.assertTrue(callable(b.recall))
        self.assertTrue(callable(b.remember))
        self.assertTrue(callable(b.procedural_list))
        self.assertTrue(callable(b.procedural_execute))
        self.assertTrue(callable(b.plan_guard))
        self.assertTrue(callable(b.veto))
        self.assertTrue(callable(b.quarantine))
        self.assertIsNotNone(b.cog)  # cog imports without any key

    def test_sealed_raises_without_hook(self) -> None:
        b = _substrate.Backend(use_substrate=False)
        with self.assertRaises(_substrate.BackendSealed):
            b.recall("x")
        with self.assertRaises(_substrate.BackendSealed):
            b.plan_guard([1])

    def test_hook_overrides_seal(self) -> None:
        stub = StubSubstrate()
        stub.recall_results = [{"ts": "2026-01-01", "content": "memory-line"}]
        b = _substrate.Backend(use_substrate=False)
        install_for(b, stub)
        rec = b.recall("x")
        self.assertEqual(rec[0]["content"], "memory-line")
        pg = b.plan_guard([1])
        self.assertFalse(pg.get("blocked"))


class SkillsTest(unittest.TestCase):
    def test_callable_and_procedural(self) -> None:
        stub = StubSubstrate()
        set_stub(stub)
        try:
            s = Skills()
            s.add_callable("up", lambda a: a.upper())
            s.add_procedural("echo")
            self.assertIn("up", s.names())
            self.assertIn("echo", s.names())
            r1 = s.execute("up", "hello")
            self.assertTrue(r1["ok"])
            self.assertEqual(r1["output"], "HELLO")
            r2 = s.execute("echo", "hello")
            self.assertTrue(r2["ok"])
            self.assertEqual(r2["output"], "echo:hello")
        finally:
            restore_backend()

    def test_unknown_tool_is_an_error_result(self) -> None:
        stub = StubSubstrate()  # empty inventory — no real store lookups
        set_stub(stub)
        try:
            s = Skills()
            r = s.execute("nope", "")
            self.assertFalse(r["ok"])
            self.assertIn("unknown tool", r["output"])
        finally:
            restore_backend()


class ContextTest(unittest.TestCase):
    def test_interpolation(self) -> None:
        self.assertEqual(interpolate("build {x}", {"x": "yes"}), "build yes")

    def test_assemble_prompt(self) -> None:
        stub = StubSubstrate()
        set_stub(stub)
        try:
            task = Task(name="t1", description="do {topic}",
                        expected_output="a plan for {topic}", agent="Researcher")
            agent = Agent(role="Researcher", goal="research",
                          capabilities=["reason"], values=["honest"])
            ctx = assemble(task, agent, {"up1": "prev result"}, {"topic": TOPIC})
            self.assertIsInstance(ctx, TaskContext)
            self.assertIn("do mem20crewz-unit", ctx.prompt())
            self.assertIn("prev result", ctx.prompt())
            self.assertIn("reason", ctx.prompt())
            self.assertEqual(ctx.inputs["topic"], TOPIC)
            self.assertIn("a plan for mem20crewz-unit", ctx.prompt())
        finally:
            restore_backend()


class GuardrailsTest(unittest.TestCase):
    def test_plan_gate_blocks(self) -> None:
        stub = StubSubstrate()
        stub.planned_blocks = True
        set_stub(stub)
        try:
            g = Guards(actor="x")
            with self.assertRaises(GuardrailBlocked):
                g.gate([1, 2])
        finally:
            restore_backend()

    def test_veto_require(self) -> None:
        stub = StubSubstrate()
        stub.vetoed = True
        set_stub(stub)
        try:
            g = Guards()
            with self.assertRaises(GuardrailBlocked):
                g.require_clearance([99])
        finally:
            restore_backend()

    def test_sweep(self) -> None:
        stub = StubSubstrate()
        set_stub(stub)
        try:
            g = Guards()
            r = g.sweep()
            self.assertEqual(r, {"quarantined": []})
        finally:
            restore_backend()


class ToolLoopTest(unittest.TestCase):
    def test_tool_then_final(self) -> None:
        stub = StubSubstrate()
        set_stub(stub)
        try:
            brain = FakeBrain(steps=[
                {"action": "tool", "tool": "echo", "args": "hi"},
                {"action": "final", "final": "answer"},
            ])
            g = Guards(actor="x", enforce_veto=False, sweep_after=False)
            s = Skills()
            s.add_procedural("echo")
            loop = ToolLoop(brain=brain, skills=s, guards=g, max_iter=10)
            r = loop.run("goal")
            self.assertEqual(r.text, "answer")
            self.assertEqual(r.iterations, 2)
            self.assertIn("echo:hi", " | ".join(r.observations))
            self.assertEqual(len(brain.propose_calls), 2)
        finally:
            restore_backend()

    def test_delegate_with_fake_a2a(self) -> None:
        stub = StubSubstrate()
        set_stub(stub)
        try:
            brain = FakeBrain(steps=[
                {"action": "delegate", "capability": "analyst", "message": "please"},
                {"action": "final", "final": "ok"},
            ])
            class FakeA2A:
                def fan_out(self, capability, message):
                    return {"results": [{"agent": "a", "reply": "done-x"}]}
            s = Skills()
            loop = ToolLoop(brain=brain, skills=s, guards=Guards(),
                            a2a=FakeA2A())
            r = loop.run("goal")
            self.assertEqual(r.text, "ok")
            self.assertIn("done-x", " | ".join(r.observations))
        finally:
            restore_backend()

    def test_brain_error_becomes_final(self) -> None:
        stub = StubSubstrate()
        set_stub(stub)
        try:
            class Boom(Brain):
                name = "boom"
                def propose(self, goal, tools_blob, observations,
                            require_tool_before_final=False):
                    raise RuntimeError("kaboom")
            s = Skills()
            loop = ToolLoop(brain=Boom(), skills=s, guards=Guards(), max_iter=3)
            r = loop.run("g")
            self.assertIn("kaboom", r.text)
        finally:
            restore_backend()

    def test_max_iter(self) -> None:
        stub = StubSubstrate()
        set_stub(stub)
        try:
            brain = FakeBrain(steps=[
                {"action": "tool", "tool": "echo", "args": "x"} for _ in range(5)
            ])
            s = Skills()
            s.add_procedural("echo")
            loop = ToolLoop(brain=brain, skills=s, guards=Guards(), max_iter=3)
            r = loop.run("g")
            self.assertIn("max_iter", r.text)
        finally:
            restore_backend()


class AgentsTest(BackendTestCase):
    def test_identity_and_persist(self) -> None:
        a = Agent(role="Boss", goal="g", backstory="b",
                  capabilities=["reason"], values=["vigor"])
        d = a.identity()
        self.assertEqual(d["role"], "Boss")
        self.assertIn("boss", a.namespace)
        self.assertEqual(len(a.namespace), len(a.namespace))
        rid = a.persist_identity()
        self.assertTrue(isinstance(rid, dict))

    def test_kickoff_assembles_and_executes(self) -> None:
        stub = StubSubstrate()
        set_stub(stub)
        try:
            a = Agent(role="Researcher", goal="g", brain=FakeBrain(
                steps=[{"action": "final", "final": "done-research"}]))
            t = Task(name="t1", description="do {topic}",
                     expected_output="ok {topic}", agent="Researcher")
            task_ctx = assemble(t, a, {}, {"topic": TOPIC})
            r = a.kickoff(task_ctx)
            self.assertEqual(r.text, "done-research")
        finally:
            restore_backend()


class TaskTest(BackendTestCase):
    def test_run_output_json_and_file(self) -> None:
        stub = StubSubstrate()
        set_stub(stub)
        try:
            a = Agent(role="Q", goal="q", brain=FakeBrain(
                steps=[{"action": "final", "final": '{"a": 1}'}]))
            with tempfile.TemporaryDirectory() as tmp:
                t = Task(name="tj", description="d", expected_output="e",
                         agent="Q", output_json=True,
                         output_file=os.path.join(tmp, "o.json"))
                o = t.run({}, a, {})
                self.assertTrue(o.ok)
                self.assertEqual(o.json_output, {"a": 1})
                self.assertTrue(os.path.exists(os.path.join(tmp, "o.json")))
                with open(os.path.join(tmp, "o.json")) as fh:
                    self.assertEqual(json.load(fh), {"a": 1})
        finally:
            restore_backend()

    def test_run_guarded_blocked(self) -> None:
        stub = StubSubstrate()
        stub.planned_blocks = True
        set_stub(stub)
        try:
            a = Agent(role="Q", goal="q")
            t = Task(name="tb", description="d", expected_output="e", agent="Q")
            o = t.run({}, a, {})
            self.assertFalse(o.ok)
            self.assertTrue(o.blocked)
            self.assertIn("plan blocked", o.blocked_reason)
        finally:
            restore_backend()


class CrewTest(BackendTestCase):
    def test_kickoff_sequential_roadmap(self) -> None:
        stub = StubSubstrate()
        set_stub(stub)
        try:
            writer_step = {"action": "final", "final": "writer-out"}
            crew = Crew(
                name="unit-crew",
                agents=[
                    Agent(role="A", goal="a", brain=FakeBrain(
                        steps=[{"action": "final", "final": "a-out"}]),
                          max_iter=4),
                    Agent(role="B", goal="b", brain=FakeBrain(steps=[writer_step]),
                          max_iter=4),
                ],
                tasks=[
                    Task(name="ta", description="a", expected_output="a-out",
                         agent="A"),
                    Task(name="tb", description="b", expected_output="b-out",
                         agent="B", context=["ta"]),
                ],
                persist_memory=False,
            )
            r = crew.kickoff(inputs={"x": 1})
            self.assertTrue(r.ok())
            self.assertEqual(r.output("ta"), "a-out")
            self.assertEqual(r.output("tb"), "writer-out")
            self.assertIsNotNone(r.roadmap)
            phases = [e["phase"] for e in r.roadmap.view()]
            self.assertIn("ta", phases)
            self.assertIn("tb", phases)
            ta_status = [e["status"] for e in r.roadmap.view() if e["phase"] == "ta"]
            self.assertIn("completed", ta_status)
            # task context must carry upstream output
            ctx = r.outcomes[1].context
            upstream = ctx["upstream"]
            self.assertEqual(upstream["ta"], "a-out")
        finally:
            restore_backend()


class FlowTest(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile
        self._froot = tempfile.mkdtemp(prefix="mem20-flow-")

    def test_class_level_start_listen(self) -> None:
        class P(Flow):
            @start
            def begin(self, ctx, state):
                return "m1"

            @listen("m1")
            def mid(self, ctx, state):
                return "m2"

            @listen("m2")
            def end(self, ctx, state):
                return ""

        f = P(name="p-test", roadmap_root=self._froot)
        r = f.run(inputs={"topic": "t"})
        self.assertIn("m1", r.emitted)
        self.assertIn("m2", r.emitted)
        self.assertEqual(len(r.runs), 3)
        phases = [e["phase"] for e in r.roadmap.view()]
        # each handler leaves in_progress then completed: begin,begin,mid,mid,end,end
        self.assertEqual(phases, ["begin", "begin", "mid", "mid", "end", "end"])
        statuses = [e["status"] for e in r.roadmap.view()]
        self.assertEqual(statuses, ["in_progress", "completed"] * 3)

    def test_instance_style(self) -> None:
        def begin(ctx, state):
            return "s1"

        def after(ctx, state):
            return ""

        f = Flow(name="f-inst", roadmap_root=self._froot)
        f.start()(begin)
        f.listen("s1")(after)
        r = f.run()
        self.assertIn("s1", r.emitted)
        self.assertEqual(len(r.runs), 2)

    def test_emit_and_listen_once(self) -> None:
        class E(Flow):
            @start
            def s(self, ctx, state):
                self.emit("a", "b")
                return ""

            @listen_once("a")
            def ha(self, ctx, state):
                self.emit("a")  # would re-trigger, but once fires a single time

        e = E(name="e", roadmap_root=self._froot)
        r = e.run()
        self.assertIn("a", r.emitted)
        self.assertIn("b", r.emitted)
        counts = [x["handler"] for x in r.runs].count("ha")
        self.assertEqual(counts, 1)


class A2ATest(unittest.TestCase):
    def _serve(self, reply_text: str, reply_is_text: bool = True) -> str:
        """Loopback A2A JSON-RPC server (protocol-compliant envelope)."""
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                body = json.dumps({
                    "name": "loop",
                    "url": "http://127.0.0.1:%d" % self.server.server_address[1],
                    "version": "0.2.0",
                    "capabilities": ["advertise"],
                    "skills": [],
                    "supportedInterfaces": {"jsonrpc": "*"},
                }).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(length)
                req = json.loads(raw)
                task = {"id": "task-1", "status": {"state": "TASK_STATE_COMPLETED"}}
                if reply_is_text:
                    task["status"]["message"] = {"role": "ROLE_AGENT",
                                                 "parts": [{"text": reply_text,
                                                            "mediaType": "text/plain"}]}
                else:
                    task["artifacts"] = [{"name": "out",
                                          "parts": [{"text": reply_text,
                                                     "mediaType": "text/plain"}]}]
                resp = {"jsonrpc": "2.0", "id": req.get("id"),
                        "result": {"task": task}}
                body = json.dumps(resp).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):  # silence
                pass

        srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=srv.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(srv.shutdown)
        self.addCleanup(srv.server_close)
        return "http://127.0.0.1:%d" % srv.server_address[1]

    def test_parse_helpers(self) -> None:
        payload = {"task": {"status": {"message": {"parts": [{"text": "hi"}]}}}}
        self.assertEqual(_unwrap(payload), payload["task"])
        self.assertEqual(_extract_text(payload["task"]), "hi")
        self.assertEqual(_extract_text({"artifacts": [
            {"parts": [{"kind": "data", "data": {"x": 1}}]}]}), '{"x": 1}')

    def test_discover_and_call_loopback(self) -> None:
        url = self._serve("hello-from-peer", reply_is_text=True)
        client = A2AClient(peers={"loop": {"url": url, "capabilities": ["advertise"]}},
                           timeout=10)
        card = client.discover("loop")
        self.assertEqual(card["name"], "loop")
        res = client.call("loop", "ping")
        self.assertEqual(res["reply"], "hello-from-peer")
        self.assertEqual(res["state"], "completed")

    def test_artifact_reply(self) -> None:
        url = self._serve("artifact-output", reply_is_text=False)
        client = A2AClient(peers={"loop": {"url": url, "capabilities": []}})
        res = client.call("loop", "ping")
        self.assertEqual(res["reply"], "artifact-output")

    def test_fan_out_parallel_capability_match(self) -> None:
        # one matching peer (capability advertise) over the loopback server
        url = self._serve("fan-reply")
        client = A2AClient(peers={
            "loop": {"url": url, "capabilities": ["advertise"]},
            "other": {"url": "http://127.0.0.1:1", "capabilities": ["research"]},
        })
        result = client.fan_out("advertise", "hello", mode="parallel")
        self.assertEqual(result["matched"], ["loop"])
        self.assertEqual(len(result["results"]), 1)
        self.assertEqual(result["results"][0]["reply"], "fan-reply")

    def test_unknown_peer_raises(self) -> None:
        client = A2AClient(peers={})
        with self.assertRaises(Exception):
            client.call("ghost", "hi")


class RoadmapTest(unittest.TestCase):
    def test_persisted_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            r = Roadmap("rm-test", root_dir=tmp)
            r.running("p1")
            r.done("p1")
            r.blocked("p2", "nope")
            view = r.view()
            self.assertEqual(len(view), 3)
            self.assertEqual(view[0]["phase"], "p1")
            self.assertEqual(view[0]["status"], "in_progress")
            self.assertEqual(view[2]["status"], "blocked")
            self.assertTrue(os.path.exists(os.path.join(tmp, "rm-test.jsonl")))


class ConfigTest(unittest.TestCase):
    def test_yaml_roundtrip_and_crew(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = write_example(tmp)
            agents = load_agents_yaml(paths[0])
            self.assertEqual(len(agents), 2)
            self.assertEqual(agents[0].role, "Researcher")
            tasks = load_tasks_yaml(paths[1], agents)
            self.assertEqual(len(tasks), 2)
            self.assertEqual(tasks[0].agent, "Researcher")
            self.assertEqual(tasks[1].context, ["research_step"])
            crew = build_crew("example", agents, tasks)
            self.assertEqual(crew.name, "example")
            # resolve roles
            self.assertIn("Researcher", crew.agents)
            self.assertIn("Writer", crew.agents)


class IntegrationDeterministicTest(unittest.TestCase):
    def test_end_to_end_crew_flow_demo_fake(self) -> None:
        stub = StubSubstrate()
        set_stub(stub)
        try:
            from ..demo.demo_crew import FakeBrain as FB  # noqa: F401 (parity guard)
            from ..demo.demo_crew import run
            text, crew_result, flow_result = run(real=False, topic="cleanroom")
            self.assertIn("cleanroom", text)
            self.assertTrue(crew_result.ok())
            self.assertEqual(len(flow_result.runs), 3)
            self.assertIn("written", flow_result.emitted)
        finally:
            restore_backend()


if __name__ == "__main__":
    unittest.main()