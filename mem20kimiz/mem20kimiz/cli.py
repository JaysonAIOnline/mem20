"""mem20kimiz CLI — exercise the Kimi Agent Swarm substrate in-process.

Runs the full pipeline with a fake in-process sub-agent runtime: validate the
input, expand the template, run the batch scheduler, and print the ordered XML
result. `--flaky` makes the first launch hit a simulated provider rate limit so
the adaptive retry path is exercised.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass, field

from .batch import AgentRunAttemptHandle, AgentRunBatch, AgentRunBatchLauncher, AgentRunSuspendedEvent
from .tool import AgentSwarmTool

class RateLimitError(Exception):
    pass


@dataclass
class _FakeRuntime:
    delay: float = 0.05
    flaky: bool = False
    agents: dict[str, int] = field(default_factory=dict)
    suspended_events: list[AgentRunSuspendedEvent] = field(default_factory=list)
    _next_id: int = 0

    def _agent_id(self, prefix: str) -> str:
        self._next_id += 1
        return f"{prefix}-{self._next_id}"

    def _complete(self, agent_id: str, opts) -> asyncio.Future:
        loop = asyncio.get_running_loop()
        fut = loop.create_future()

        async def _work() -> None:
            await asyncio.sleep(self.delay)
            self.agents[agent_id] = self.agents.get(agent_id, 0) + 1
            attempts = self.agents[agent_id]
            if self.flaky and attempts == 1 and agent_id == "subagent-1":
                fut.set_exception(RateLimitError("Provider rate limit exceeded"))
            else:
                fut.set_result({"result": f'handled "{opts.prompt}"', "stopReason": None})

        asyncio.create_task(_work())
        return fut

    async def spawn(self, opts) -> AgentRunAttemptHandle:
        aid = self._agent_id("subagent")
        return AgentRunAttemptHandle(agentId=aid, profileName=opts.profileName, completion=self._complete(aid, opts))

    async def resume(self, agent_id: str, opts) -> AgentRunAttemptHandle:
        return AgentRunAttemptHandle(agentId=agent_id, profileName="subagent", completion=self._complete(f"{agent_id}.r", opts))

    async def retry(self, agent_id: str, opts) -> AgentRunAttemptHandle:
        return AgentRunAttemptHandle(agentId=agent_id, profileName="subagent", completion=self._complete(agent_id, opts))

    def on_suspended(self, event: AgentRunSuspendedEvent) -> None:
        self.suspended_events.append(event)


async def _run(tool: AgentSwarmTool, runtime: _FakeRuntime, max_concurrency: int | None, timeout: float | None) -> str:
    specs = tool.validate_specs()
    tasks = tool.to_tasks(caller_agent_id="coordinator", parent_tool_call_id="swarm_1", spec_source=specs)
    for i, t in enumerate(tasks):
        t.timeout = timeout
        t.signal = None
    launcher = AgentRunBatchLauncher(
        spawn=runtime.spawn,
        resume=runtime.resume,
        retry=runtime.retry,
        suspended=runtime.on_suspended,
    )
    batch = AgentRunBatch(launcher, tasks, max_concurrency=max_concurrency)
    results = await batch.run()
    return tool.render_results(results, specs)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mem20kimiz", description="Kimi Agent Swarm substrate demo")
    parser.add_argument("--items", required=True, help='comma-separated items for {{item}} fan-out')
    parser.add_argument("--template", required=True, help='prompt template containing {{item}}')
    parser.add_argument("--description", default="Process the requested items in parallel")
    parser.add_argument("--subagent-type", default="coder")
    parser.add_argument("--max-concurrency", type=int, default=None, help="cap concurrent subagents")
    parser.add_argument("--timeout", type=float, default=10.0, help="per-subagent timeout (seconds)")
    parser.add_argument("--flaky", action="store_true", help="simulate one provider rate limit on first launch")
    parser.add_argument("--resume-agent-ids", default=None, help='resume map as comma list of agent_id:prompt')
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    items = [i.strip() for i in args.items.split(",") if i.strip()]
    resume = {}
    if args.resume_agent_ids:
        for chunk in args.resume_agent_ids.split(","):
            if ":" not in chunk:
                print(f"error: resume entries must be agent_id:prompt, got {chunk!r}", file=sys.stderr)
                return 2
            key, _, val = chunk.partition(":")
            resume[key.strip()] = val.strip()

    tool = AgentSwarmTool(
        description=args.description,
        subagent_type=args.subagent_type,
        prompt_template=args.template,
        items=items,
        resume_agent_ids=resume or None,
    )
    runtime = _FakeRuntime(flaky=args.flaky)

    try:
        specs = tool.validate_specs(get_resume_item=lambda aid: aid)
    except Exception as error:
        print(f"validation error: {error}", file=sys.stderr)
        return 1

    print(f"# swarm mode: {len(specs.spawn)} spawn(s), {len(specs.resume)} resume(s)")
    xml = asyncio.run(
        _run(tool, runtime, args.max_concurrency, args.timeout),
    )
    print(xml)
    if runtime.suspended_events:
        print(f"# suspended events: {len(runtime.suspended_events)}")
        for ev in runtime.suspended_events:
            print(f"#   {ev.agentId}: {ev.reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())