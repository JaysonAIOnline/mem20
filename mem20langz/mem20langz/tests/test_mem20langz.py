"""mem20langz hermetic test suite (unittest, stdlib only)."""

from __future__ import annotations

import operator
import os
import sys
import unittest
from typing import Any, Annotated

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mem20langz import (  # noqa: E402
    Command,
    END,
    GraphRecursionError,
    InMemorySaver,
    Message,
    Send,
    START,
    StateGraph,
    add_messages,
    interrupt,
)
from mem20langz.types import InvalidUpdateError, LangzError  # noqa: E402


class TestTypes(unittest.TestCase):
    def test_interrupt_outside_graph(self):
        with self.assertRaises(LangzError):
            interrupt("x")

    def test_send_repr(self):
        s = Send("b", 17)
        self.assertEqual(s.node, "b")
        self.assertEqual(s.arg, 17)

    def test_command_fields(self):
        c = Command(update={"a": 1}, goto="next", resume=True)
        self.assertEqual(c.update, {"a": 1})
        self.assertEqual(c.goto, "next")
        self.assertTrue(c.resume)


class TestMessages(unittest.TestCase):
    def test_add_messages_append(self):
        m1 = Message(role="user", content="hi")
        m2 = Message(role="assistant", content="yo")
        out = add_messages([m1], [m2])
        self.assertEqual([m.content for m in out], ["hi", "yo"])

    def test_add_messages_replaces_by_id(self):
        m1 = Message(role="user", content="hi")
        m2 = Message(role="user", content="hi", id=m1.id)
        out = add_messages([m1], [m2])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].content, "hi")

    def test_add_messages_coerces_tuples(self):
        out = add_messages([], [("user", "hello")])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].role, "user")
        self.assertEqual(out[0].content, "hello")


def _superstep_sequence(app, schema):
    return app


class TestStateGraphCore(unittest.TestCase):
    def test_simple_chain(self):
        g = StateGraph({"total": {}})
        g.add_node("a", lambda s: {"total": s.get("total", 0) + 1})
        g.add_node("b", lambda s: {"total": s.get("total", 0) + 2})
        g.set_entry_point("a")
        g.add_edge("a", "b")
        g.add_edge("b", END)
        app = g.compile()
        out = app.invoke({"total": 0})
        self.assertEqual(out["total"], 3)

    def test_conditional_route(self):
        g = StateGraph({"total": {}})
        g.add_node("inc", lambda s: {"total": s.get("total", 0) + 1})
        g.add_node("stop", lambda s: {"total": s.get("total", 0)})
        g.set_entry_point("inc")
        g.add_conditional_edges(
            "inc",
            lambda s: "stop" if s.get("total", 0) >= 3 else "inc",
            {"inc": "inc", "stop": "stop"},
        )
        g.add_edge("stop", END)
        app = g.compile()
        out = app.invoke({"total": 0})
        self.assertEqual(out["total"], 3)

    def test_messages_reducer_channel(self):
        schema = {"messages": {"reducer": "add_messages"}, "text": {}}
        g = StateGraph(schema)

        def emit(s):
            return {"messages": [("user", "ping")]}

        g.add_node("say", emit)
        g.set_entry_point("say")
        g.add_edge("say", END)
        app = g.compile()
        out = app.invoke({"messages": [Message(role="user", content="seed")]})
        self.assertEqual(len(out["messages"]), 2)
        self.assertEqual(out["messages"][-1].content, "ping")

    def test_append_channel(self):
        g = StateGraph({"log": {"reducer": "operator.add"}})
        g.add_node("a", lambda s: {"log": ["one"]})
        g.add_node("b", lambda s: {"log": ["two"]})
        g.set_entry_point("a")
        g.add_edge("a", "b")
        g.add_edge("b", END)
        app = g.compile()
        out = app.invoke({"log": []})
        self.assertEqual(out["log"], ["one", "two"])

    def test_sequence(self):
        g = StateGraph({"total": {}})

        def inc(s):
            return {"total": s.get("total", 0) + 1}

        def dbl(s):
            return {"total": (s.get("total", 0) + 1) * 2}

        def out(s):
            return {"total": s.get("total", 0) + 100}

        g.add_node("out", out)
        g.add_sequence([inc, dbl])
        g.add_edge("dbl", "out")
        g.add_edge("out", END)
        app = g.compile()
        result = app.invoke({"total": 0})
        self.assertEqual(result["total"], 104)


class TestCheckpoint(unittest.TestCase):
    def test_checkpointer_persists(self):
        g = StateGraph({"total": {}})
        g.add_node("bump", lambda s: {"total": s.get("total", 0) + 1})
        g.set_entry_point("bump")
        g.add_edge("bump", END)
        cp = InMemorySaver()
        app = g.compile(checkpointer=cp)
        cfg = {"configurable": {"thread_id": "t1"}}
        out = app.invoke({"total": 0}, cfg)
        self.assertEqual(out["total"], 1)
        # resume from checkpointed state in same thread
        out2 = app.invoke({}, cfg)
        self.assertEqual(out2["total"], 2)
        self.assertGreaterEqual(len(app.get_state_history(cfg)), 2)

    def test_get_state(self):
        g = StateGraph({"x": {}})
        g.add_node("set", lambda s: {"x": 5})
        g.set_entry_point("set")
        g.add_edge("set", END)
        cp = InMemorySaver()
        app = g.compile(checkpointer=cp)
        cfg = {"configurable": {"thread_id": "gettest"}}
        app.invoke({}, cfg)
        self.assertEqual(app.get_state(cfg)["x"], 5)


