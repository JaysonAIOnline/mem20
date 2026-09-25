from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from .agents import BaseAgent
from .config import GoogleADKConfig
from .providers import resolve_provider
from .runners import DurableRunner


def _make_runner(
    agent: BaseAgent,
    config: GoogleADKConfig,
    provider=None,
) -> DurableRunner:
    return DurableRunner(
        agent=agent,
        app_name="mem20googlez",
        config_data=config,
        provider=provider,
    )


def _cmd_serve(args) -> int:
    from .serve import serve

    config = GoogleADKConfig.load(args.config)
    serve(host=args.host, port=args.port, config=config)
    return 0


async def _cmd_run_async(args, config: GoogleADKConfig) -> int:
    from .serve import default_registry

    agent = next((candidate for candidate in default_registry() if candidate.name == args.agent), None)
    if agent is None:
        print(json.dumps({"error": f"unknown agent '{args.agent}'"}))
        return 1
    provider = await resolve_provider(config, provider=args.provider) if args.provider != "auto" else None
    runner = _make_runner(agent, config, provider)
    result = await runner.run(
        user_id=args.user,
        session_id=args.session,
        input=args.input,
    )
    print(
        json.dumps(
            {
                "agent": agent.name,
                "session_id": result.session.id,
                "output": result.final_output or "",
                "events": len(result.events),
                "error": result.error,
            },
            indent=2,
        )
    )
    return 0 if not result.error else 2


def _cmd_run(args) -> int:
    return asyncio.run(_cmd_run_async(args, GoogleADKConfig.load(args.config)))


def _cmd_pytest(args) -> int:
    import pytest

    package_root = Path(__file__).resolve().parent
    return pytest.main([str(package_root / "tests"), "-v"])


def _cmd_agents(args) -> int:
    from .serve import default_registry

    print(json.dumps({"agents": [agent.to_card() for agent in default_registry()]}, indent=2))
    return 0


def _cmd_health(args) -> int:
    config = GoogleADKConfig.load(args.config)
    provider = asyncio.run(resolve_provider(config, provider=args.provider))
    healthy, detail = asyncio.run(provider.health())
    print(
        json.dumps(
            {
                "healthy": healthy,
                "provider": provider.name,
                "model": provider.model,
                "detail": detail,
                "config": {
                    "ollama_url": config.ollama_url,
                    "gateway_url": config.gateway_url,
                    "port": config.port,
                },
            },
            indent=2,
        )
    )
    return 0 if healthy else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="mem20googlez", description="mem20 Google ADK runtime")
    parser.add_argument("--config", help="YAML configuration path")
    sub = parser.add_subparsers(dest="command", required=True)

    serve_parser = sub.add_parser("serve", help="Run the FastAPI server")
    serve_parser.add_argument("--config", default=argparse.SUPPRESS)
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8002)
    serve_parser.set_defaults(func=_cmd_serve)

    run_parser = sub.add_parser("run", help="Run an agent against the local model endpoint")
    run_parser.add_argument("--config", default=argparse.SUPPRESS)
    run_parser.add_argument("--agent", default="chat")
    run_parser.add_argument("--input", required=True)
    run_parser.add_argument("--user", default="cli")
    run_parser.add_argument("--session")
    run_parser.add_argument("--provider", choices=["auto", "ollama", "openai"], default="auto")
    run_parser.set_defaults(func=_cmd_run)

    agents_parser = sub.add_parser("agents", help="List registered agents")
    agents_parser.add_argument("--config", default=argparse.SUPPRESS)
    agents_parser.set_defaults(func=_cmd_agents)

    health_parser = sub.add_parser("health", help="Check the resolved model endpoint")
    health_parser.add_argument("--config", default=argparse.SUPPRESS)
    health_parser.add_argument("--provider", choices=["auto", "ollama", "openai"], default="auto")
    health_parser.set_defaults(func=_cmd_health)

    test_parser = sub.add_parser("test", help="Run package tests")
    test_parser.add_argument("--config", default=argparse.SUPPRESS)
    test_parser.set_defaults(func=_cmd_pytest)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
