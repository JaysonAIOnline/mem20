"""mem20agentz_sdk CLI — agent SDK primitives."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from .agent import Agent, SimpleAgent, create_agent, ModelSettings
from .config import DEFAULT_CONFIG, AgentSDKConfig
from .runner import Runner, RunConfig, run
from .tools import function_tool, FunctionTool, ToolContext
from .handoffs import handoff, Handoff
from .guardrails import input_guardrail, output_guardrail
from .tracing import trace, span, get_current_trace


def _cmd_serve(args) -> int:
    """Run a simple agent server."""
    print(f"mem20agentz_sdk server on {args.host}:{args.port}")
    print("Not yet implemented - use Runner directly")
    return 0


def _cmd_run(args) -> int:
    """Run an agent from command line."""
    if not args.agent:
        print("Error: --agent required")
        return 1

    agent = SimpleAgent(
        name=args.agent,
        instructions=args.instructions or "You are a helpful assistant.",
        model=args.model or "fast",
    )

    if args.input:
        result = asyncio.run(run(agent, args.input))
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print("Agent created. Use --input to run.")
    return 0


def _cmd_test(args) -> int:
    """Run a quick test."""
    @function_tool
    def get_weather(city: str) -> str:
        return f"Weather in {city}: sunny, 72F"

    @function_tool
    def get_time(timezone: str = "UTC") -> str:
        return f"Time in {timezone}: 12:00"

    agent = create_agent(
        name="test_agent",
        instructions="You have access to weather and time tools.",
        tools=[get_weather, get_time],
    )

    async def test():
        result = await run(agent, "What's the weather in NYC?", mock=True)
        print(f"Result: {result.output}")
        return result

    asyncio.run(test())
    return 0


def _cmd_demo(args) -> int:
    """Run a demo with handoff."""
    @function_tool
    def calculator(a: float, b: float, op: str) -> float:
        if op == "+": return a + b
        if op == "-": return a - b
        if op == "*": return a * b
        if op == "/": return a / b
        raise ValueError(f"Unknown op: {op}")

    math_agent = create_agent(
        name="math_expert",
        instructions="You are a math expert. Use the calculator tool.",
        tools=[calculator],
    )

    main_agent = create_agent(
        name="assistant",
        instructions="You are a helpful assistant. Handoff to math_expert for calculations. Use handoff_to_math_expert to transfer.",
        handoffs=[handoff(math_agent)],
    )

    async def demo():
        result = await run(main_agent, "What's 15 * 23?", config=RunConfig(), mock=True)
        print(f"Output: {result.output}")
        print(f"Handoffs: {result.handoffs}")

    asyncio.run(demo())
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="mem20agentz_sdk", description="mem20 native OpenAI Agents SDK")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("serve", help="Run agent server")
    s.add_argument("--host", default="0.0.0.0")
    s.add_argument("--port", type=int, default=8001)
    s.set_defaults(func=_cmd_serve)

    r = sub.add_parser("run", help="Run an agent")
    r.add_argument("--agent", required=True, help="Agent name")
    r.add_argument("--instructions", help="Agent instructions")
    r.add_argument("--model", default="fast")
    r.add_argument("--input", help="Input to process")
    r.set_defaults(func=_cmd_run)

    sub.add_parser("test", help="Quick test").set_defaults(func=_cmd_test)
    sub.add_parser("demo", help="Demo with handoff").set_defaults(func=_cmd_demo)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())