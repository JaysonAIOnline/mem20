"""Hermetic test suite for mem20orcaz (pure stdlib; unittest).

Run from the package root:
    /root/.venv/bin/python -m unittest discover -s tests -v
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mem20orcaz as o
from mem20orcaz.agents import AGENT_CLASSES
from mem20orcaz.agent_factory import AgentFactory
from mem20orcaz.concurrency import ConcurrencyManager  # noqa: F401
from mem20orcaz.execution import (
    AgentRunner,
    ContextManager,
    MetricsCollector,
    QueueProcessor,
    ResponseProcessor,
    TraceBuilder,
)
from mem20orcaz.fork_group_manager import ForkGroupManager
from mem20orcaz.loader import YAMLLoader
from mem20orcaz.memory import InMemoryMemoryLogger, MemoryLoggerError, create_memory_logger
from mem20orcaz.nodes import NODE_CLASSES
from mem20orcaz.prompt_rendering import FILTERS, render_template
from mem20orcaz.registry import ResourceRegistry, init_registry
from mem20orcaz.response_builder import ResponseBuilder

_ = (ConcurrencyManager,)


SIMPLE_YAML = """\
orchestrator:
  id: simple-demo
  queue: [a]
agents:
  - id: a
    type: echo
    prompt: "saw {{ input }}"
