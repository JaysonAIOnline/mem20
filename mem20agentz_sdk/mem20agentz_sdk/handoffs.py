"""Handoff primitives — native absorption of OpenAI Agents SDK handoffs."""

from __future__ import annotations

import asyncio
import inspect
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, TYPE_CHECKING

from .tools import ToolContext

if TYPE_CHECKING:
    from .agent import Agent


@dataclass
class HandoffInputData:
    """Data passed during handoff."""
    input: str
    context: dict = field(default_factory=dict)
    history: list = field(default_factory=list)


class HandoffHistoryMapper(ABC):
    """Maps conversation history during handoff.

    Mirrors the OpenAI Agents SDK ``HandoffHistoryMapper`` contract: a mapper
    decides what history the receiving agent sees at three points — the new
    agent's starting history, the next model step, and the handoff message.
    Concrete mappers implement ``input_for_handoff``; the two convenience
    methods default to the same mapping.
    """

    @abstractmethod
    def input_for_handoff(self, history: list) -> list:
        """History the receiving agent starts with after the handoff."""

    def input_for_history(self, history: list) -> list:
        return self.input_for_handoff(history)

    def input_for_next_step(self, history: list) -> list:
        return self.input_for_handoff(history)


@dataclass
class DefaultHandoffHistoryMapper(HandoffHistoryMapper):
    """Passes the full conversation history through to the receiving agent."""

    def input_for_handoff(self, history: list) -> list:
        return default_handoff_history_mapper(history)


@dataclass
class RemoveAllHistoryMapper(HandoffHistoryMapper):
    """Starts the receiving agent with no prior history (full privacy).

    The receiving agent still sees the handoff input itself; everything
    before it is dropped so no inter-agent context leaks across the handoff.
    """

    def input_for_handoff(self, history: list) -> list:
        return []


@dataclass
class Handoff:
    """Handoff between agents."""

    agent_name: str
    agent: Optional["Agent"] = None
    on_handoff: Optional[Callable[[HandoffInputData], Any]] = None
    input_filter: Optional[Callable[[str], str]] = None
    history_mapper: Optional[HandoffHistoryMapper] = None

    def __post_init__(self):
        if self.agent and self.agent_name != self.agent.name:
            self.agent_name = self.agent.name

    async def execute(self, input_data: HandoffInputData) -> "Agent":
        if self.on_handoff:
            if inspect.iscoroutinefunction(self.on_handoff):
                await self.on_handoff(input_data)
            else:
                self.on_handoff(input_data)

        if self.input_filter:
            input_data.input = self.input_filter(input_data.input)

        mapper = self.history_mapper or DefaultHandoffHistoryMapper()
        input_data.history = mapper.input_for_handoff(input_data.history)

        return self.agent


def handoff(
    agent: "Agent",
    *,
    on_handoff: Optional[Callable[[HandoffInputData], Any]] = None,
    input_filter: Optional[Callable[[str], str]] = None,
    history_mapper: Optional[HandoffHistoryMapper] = None,
) -> Handoff:
    """Create a handoff to another agent."""
    return Handoff(
        agent_name=agent.name,
        agent=agent,
        on_handoff=on_handoff,
        input_filter=input_filter,
        history_mapper=history_mapper,
    )


def default_handoff_history_mapper(history: list) -> list:
    """Default handoff history mapper — returns the history unchanged."""
    return list(history)