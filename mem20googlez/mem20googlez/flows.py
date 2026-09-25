from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from .agents import BaseAgent
from .config import GoogleADKConfig
from .events import Event
from .memory import BaseMemoryService
from .providers import ModelProvider
from .runners import DurableRunner, Runner
from .sessions import BaseSessionService, Session


@dataclass
class FlowStepResult:
    agent: BaseAgent
    events: list[Event]
    output: str


@dataclass
class FlowResult:
    flow_name: str
    steps: list[FlowStepResult] = field(default_factory=list)
    final_output: str = ""
    events: list[Event] = field(default_factory=list)


def _last_model_text(events: list[Event]) -> str:
    for event in reversed(events):
        if event.author == "model" and event.text():
            return event.text()
    return ""


class Flow:
    def __init__(
        self,
        name: str,
        agents: list[BaseAgent],
        description: str = "",
        runner: Runner | None = None,
        session_service: BaseSessionService | None = None,
        memory_service: BaseMemoryService | None = None,
        config_data: GoogleADKConfig | None = None,
    ):
        if not agents:
            raise ValueError("a flow requires at least one agent")
        self.name = name
        self.agents = list(agents)
        self.description = description
        self.runner = runner
        self.session_service = session_service
        self.memory_service = memory_service
        self.config_data = config_data

    async def run(
        self,
        input: str,
        session: Session | None = None,
        provider: ModelProvider | None = None,
        config: Any = None,
    ) -> FlowResult:
        active_session = session or Session(
            id=f"flow_{uuid.uuid4().hex[:12]}",
            app_name="mem20googlez",
            user_id="flow",
        )
        active_runner = self.runner
        if active_runner is None and (
            self.session_service is not None or self.memory_service is not None
        ):
            active_runner = DurableRunner(
                self.agents[0],
                active_session.app_name,
                session_service=self.session_service,
                memory_service=self.memory_service,
                provider=provider,
                config_data=self.config_data,
            )
        result = FlowResult(flow_name=self.name)
        current_input = input
        for agent in self.agents:
            if active_runner is None:
                step_events = await agent.run_async(
                    active_session,
                    current_input,
                    provider=provider,
                    config=config,
                )
            else:
                active_runner.agent = agent
                if provider is not None:
                    active_runner.provider = provider
                step_result = await active_runner.run_async(
                    agent,
                    active_session,
                    current_input,
                    config,
                )
                if step_result.error:
                    raise RuntimeError(step_result.error)
                step_events = step_result.events
            output = _last_model_text(step_events) or _last_model_text(result.events)
            result.steps.append(FlowStepResult(agent=agent, events=step_events, output=output))
            result.events.extend(step_events)
            current_input = output
        result.final_output = current_input
        return result

    def to_card(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "agents": [agent.name for agent in self.agents],
        }


async def _run_chain(
    agents: list[BaseAgent],
    session: Session,
    input: str,
    provider: ModelProvider | None = None,
    config: Any = None,
) -> list[Event]:
    result = await Flow(name=session.app_name or "sequential", agents=agents).run(
        input,
        session=session,
        provider=provider,
        config=config,
    )
    return result.events