"""


class LoaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.loader = YAMLLoader()

    def test_parse_simple(self) -> None:
        cfg = self.loader.parse(SIMPLE_YAML)
        self.assertEqual(cfg["orchestrator"]["id"], "simple-demo")
        self.assertEqual(cfg["agents"][0]["id"], "a")
        self.assertEqual(cfg["agents"][0]["type"], "echo")

    def test_agent_config_map(self) -> None:
        self.loader.parse(SIMPLE_YAML)
        cfg_map = self.loader.agent_config_map()
        self.assertIn("a", cfg_map)
        self.assertEqual(cfg_map["a"]["type"], "echo")

    def test_initial_queue(self) -> None:
        self.loader.parse(SIMPLE_YAML)
        self.assertEqual(self.loader.initial_queue(), ["a"])

    def test_validate_passes(self) -> None:
        self.loader.parse(SIMPLE_YAML)
        self.assertTrue(self.loader.validate())

    def test_compact_nested_sequence(self) -> None:
        yaml = (
            "orchestrator:\n"
            "  id: nested\n"
            "  queue: [fork]\n"
            "agents:\n"
            "  - id: fork\n"
            "    type: forknode\n"
            "    params:\n"
            "      targets:\n"
            "        - - a\n"
            "          - b\n"
        )
        self.loader.parse(yaml)
        cfg = self.loader.agent_config_map()["fork"]["params"]["targets"]
        self.assertEqual(cfg, [["a", "b"]])


class MemoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.logger = InMemoryMemoryLogger()

    def test_log_and_get(self) -> None:
        self.logger.log_memory("k1", "stored-value")
        got = self.logger.get_memory("k1")
        self.assertEqual(got["value"], "stored-value")

    def test_search_returns_by_key_prefix(self) -> None:
        self.logger.log_memory("k1", "stored-value")
        hits = self.logger.search_memories("k1")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["value"], "stored-value")
        self.assertGreaterEqual(hits[0]["relevance"], 0.15)

    def test_search_matches_value_text(self) -> None:
        self.logger.log_memory("doc", "the quick brown fox")
        hits = self.logger.search_memories("fox")
        self.assertEqual([h["key"] for h in hits], ["memory_manager:doc"])

    def test_search_no_match(self) -> None:
        self.logger.log_memory("doc", "the quick brown fox")
        self.assertEqual(self.logger.search_memories("zzz"), [])

    def test_unsupported_backend(self) -> None:
        with self.assertRaises(MemoryLoggerError):
            create_memory_logger(backend="redis")


class PromptRenderingTests(unittest.TestCase):
    def test_render_simple(self) -> None:
        self.assertEqual(render_template("hi {{ name }}", {"name": "x"}), "hi x")

    def test_missing_var_empty(self) -> None:
        self.assertEqual(render_template("hi {{ missing }}", {}), "hi ")

    def test_filters_exist(self) -> None:
        for name in ("upper", "lower", "strip"):
            self.assertIn(name, FILTERS)

    def test_literal_braces(self) -> None:
        self.assertIn("{", render_template("literal {block}", {}))


class ResponseBuilderTests(unittest.TestCase):
    def test_success_has_status(self) -> None:
        resp = ResponseBuilder.create_success_response("v", component_id="a")
        self.assertEqual(resp["status"], "success")

    def test_error_has_status(self) -> None:
        resp = ResponseBuilder.create_error_response(ValueError("nope"), component_id="a")
        self.assertEqual(resp["status"], "error")
        self.assertIn("nope", str(resp["error"]))

    def test_plain_preserves_extras(self) -> None:
        resp = ResponseBuilder.from_plain_response(
            {"response": {"join_complete": True, "group_id": "g"},
             "hits": [1]},
            component_id="join", component_type="joinnode",
        )
        self.assertTrue(resp["join_complete"])
        self.assertEqual(resp["group_id"], "g")
        self.assertEqual(resp["hits"], [1])


class FactoryTests(unittest.TestCase):
    def test_star_kwargs_class_gets_config_prompt_registry(self) -> None:
        factory = AgentFactory(registry=None)
        factory.register_node_class("rag", NODE_CLASSES["rag"])
        node = factory.create("rag", {"type": "rag", "prompt": "{{ input }}"})
        self.assertEqual(node.prompt, "{{ input }}")
        self.assertEqual(node.config["type"], "rag")


class ForkGroupManagerTests(unittest.TestCase):
    def test_tracking(self) -> None:
        mgr = ForkGroupManager()
        mgr.create_group("g1")
        mgr.add_members("g1", ["a", "b"])
        self.assertTrue(mgr.group_exists("g1"))
        self.assertIn("a", mgr.list_pending_agents("g1"))
        mgr.mark_agent_done("g1", "a")
        self.assertNotIn("a", mgr.list_pending_agents("g1"))
        mgr.mark_agent_done("g1", "b")
        self.assertTrue(mgr.is_group_done("g1"))
        self.assertEqual(set(mgr.list_group_members("g1")), {"a", "b"})


class ExecutionTests(unittest.TestCase):
    def _run_workflow(self, agents: list[dict], max_exec: int = 20) -> dict:
        cfg = {"workflow": {"agents": agents}, "orchestration": {"max_executions": max_exec}}
        return o.Orchestrator("t", cfg).run("in")

    def test_sequential_echo(self) -> None:
        r = self._run_workflow([{"id": "a", "type": "echo", "prompt": "saw {{ input }}"}])
        self.assertEqual(r["response"], "saw in")

    def test_trace_shape(self) -> None:
        r = self._run_workflow([{"id": "a", "type": "echo", "prompt": "x"}])
        trace = r["trace"]
        self.assertEqual(trace["n_entries"], 1)
        entry = trace["entries"][0]
        self.assertEqual(entry["component_type"], "echo")
        self.assertEqual(entry["status"], "success")
        self.assertEqual(entry["output"], "x")

    def test_metrics_recorded(self) -> None:
        r = self._run_workflow([{"id": "a", "type": "echo", "prompt": "x"}])
        self.assertEqual(r["metrics"]["total_executions"], 1)
        self.assertEqual(r["metrics"]["statuses"], {"success": 1})

    def test_queue_processor_direct(self) -> None:
        cfg = {"workflow": {"agents": [
            {"id": "a", "type": "echo", "prompt": "A"},
            {"id": "b", "type": "echo", "prompt": "B"}]},
            "orchestration": {"max_executions": 10}}
        orch = o.Orchestrator("q", cfg)
        result = asyncio.run(orch.arun("q"))
        self.assertEqual(result["metrics"]["total_executions"], 2)

    def test_fork_join(self) -> None:
        r = self._run_workflow([
            {"id": "fork", "type": "forknode",
             "params": {"targets": ["a", "b"], "mode": "parallel"}},
            {"id": "a", "type": "echo", "prompt": "A"},
            {"id": "b", "type": "echo", "prompt": "B"},
            {"id": "join", "type": "joinnode",
             "params": {"group": "forkgroup0", "output_key": "joined"}},
            {"id": "d", "type": "constant", "output": "D after join"},
        ], max_exec=20)
        self.assertEqual(r["response"], "D after join")
        self.assertEqual(len(r["results"]), 5)

    def test_router(self) -> None:
        r = self._run_workflow([
            {"id": "r", "type": "routernode", "params": {"routes": [
                {"input": "in", "to": "b"}]}},
            {"id": "b", "type": "constant", "output": "BB"},
        ])
        self.assertEqual(r["response"], "BB")

    def test_failing_error_response(self) -> None:
        r = self._run_workflow([
            {"id": "boom", "type": "failing", "params": {"message": "kaboom"}},
        ])
        self.assertEqual(r["results"]["boom"]["status"], "error")
        self.assertIn("kaboom", str(r["results"]["boom"]["error"]))

    def test_failover(self) -> None:
        r = self._run_workflow([
            {"id": "f", "type": "failover", "params": {"fallbacks": ["alt"]}},
            {"id": "alt", "type": "constant", "output": "ALT RESULT"},
        ], max_exec=10)
        self.assertEqual(r["results"]["f"]["response"]["response"], "ALT RESULT")

    def test_loop_counter(self) -> None:
        r = self._run_workflow([
            {"id": "loop", "type": "loopnode", "params": {
                "target": "ctr", "start": 0, "end": 3, "step": 1,
                "loop_agent": "ctr", "max_iterations": 4}},
            {"id": "ctr", "type": "counter", "params": {"start": 0}},
        ], max_exec=30)
        self.assertEqual(r["response"], 1)

    def test_memory_writer_reader(self) -> None:
        r = self._run_workflow([
            {"id": "w", "type": "memory_writer",
             "params": {"key": "k1", "value": "stored-value"}},
            {"id": "rd", "type": "memory_reader", "params": {"query": "k1"}},
        ])
        self.assertEqual(r["results"]["rd"]["response"], ["stored-value"])

    def test_rag_with_gateway(self) -> None:
        orch = o.Orchestrator("rag", {"workflow": {"agents": [
            {"id": "w", "type": "memory_writer",
             "params": {"key": "doc1", "value": "Anaconda habitat facts"}},
            {"id": "rag", "type": "rag", "prompt": "retrieved: {{ retrieved }}"},
        ]}})
        orch.set_llm_gateway(lambda prompt, **kw: "SYNTH")
        r = orch.run("anaconda")
        rag = r["results"]["rag"]
        self.assertEqual(rag["response"], "SYNTH")
        self.assertGreaterEqual(len(rag["hits"]), 1)

    def test_binary_agent(self) -> None:
        r = o.Orchestrator("bint", {"workflow": {"agents": [
            {"id": "clf", "type": "binary",
             "params": {"true_values": ["yes"], "false_values": ["no"]}},
        ]}}).run("yes")
        self.assertIs(r["results"]["clf"]["response"], True)

    def test_factory_unknown_type_is_error_response(self) -> None:
        r = self._run_workflow([{"id": "x", "type": "definitely_missing"}])
        self.assertEqual(r["results"]["x"]["status"], "error")


class YAMLWorkflowTests(unittest.TestCase):
    def test_yaml_file_workflow(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".yml", delete=False) as fh:
            fh.write(SIMPLE_YAML)
            path = fh.name
        try:
            orch = o.Orchestrator("yaml-run",
                                  {"workflow": {"yaml_file_path": path}})
            result = orch.run("yaml input")
            self.assertIn("yaml input", result["response"])
        finally:
            os.unlink(path)

    def test_example_corpus_loads_and_validates(self) -> None:
        example_dir = os.environ.get("ORKA_CORPUS_DIR", "/opt/mem20/mem20orcaz/corpus/orca-examples")
        if not os.path.isdir(example_dir):
            self.skipTest("OrKa example corpus not present")
        loader = YAMLLoader()
        loaded, validated, skipped = 0, 0, 0
        failures: list[str] = []
        for root, _dirs, files in os.walk(example_dir):
            for fname in sorted(files):
                if not fname.endswith((".yml", ".yaml")):
                    continue
                path = os.path.join(root, fname)
                is_inputs_file = fname.endswith("inputs.yml") or fname.endswith("inputs.yaml")
                try:
                    loader.load_yaml(path)
                    loaded += 1
                    if is_inputs_file:
                        skipped += 1
                        continue  # payload files are input data, not orchestrator configs
                    if not loader.validate():
                        failures.append(path)
                except Exception as exc:  # noqa: BLE001
                    failures.append(f"{path}: {exc}")
        validated = loaded - skipped - len(failures)
        self.assertGreaterEqual(loaded, 84, f"corpus failures: {failures[:8]}")
        self.assertGreaterEqual(validated, 80, f"corpus failures: {failures[:8]}")
        self.assertEqual(failures, [])


class CLITests(unittest.TestCase):
    def test_version(self) -> None:
        import io
        from contextlib import redirect_stderr, redirect_stdout
        from mem20orcaz import cli
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cli.main(["--version"])
        self.assertEqual(code, 0)
        self.assertIn("0.9.17", buf.getvalue())

    def test_list_types(self) -> None:
        import io
        from contextlib import redirect_stdout
        from mem20orcaz import cli
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cli.main(["--list-types"])
        self.assertEqual(code, 0)
        self.assertIn("forknode", buf.getvalue())
        self.assertIn("echo", buf.getvalue())

    def test_missing_arg(self) -> None:
        import io
        from contextlib import redirect_stderr
        from mem20orcaz import cli
        buf = io.StringIO()
        with redirect_stderr(buf):
            code = cli.main([])
        self.assertEqual(code, 2)

    def test_run_yaml(self) -> None:
        import io
        from contextlib import redirect_stdout
        from mem20orcaz import cli
        with tempfile.NamedTemporaryFile("w", suffix=".yml", delete=False) as fh:
            fh.write(SIMPLE_YAML)
            path = fh.name
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = cli.main([path, "--input", "cli input", "--outputs"])
            self.assertEqual(code, 0)
            self.assertIn("final response", buf.getvalue())
            self.assertIn("cli input", buf.getvalue())
        finally:
            os.unlink(path)


class ImportSurfaceTests(unittest.TestCase):
    def test_exports(self) -> None:
        for name in ("Orchestrator", "YAMLLoader", "InMemoryMemoryLogger",
                     "create_memory_logger", "ResourceRegistry", "init_registry",
                     "ForkGroupManager", "QueueProcessor", "AgentRunner",
                     "ContextManager", "MetricsCollector", "ResponseProcessor",
                     "TraceBuilder", "AgentFactory", "render_template"):
            self.assertTrue(hasattr(o, name), name)

    def test_type_registries(self) -> None:
        self.assertIn("forknode", NODE_CLASSES)
        self.assertIn("joinnode", NODE_CLASSES)
        self.assertIn("echo", AGENT_CLASSES)
        self.assertIn("rag", NODE_CLASSES)


if __name__ == "__main__":
    unittest.main()