class TestStream(unittest.TestCase):
    def test_stream_values(self):
        g = StateGraph({"total": {}})
        g.add_node("a", lambda s: {"total": s.get("total", 0) + 1})
        g.add_node("b", lambda s: {"total": s.get("total", 0) + 1})
        g.set_entry_point("a")
        g.add_edge("a", "b")
        g.add_edge("b", END)
        app = g.compile()
        events = [c for c in app.stream({}, stream_mode="values")]
        self.assertGreaterEqual(len(events), 2)

    def test_stream_updates(self):
        g = StateGraph({"total": {}})
        g.add_node("a", lambda s: {"total": 1})
        g.set_entry_point("a")
        g.add_edge("a", END)
        app = g.compile()
        events = [c for c in app.stream({}, stream_mode="updates")]
        labels = [k for (mode, payload) in events if mode == "updates" for k in payload]
        self.assertIn("a", labels)


class TestInterrupt(unittest.TestCase):
    def _build(self):
        def ask(s):
            return {"approve": interrupt({"q": "approve?"})}

        g = StateGraph({"approve": {}, "log": {}})
        g.add_node("ask", ask)
        g.add_node("use", lambda s: {"log": ["approved"]})
        g.add_node("deny", lambda s: {"log": ["denied"]})
        g.set_entry_point("ask")
        g.add_conditional_edges("ask", lambda s: "use" if s.get("approve") else "deny",
                                {"use": "use", "deny": "deny"})
        g.add_edge("use", END)
        g.add_edge("deny", END)
        return g.compile(checkpointer=InMemorySaver())

    def test_interrupt_then_resume_approve(self):
        app = self._build()
        cfg = {"configurable": {"thread_id": "it1"}}
        app.invoke({}, cfg)
        self.assertEqual(app.get_state(cfg)["_interrupt"], {"q": "approve?"})
        app.invoke(Command(resume=True), cfg)
        self.assertEqual(app.get_state(cfg)["log"], ["approved"])

    def test_interrupt_then_resume_deny(self):
        app = self._build()
        cfg = {"configurable": {"thread_id": "it2"}}
        app.invoke({}, cfg)
        app.invoke(Command(resume=False), cfg)
        self.assertEqual(app.get_state(cfg)["log"], ["denied"])

    def test_interrupt_persists_in_checkpoint(self):
        app = self._build()
        cfg = {"configurable": {"thread_id": "it3"}}
        app.invoke({}, cfg)
        snap = app.get_state(cfg)
        self.assertTrue(snap["_interrupt"])


class TestSend(unittest.TestCase):
    def test_fanout(self):
        g = StateGraph({"out": {"reducer": "operator.add"}})

        def split(s):
            return [Send("add", v) for v in s.get("vals", [])]

        g.add_node("split", split)
        g.add_node("add", lambda s: {"out": [int(s) + 1]})
        g.set_entry_point("split")
        g.add_edge("add", END)
        app = g.compile()
        out = app.invoke({"vals": [1, 2, 3], "out": []})
        self.assertEqual(sorted(int(x) for x in out["out"]), [2, 3, 4])


class TestErrors(unittest.TestCase):
    def test_recursion_limit(self):
        g = StateGraph({"total": {}})
        g.add_node("loop", lambda s: {"total": s.get("total", 0) + 1})
        g.set_entry_point("loop")
        g.add_conditional_edges("loop", lambda s: "loop", {"loop": "loop"})
        app = g.compile()
        with self.assertRaises(GraphRecursionError):
            app.invoke({"total": 0}, {"recursion_limit": 5})

    def test_invalid_node_return(self):
        g = StateGraph({"x": {}})
        g.add_node("bad", lambda s: "nope")
        g.set_entry_point("bad")
        g.add_edge("bad", END)
        app = g.compile()
        with self.assertRaises(InvalidUpdateError):
            app.invoke({})

    def test_unknown_edge_source(self):
        g = StateGraph({})
        g.add_node("a", lambda s: {})
        g.set_entry_point("a")
        g.add_edge("missing", END)
        with self.assertRaises(LangzError):
            g.compile()


class TestBatchAndAsync(unittest.TestCase):
    def test_batch(self):
        g = StateGraph({"v": {}})
        g.add_node("id", lambda s: {"v": s.get("v", 0)})
        g.set_entry_point("id")
        g.add_edge("id", END)
        app = g.compile()
        outs = app.batch([{"v": 1}, {"v": 2}])
        self.assertEqual([o["v"] for o in outs], [1, 2])

    def test_async_invoke(self):
        import asyncio

        g = StateGraph({"v": {}})
        g.add_node("id", lambda s: {"v": s.get("v", 7)})
        g.set_entry_point("id")
        g.add_edge("id", END)
        app = g.compile()
        out = asyncio.run(app.ainvoke({}))
        self.assertEqual(out["v"], 7)


class TestFreestyle(unittest.TestCase):
    def test_node_returns_none(self):
        g = StateGraph({"x": {}})
        g.add_node("noop", lambda s: None)
        g.add_node("set", lambda s: {"x": 1})
        g.set_entry_point("noop")
        g.add_edge("noop", "set")
        g.add_edge("set", END)
        app = g.compile()
        out = app.invoke({})
        self.assertEqual(out["x"], 1)


def main(argv: list[str] | None = None) -> int:
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())