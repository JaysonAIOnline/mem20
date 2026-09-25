from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .events import Event
from .providers import ModelProvider
from .sessions import Session
from .tools import BaseTool


class AgentType(str, Enum):
    LLM = "llm"
    LOOP = "loop"
    PARALLEL = "parallel"
    SEQUENTIAL = "sequential"
    CUSTOM = "custom"


@dataclass
class AgentConfig:
    name: str
    description: str = ""
    agent_type: str = "llm"
    model: str = "fast"
    instruction: str = ""
    tools: list[BaseTool] = field(default_factory=list)
    sub_agents: list[BaseAgent] = field(default_factory=list)
    before_model_callback: Callable | None = None
    after_model_callback: Callable | None = None
    before_tool_callback: Callable | None = None
    after_tool_callback: Callable | None = None
    max_iterations: int = 10
    temperature: float = 1.0
    top_p: float = 1.0
    top_k: int = 40


def _last_model_text(events: list[Event]) -> str:
    for event in reversed(events):
        if event.author == "model" and event.text():
            return event.text()
    return ""


class BaseAgent:
    def __init__(
        self,
        name: str,
        agent_type: AgentType,
        config: AgentConfig | None = None,
        **kwargs: Any,
    ):
        self.name = name
        self.agent_type = agent_type
        self.config = config or AgentConfig(name=name)
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)

    async def run_async(
        self,
        session: Session,
        input: str,
        provider: ModelProvider | None = None,
        config: Any = None,
    ) -> list[Event]:
        raise TypeError(f"{type(self).__name__} must implement run_async")

    def run(self, session: Session, input: str, provider: ModelProvider | None = None) -> list[Event]:
        return asyncio.run(self.run_async(session, input, provider=provider))

    def get_tool(self, name: str) -> BaseTool | None:
        return next((tool for tool in self.config.tools if tool.name == name), None)

    def get_sub_agent(self, name: str) -> BaseAgent | None:
        return next((agent for agent in self.config.sub_agents if agent.name == name), None)

    def to_card(self) -> dict:
        return {
            "name": self.name,
            "type": self.agent_type.value,
            "description": self.config.description,
            "model": self.config.model,
            "instruction": self.config.instruction,
            "tools": [tool.name for tool in self.config.tools],
            "sub_agents": [agent.name for agent in self.config.sub_agents],
        }


class LlmAgent(BaseAgent):
    def __init__(
        self,
        name: str,
        instruction: str = "",
        model: str = "fast",
        tools: list[BaseTool] | None = None,
        sub_agents: list[BaseAgent] | None = None,
        description: str = "",
        **kwargs: Any,
    ):
        super().__init__(
            name,
            AgentType.LLM,
            AgentConfig(
                name=name,
                agent_type=AgentType.LLM,
                instruction=instruction,
                model=model,
                tools=list(tools or []),
                sub_agents=list(sub_agents or []),
                description=description,
            ),
            **kwargs,
        )

    async def run_async(
        self,
        session: Session,
        input: str,
        provider: ModelProvider | None = None,
        config: Any = None,
    ) -> list[Event]:
        from .runners import run_agent

        return await run_agent(self, session, input, config=config, provider=provider)


class LoopAgent(BaseAgent):
    def __init__(
        self,
        name: str,
        sub_agents: list[BaseAgent],
        max_iterations: int = 10,
        **kwargs: Any,
    ):
        super().__init__(
            name,
            AgentType.LOOP,
            AgentConfig(
                name=name,
                agent_type=AgentType.LOOP,
                sub_agents=list(sub_agents),
                max_iterations=max(1, int(max_iterations)),
            ),
            **kwargs,
        )

    async def run_async(
        self,
        session: Session,
        input: str,
        provider: ModelProvider | None = None,
        config: Any = None,
    ) -> list[Event]:
        events: list[Event] = []
        current_input = input
        for _ in range(self.config.max_iterations):
            for agent in self.config.sub_agents:
                step_events = await agent.run_async(
                    session,
                    current_input,
                    provider=provider,
                    config=config,
                )
                events.extend(step_events)
                current_input = _last_model_text(step_events) or current_input
        return events


class ParallelAgent(BaseAgent):
    def __init__(self, name: str, sub_agents: list[BaseAgent], **kwargs: Any):
        super().__init__(
            name,
            AgentType.PARALLEL,
            AgentConfig(
                name=name,
                agent_type=AgentType.PARALLEL,
                sub_agents=list(sub_agents),
            ),
            **kwargs,
        )

    async def run_async(
        self,
        session: Session,
        input: str,
        provider: ModelProvider | None = None,
        config: Any = None,
    ) -> list[Event]:
        results = await asyncio.gather(
            *(
                agent.run_async(session, input, provider=provider, config=config)
                for agent in self.config.sub_agents
            )
        )
        return [event for result in results for event in result]


class SequentialAgent(BaseAgent):
    def __init__(self, name: str, sub_agents: list[BaseAgent], **kwargs: Any):
        super().__init__(
            name,
            AgentType.SEQUENTIAL,
            AgentConfig(
                name=name,
                agent_type=AgentType.SEQUENTIAL,
                sub_agents=list(sub_agents),
            ),
            **kwargs,
        )

    async def run_async(
        self,
        session: Session,
        input: str,
        provider: ModelProvider | None = None,
        config: Any = None,
    ) -> list[Event]:
        from .flows import Flow

        result = await Flow(
            name=self.name,
            agents=self.config.sub_agents,
        ).run(input, session=session, provider=provider, config=config)
        return result.events


class CustomAgent(BaseAgent):
    def __init__(
        self,
        name: str,
        run_function: Callable,
        description: str = "",
        **kwargs: Any,
    ):
        self.run_function = run_function
        super().__init__(
            name,
            AgentType.CUSTOM,
            AgentConfig(name=name, agent_type=AgentType.CUSTOM, description=description),
            **kwargs,
        )

    async def run_async(
        self,
        session: Session,
        input: str,
        provider: ModelProvider | None = None,
        config: Any = None,
    ) -> list[Event]:
        result = self.run_function(session, input, provider, config)
        if hasattr(result, "__await__"):
            result = await result
        if not isinstance(result, list) or not all(isinstance(event, Event) for event in result):
            raise TypeError("CustomAgent run_function must return a list of Event objects")
        return result


def create_llm_agent(
    name: str,
    instruction: str = "",
    model: str = "fast",
    tools: list[BaseTool] | None = None,
    description: str = "",
    **kwargs: Any,
) -> LlmAgent:
    return LlmAgent(
        name=name,
        instruction=instruction,
        model=model,
        tools=tools,
        description=description,
        **kwargs,
    )


def create_loop_agent(
    name: str,
    sub_agents: list[BaseAgent],
    max_iterations: int = 10,
    **kwargs: Any,
) -> LoopAgent:
    return LoopAgent(name, sub_agents, max_iterations=max_iterations, **kwargs)


def create_parallel_agent(
    name: str,
    sub_agents: list[BaseAgent],
    **kwargs: Any,
) -> ParallelAgent:
    return ParallelAgent(name, sub_agents, **kwargs)


def create_sequential_agent(
    name: str,
    sub_agents: list[BaseAgent],
    **kwargs: Any,
) -> SequentialAgent:
    return SequentialAgent(name, sub_agents, **kwargs)


def create_custom_agent(
    name: str,
    run_function: Callable,
    description: str = "",
    **kwargs: Any,
) -> CustomAgent:
    return CustomAgent(name, run_function, description=description, **kwargs)
