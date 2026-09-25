"""mem20langz — CLI."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .graph import StateGraph
from .checkpointer import InMemorySaver
from .types import END, Command, Send, interrupt


def _ordering_state() -> dict[str, Any]:
    return {"total": {}}


def _build_loop_graph() -> Any:
    from .state import Message, add_messages

    g = StateGraph({"total": {}})
    g.add_node("bump", lambda s: {"total": s.get("total", 0) + 1})
    g.add_node("done", lambda s: {"total": s.get("total", 0) + 1})
    g.add_conditional_edges("bump", lambda s: "done" if s.get("total", 0) >= 3 else "bump",
                            {"bump": "bump", "done": "done"})
    g.set_entry_point("bump")
    g.add_edge("done", END)
    return g.compile()


def _build_fanout_graph() -> Any:
    g = StateGraph({"out": {}})
    g.add_node("split", lambda s: [Send("add", v) for v in s.get("vals", [])])
    g.add_node("add", lambda s: {"out": [int(s) + 1]})
    g.set_entry_point("split")
    g.add_edge("add", END)
    return g.compile()


def _build_interrupt_graph() -> Any:
    def ask(s: dict[str, Any]) -> dict[str, Any]:
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


def cmd_loop(args: argparse.Namespace) -> int:
    app = _build_loop_graph()
    out = app.invoke({"total": 0}, {"configurable": {"thread_id": "looptest", "recursion_limit": 10}})
    print(json.dumps({"total": out["total"]}))
    return 0


def cmd_fanout(args: argparse.Namespace) -> int:
    app = _build_fanout_graph()
    vals = [int(x) for x in args.values.split(",")]
    out = app.invoke({"vals": vals, "out": []})
    print(json.dumps({"out": [int(x) for x in out["out"]]}))
    return 0


def cmd_interrupt(args: argparse.Namespace) -> int:
    app = _build_interrupt_graph()
    cfg = {"configurable": {"thread_id": args.thread}}
    app.invoke({}, cfg)
    snap = app.get_state(cfg)
    prompt = (snap or {}).get("_interrupt")
    print("INTERRUPTED waiting on:", json.dumps(prompt))
    app.invoke(Command(resume=args.resume == "true"), cfg)
    out = app.get_state(cfg)
    print(json.dumps({k: v for k, v in out.items() if not k.startswith("_")}))
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    g = _build_loop_graph()
    print(json.dumps(g.get_graph()))
    return 0


def cmd_test(args: argparse.Namespace) -> int:
    from .tests import test_mem20langz

    return test_mem20langz.main()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mem20langz", description="Native mem20 graph substrate absorption")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("serve", help="print compiled graph structure")
    sub.add_parser("loop", help="run simple loop graph")
    f = sub.add_parser("fanout", help="run Send fan-out graph")
    f.add_argument("--values", default="1,2,3")
    it = sub.add_parser("interrupt", help="interrupt/resume demo")
    it.add_argument("--thread", default="itest")
    it.add_argument("--resume", default="true", choices=["true", "false"])
    sub.add_parser("test", help="run hermetic test suite")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "loop":
        return cmd_loop(args)
    if args.cmd == "fanout":
        return cmd_fanout(args)
    if args.cmd == "interrupt":
        return cmd_interrupt(args)
    if args.cmd == "serve":
        return cmd_serve(args)
    if args.cmd == "test":
        return cmd_test(args)
    build_parser().print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())