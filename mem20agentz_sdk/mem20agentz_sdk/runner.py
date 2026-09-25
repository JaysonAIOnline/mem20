"""Runner — native absorption of OpenAI Agents SDK Runner."""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from .agent import Agent, SimpleAgent
from .config import DEFAULT_CONFIG
from .tools import ToolContext, FunctionTool
from .handoffs import Handoff, HandoffInputData
from .guardrails import InputGuardrail, OutputGuardrail, InputGuardrailResult, OutputGuardrailResult
from .tracing import trace, span, get_current_trace


@dataclass
class RunConfig:
    """Configuration for a run."""
    model: str = "fast"
    max_turns: int = 10
    temperature: float = 1.0
    top_p: float = 1.0
    max_tokens: Optional[int] = None


@dataclass
class RunResult:
    """Result of an agent run."""
    output: str
    agent: Agent
    context: dict = field(default_factory=dict)
    turns: int = 0
    handoffs: list[str] = field(default_factory=list)
    guardrail_trips: list[str] = field(default_factory=list)
    trace: Optional[Any] = None

    def to_dict(self) -> dict:
        return {
            "output": self.output,
            "agent": self.agent.name,
            "turns": self.turns,
            "handoffs": self.handoffs,
            "guardrail_trips": self.guardrail_trips,
        }


