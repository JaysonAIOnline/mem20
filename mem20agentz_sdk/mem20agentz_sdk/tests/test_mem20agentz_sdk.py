"""Hermetic tests for mem20agentz_sdk."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock

from mem20agentz_sdk.agent import Agent, SimpleAgent, create_agent, ModelSettings, AgentOutputSchema
from mem20agentz_sdk.config import AgentSDKConfig, DEFAULT_CONFIG
from mem20agentz_sdk.tools import FunctionTool, function_tool, ToolContext, ComputerTool, WebSearchTool, FileSearchTool
from mem20agentz_sdk.handoffs import Handoff, handoff, HandoffInputData, HandoffHistoryMapper, DefaultHandoffHistoryMapper, RemoveAllHistoryMapper, default_handoff_history_mapper
from mem20agentz_sdk.guardrails import input_guardrail, output_guardrail, InputGuardrail, OutputGuardrail, GuardrailFunctionOutput
from mem20agentz_sdk.tracing import trace, span, get_current_trace, get_current_span, Trace, Span
from mem20agentz_sdk.runner import Runner, RunConfig, RunResult, run


class TestConfig(unittest.TestCase):
    """Config tests."""

    def test_defaults(self):
        cfg = AgentSDKConfig()
        self.assertEqual(cfg.port, 8001)
        self.assertEqual(cfg.gateway_url, "http://127.0.0.1:4000")
        self.assertTrue(cfg.enable_tracing)
        self.assertTrue(cfg.enable_guardrails)

    def test_load_from_yaml(self):
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("port: 9000\ngateway_url: \"http://localhost:4100\"\n")
            f.flush()
            cfg = AgentSDKConfig.load(f.name)
        import os
        os.unlink(f.name)
        self.assertEqual(cfg.port, 9000)
        self.assertEqual(cfg.gateway_url, "http://localhost:4100")


class TestAgent(unittest.TestCase):
    """Agent primitive tests."""

    def test_create_agent(self):
        agent = create_agent(name="test", instructions="Test agent", model="fast")
        self.assertEqual(agent.name, "test")
        self.assertEqual(agent.instructions, "Test agent")
        self.assertEqual(agent.model, "fast")
        self.assertEqual(agent.tools, [])
        self.assertEqual(agent.handoffs, [])
        self.assertEqual(agent.input_guardrails, [])
        self.assertEqual(agent.output_guardrails, [])

    def test_agent_with_tools(self):
        @function_tool
        def my_tool(x: int) -> int:
            return x * 2

        agent = create_agent(name="test", tools=[my_tool])
        self.assertEqual(len(agent.tools), 1)
        self.assertEqual(agent.tools[0].name, "my_tool")

    def test_agent_with_handoffs(self):
        other = create_agent(name="other")
        agent = create_agent(name="test", handoffs=[handoff(other)])
        self.assertEqual(len(agent.handoffs), 1)
        self.assertEqual(agent.handoffs[0].agent_name, "other")

    def test_get_tool(self):
        @function_tool
        def my_tool(x: int) -> int:
            return x * 2

        agent = create_agent(name="test", tools=[my_tool])
        tool = agent.get_tool("my_tool")
        self.assertIsNotNone(tool)
        self.assertEqual(tool.name, "my_tool")

    def test_get_handoff(self):
        other = create_agent(name="other")
        agent = create_agent(name="test", handoffs=[handoff(other)])
        h = agent.get_handoff("other")
        self.assertIsNotNone(h)
        self.assertEqual(h.agent_name, "other")


class TestTools(unittest.TestCase):
    """Tool primitive tests."""

    def test_function_tool(self):
        @function_tool
        def add(a: int, b: int) -> int:
            return a + b

        self.assertEqual(add.name, "add")
        self.assertIn("a", add.params_schema["properties"])
        self.assertIn("b", add.params_schema["properties"])

    def test_tool_invoke(self):
        @function_tool
        def add(a: int, b: int) -> int:
            return a + b

        import asyncio
        result = asyncio.run(add.invoke({"a": 2, "b": 3}, ToolContext()))
        self.assertEqual(result, 5)

    def test_tool_context_passed(self):
        received = {}

        @function_tool
        def with_context(*, ctx: ToolContext) -> str:
            received["ctx"] = ctx
            return "ok"

        import asyncio
        asyncio.run(with_context.invoke({}, ToolContext(agent_name="test", run_id="123")))
        self.assertEqual(received["ctx"].agent_name, "test")
        self.assertEqual(received["ctx"].run_id, "123")

    def test_computer_tool(self):
        tool = ComputerTool()
        self.assertEqual(tool.name, "computer")
        import asyncio
        result = asyncio.run(tool.invoke({"action": "screenshot"}, ToolContext()))
        self.assertEqual(result["status"], "simulated")

    def test_web_search_tool(self):
        tool = WebSearchTool()
        self.assertEqual(tool.name, "web_search")
        import asyncio
        result = asyncio.run(tool.invoke({"query": "test"}, ToolContext()))
        self.assertEqual(result["query"], "test")

    def test_file_search_tool(self):
        tool = FileSearchTool()
        self.assertEqual(tool.name, "file_search")
        import asyncio
        result = asyncio.run(tool.invoke({"query": "test"}, ToolContext()))
        self.assertEqual(result["query"], "test")


class TestHandoffs(unittest.TestCase):
    """Handoff tests."""

    def test_handoff_creation(self):
        other = create_agent(name="other")
        h = handoff(other)
        self.assertEqual(h.agent_name, "other")
        self.assertEqual(h.agent, other)

    def test_handoff_with_callback(self):
        called = {}

        def on_handoff(data: HandoffInputData):
            called["data"] = data

        other = create_agent(name="other")
        h = handoff(other, on_handoff=on_handoff)

        import asyncio
        asyncio.run(h.execute(HandoffInputData(input="test")))
        self.assertEqual(called["data"].input, "test")

    def test_handoff_history_mapper_default(self):
        other = create_agent(name="other")
        h = handoff(other)
        self.assertIsNone(h.history_mapper)
        import asyncio
        data = asyncio.run(h.execute(HandoffInputData(input="hi", history=[{"role": "user", "content": "1"}])))
        self.assertIsNotNone(data)

    def test_default_mapper_passthrough(self):
        history = [{"role": "user", "content": "x"}, {"role": "assistant", "content": "y"}]
        self.assertEqual(default_handoff_history_mapper(history), history)

    def test_remove_all_mapper(self):
        mapper = RemoveAllHistoryMapper()
        self.assertEqual(mapper.input_for_handoff([{"role": "user", "content": "x"}]), [])
        self.assertEqual(mapper.input_for_history([{"role": "user", "content": "x"}]), [])
        self.assertEqual(mapper.input_for_next_step([{"role": "user", "content": "x"}]), [])

    def test_default_mapper_keeps_history(self):
        mapper = DefaultHandoffHistoryMapper()
        history = [{"role": "user", "content": "x"}]
        self.assertEqual(mapper.input_for_handoff(history), history)

    def test_handoff_execute_applies_remove_all(self):
        other = create_agent(name="other")
        h = handoff(other, history_mapper=RemoveAllHistoryMapper())
        import asyncio
        data = HandoffInputData(input="hi", history=[{"role": "user", "content": "secret"}])
        asyncio.run(h.execute(data))
        # History wiped before the receiving agent continues
        self.assertEqual(data.history, [])

    def test_handoff_execute_applies_default(self):
        other = create_agent(name="other")
        h = handoff(other)
        import asyncio
        data = HandoffInputData(input="hi", history=[{"role": "user", "content": "kept"}])
        asyncio.run(h.execute(data))
        self.assertEqual(data.history, [{"role": "user", "content": "kept"}])

    def test_custom_mapper(self):
        class CapMapper(HandoffHistoryMapper):
            def input_for_handoff(self, history: list) -> list:
                return [{"role": "user", "content": m["content"].upper()} for m in history]

        other = create_agent(name="other")
        h = handoff(other, history_mapper=CapMapper())
        import asyncio
        data = HandoffInputData(input="hi", history=[{"role": "user", "content": "mem" }])
        asyncio.run(h.execute(data))
        self.assertEqual(data.history, [{"role": "user", "content": "MEM"}])


class TestGuardrails(unittest.TestCase):
    """Guardrail tests."""

    def test_input_guardrail(self):
        @input_guardrail
        def check_length(input: str, ctx: ToolContext) -> GuardrailFunctionOutput:
            return GuardrailFunctionOutput(
                output_info=len(input),
                tripwire_triggered=len(input) > 100
            )

        self.assertEqual(check_length.name, "check_length")
        import asyncio
        result = asyncio.run(check_length.check("short", ToolContext()))
        self.assertFalse(result.tripwire_triggered)

        result = asyncio.run(check_length.check("x" * 200, ToolContext()))
        self.assertTrue(result.tripwire_triggered)

    def test_output_guardrail(self):
        @output_guardrail
        def check_output(output: str, ctx: ToolContext) -> GuardrailFunctionOutput:
            return GuardrailFunctionOutput(
                output_info="checked",
                tripwire_triggered="bad" in output
            )

        import asyncio
        result = asyncio.run(check_output.check("good output", ToolContext()))
        self.assertFalse(result.tripwire_triggered)

        result = asyncio.run(check_output.check("bad output", ToolContext()))
        self.assertTrue(result.tripwire_triggered)


class TestTracing(unittest.TestCase):
    """Tracing tests."""

    def test_trace_context(self):
        with trace("test_trace") as tr:
            self.assertIsInstance(tr, Trace)
            self.assertEqual(tr.name, "test_trace")
            with span("test_span") as sp:
                self.assertIsInstance(sp, Span)
                self.assertEqual(sp.name, "test_span")

    def test_span_duration(self):
        with trace("t") as tr:
            with span("s") as sp:
                import time
                time.sleep(0.01)
        self.assertGreater(sp.end_time, sp.start_time)

    def test_get_current(self):
        with trace("t") as tr:
            self.assertIs(get_current_trace(), tr)
            with span("s") as sp:
                self.assertIs(get_current_span(), sp)


class TestRunner(unittest.TestCase):
    """Runner tests (mock mode)."""

    def test_run_mock(self):
        @function_tool
        def echo(x: str) -> str:
            return x

        agent = create_agent(
            name="test",
            instructions="Echo tool",
            tools=[echo],
        )

        import asyncio
        result = asyncio.run(run(agent, "hello", mock=True))
        self.assertIn("Response from test", result.output)

    def test_run_result(self):
        result = RunResult(
            output="test",
            agent=create_agent(name="test"),
            turns=1,
            handoffs=["other"],
            guardrail_trips=["bad_guardrail"],
        )
        self.assertEqual(result.output, "test")
        self.assertEqual(result.turns, 1)
        self.assertEqual(result.handoffs, ["other"])
        self.assertEqual(result.guardrail_trips, ["bad_guardrail"])
        d = result.to_dict()
        self.assertEqual(d["output"], "test")


class TestRunConfig(unittest.TestCase):
    """RunConfig tests."""

    def test_defaults(self):
        cfg = RunConfig()
        self.assertEqual(cfg.model, "fast")
        self.assertEqual(cfg.max_turns, 10)
        self.assertEqual(cfg.temperature, 1.0)

    def test_custom(self):
        cfg = RunConfig(model="balanced", max_turns=5, temperature=0.7)
        self.assertEqual(cfg.model, "balanced")
        self.assertEqual(cfg.max_turns, 5)
        self.assertEqual(cfg.temperature, 0.7)


if __name__ == "__main__":
    unittest.main()