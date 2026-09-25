"""Agent primitive — native absorption of OpenAI Agents SDK Agent."""

from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from pydantic import BaseModel, Field

from .config import DEFAULT_CONFIG
from .tools import Tool, FunctionTool, ToolContext
from .handoffs import Handoff
from .guardrails import InputGuardrail, OutputGuardrail
from .tracing import Trace, Span


@dataclass
class ModelSettings:
    """Model settings for agent runs."""
    temperature: float = 1.0
    top_p: float = 1.0
    max_tokens: Optional[int] = None
    parallel_tool_calls: bool = True
    tool_choice: str = "auto"


@dataclass
class AgentOutputSchema:
    """Output schema for structured agent outputs."""
    output_type: type
    strict: bool = False


class Agent(ABC):
    """Native mem20 Agent — absorption of OpenAI Agents SDK Agent.

    Core primitives:
    - name, instructions, model
    - tools: list[Tool]
    - handoffs: list[Handoff]
    - input_guardrails: list[InputGuardrail]
    - output_guardrails: list[OutputGuardrail]
    - output_schema: AgentOutputSchema
    - model_settings: ModelSettings
    """

    def __init__(
        self,
        name: str,
        instructions: str = "",
        model: str = "fast",
        tools: list[Tool] = None,
        handoffs: list[Handoff] = None,
        input_guardrails: list[InputGuardrail] = None,
        output_guardrails: list[OutputGuardrail] = None,
        output_schema: Optional[AgentOutputSchema] = None,
        model_settings: Optional[ModelSettings] = None,
    ):
        self.name = name
        self.instructions = instructions
        self.model = model
        self.tools = tools or []
        self.handoffs = handoffs or []
        self.input_guardrails = input_guardrails or []
        self.output_guardrails = output_guardrails or []
        self.output_schema = output_schema
        self.model_settings = model_settings or ModelSettings()

    def get_tool(self, name: str) -> Optional[Tool]:
        """Get tool by name."""
        for t in self.tools:
            if t.name == name:
                return t
        return None

    def get_handoff(self, name: str) -> Optional[Handoff]:
        """Get handoff by name."""
        for h in self.handoffs:
            if h.agent_name == name:
                return h
        return None

    @abstractmethod
    async def run(self, input: str, context: Optional[dict] = None) -> "RunResult":
        """Run the agent with input."""
        pass

    def clone(self, **overrides) -> "Agent":
        """Create a clone with overrides."""
        data = {
            "name": self.name,
            "instructions": self.instructions,
            "model": self.model,
            "tools": self.tools.copy(),
            "handoffs": self.handoffs.copy(),
            "input_guardrails": self.input_guardrails.copy(),
            "output_guardrails": self.output_guardrails.copy(),
            "output_schema": self.output_schema,
            "model_settings": self.model_settings,
        }
        data.update(overrides)
        return self.__class__(**data)


class SimpleAgent(Agent):
    """Simple concrete agent implementation using mem20 gateway."""

    async def run(self, input: str, context: Optional[dict] = None) -> "RunResult":
        from .runner import Runner, RunConfig
        config = RunConfig(model=self.model, max_turns=DEFAULT_CONFIG.max_turns)
        runner = Runner(config=config)
        return await runner.run(self, input, context)


# Convenience factory
def create_agent(
    name: str,
    instructions: str = "",
    model: str = "fast",
    tools: list[Tool] = None,
    handoffs: list[Handoff] = None,
    **kwargs
) -> Agent:
    """Factory for creating agents."""
    return SimpleAgent(
        name=name,
        instructions=instructions,
        model=model,
        tools=tools or [],
        handoffs=handoffs or [],
        **kwargs
    )