class Runner:
    """Native Runner — executes agents with tools, handoffs, guardrails."""

    def __init__(self, config: Optional[RunConfig] = None, mock: bool = False):
        self.config = config or RunConfig()
        self.mock = mock
        if not mock:
            self._client = httpx.AsyncClient(timeout=60.0)
            self._gateway_url = DEFAULT_CONFIG.gateway_url
        else:
            self._client = None
            self._gateway_url = None

    async def run(
        self,
        agent: Agent,
        input: str,
        context: Optional[dict] = None,
    ) -> RunResult:
        """Run an agent with input."""
        ctx = context or {}
        run_id = uuid.uuid4().hex[:16]
        tool_ctx = ToolContext(agent_name=agent.name, run_id=run_id, metadata=ctx)

        with trace(f"run:{agent.name}:{run_id}") as tr:
            # Run input guardrails
            for guardrail in agent.input_guardrails:
                with span(f"guardrail:input:{guardrail.name}"):
                    result = await guardrail.check(input, tool_ctx)
                    if result.tripwire_triggered:
                        tr.metadata["guardrail_trip"] = guardrail.name
                        return RunResult(
                            output=f"Input guardrail '{guardrail.name}' triggered",
                            agent=agent,
                            context=ctx,
                            guardrail_trips=[guardrail.name],
                            trace=tr,
                        )

            # Main agent loop
            current_agent = agent
            current_input = input
            turns = 0
            handoffs_made = []
            all_output = ""
            history: list[dict] = []

            while turns < self.config.max_turns:
                turns += 1

                with span(f"turn:{turns}:{current_agent.name}") as sp:
                    sp.data["input"] = current_input[:200]

                    # Call gateway for completion
                    try:
                        output = await self._call_gateway(current_agent, current_input, ctx)
                    except Exception as e:
                        sp.finish(error=str(e))
                        return RunResult(
                            output=f"Gateway error: {e}",
                            agent=current_agent,
                            context=ctx,
                            turns=turns,
                            handoffs=handoffs_made,
                            trace=tr,
                        )

                    all_output = output
                    sp.data["output"] = output[:200]
                    history.append({"role": "assistant", "content": output})

                    # Check for handoff
                    handoff_agent = self._check_handoff(current_agent, output)
                    if handoff_agent:
                        handoffs_made.append(handoff_agent.name)
                        with span(f"handoff:{current_agent.name}->{handoff_agent.name}"):
                            # Run handoff callback with conversation history so a
                            # history_mapper can drop/rewrite prior turns before the
                            # receiving agent continues. On handoffs without a mapper,
                            # history passes through unchanged.
                            for h in current_agent.handoffs:
                                if h.agent_name == handoff_agent.name:
                                    input_data = HandoffInputData(input=output, context=ctx, history=list(history))
                                    await h.execute(input_data)
                                    history = input_data.history
                                    break
                            current_agent = handoff_agent
                            current_input = output
                            continue

                    # Run output guardrails on final output
                    if turns == self.config.max_turns or not self._has_tool_calls(output):
                        for guardrail in current_agent.output_guardrails:
                            with span(f"guardrail:output:{guardrail.name}"):
                                result = await guardrail.check(output, tool_ctx)
                                if result.tripwire_triggered:
                                    tr.metadata["output_guardrail_trip"] = guardrail.name
                                    return RunResult(
                                        output=f"Output guardrail '{guardrail.name}' triggered",
                                        agent=current_agent,
                                        context=ctx,
                                        turns=turns,
                                        handoffs=handoffs_made,
                                        guardrail_trips=[guardrail.name],
                                        trace=tr,
                                    )
                        break

                    # If tool calls detected, execute them
                    tool_results = await self._execute_tools(current_agent, output, tool_ctx)
                    if tool_results:
                        current_input = self._format_tool_results(tool_results)
                        continue

                    break

            return RunResult(
                output=all_output,
                agent=current_agent,
                context=ctx,
                turns=turns,
                handoffs=handoffs_made,
                trace=tr,
            )

    async def _call_gateway(self, agent: Agent, input: str, context: dict) -> str:
        """Call mem20 gateway for completion, or return mock response."""
        if self.mock:
            return self._mock_response(agent, input)

        payload = {
            "model": agent.model,
            "messages": [
                {"role": "system", "content": agent.instructions},
                {"role": "user", "content": input},
            ],
            "temperature": self.config.temperature,
            "top_p": self.config.top_p,
        }
        if self.config.max_tokens:
            payload["max_tokens"] = self.config.max_tokens

        resp = await self._client.post(f"{self._gateway_url}/v1/chat/completions", json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data.get("choices", [{}])[0].get("message", {}).get("content", "")

    def _mock_response(self, agent: Agent, input: str) -> str:
        """Mock response for testing."""
        # Check if input is asking for calculator
        if "calculator" in agent.instructions.lower() or "math" in agent.instructions.lower():
            # Check if input is a math question
            if "15 * 23" in input or "15*23" in input:
                return "// handoff: math_expert"
            return "I'll use the calculator tool."
        # Check for handoff
        if "handoff" in agent.instructions.lower():
            return "// handoff: math_expert"
        return f"Response from {agent.name}: {input[:50]}..."

    def _check_handoff(self, agent: Agent, output: str) -> Optional[Agent]:
        """Check if output contains a handoff request."""
        output_lower = output.lower()
        for h in agent.handoffs:
            agent_name = h.agent_name.replace("_", " ")
            patterns = [
                f"handoff_to_{h.agent_name}",
                f"handoff to {agent_name}",
                f"handoff to {h.agent_name}",
                f"handoff.*:.*{agent_name}",
                f"handoff.*:.*{h.agent_name}",
                f"handoff.*{agent_name}",
                f"handoff.*{h.agent_name}",
                f"handing.*off.*to.*{agent_name}",
                f"handing.*off.*to.*{h.agent_name}",
                f"transfer.*to.*{agent_name}",
                f"transfer.*to.*{h.agent_name}",
            ]
            import re
            for pattern in patterns:
                if re.search(pattern, output_lower):
                    return h.agent
        return None

    def _has_tool_calls(self, output: str) -> bool:
        """Check if output contains tool calls."""
        return "tool_call" in output.lower() or "function_call" in output.lower()

    async def _execute_tools(self, agent: Agent, output: str, tool_ctx: ToolContext) -> list:
        """Execute tool calls from output."""
        # Simplified - in real impl, parse structured tool calls
        return []

    def _format_tool_results(self, results: list) -> str:
        return json.dumps(results)


async def run(
    agent: Agent,
    input: str,
    context: Optional[dict] = None,
    config: Optional[RunConfig] = None,
    mock: bool = False,
) -> RunResult:
    """Convenience function to run an agent."""
    runner = Runner(config=config, mock=mock)
    return await runner.run(agent, input, context)