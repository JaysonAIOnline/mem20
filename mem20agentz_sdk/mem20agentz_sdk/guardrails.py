"""Guardrail primitives — native absorption of OpenAI Agents SDK guardrails."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .tools import ToolContext


@dataclass
class GuardrailFunctionOutput:
    """Output of a guardrail function."""
    output_info: Any
    tripwire_triggered: bool = False


@dataclass
class InputGuardrailResult:
    """Result of input guardrail check."""
    guardrail: "InputGuardrail"
    output: GuardrailFunctionOutput


@dataclass
class OutputGuardrailResult:
    """Result of output guardrail check."""
    guardrail: "OutputGuardrail"
    output: GuardrailFunctionOutput


class InputGuardrail(ABC):
    """Input guardrail - runs before agent processes input."""

    name: str

    @abstractmethod
    async def check(self, input: str, context: ToolContext) -> GuardrailFunctionOutput:
        pass


class OutputGuardrail(ABC):
    """Output guardrail - runs after agent produces output."""

    name: str

    @abstractmethod
    async def check(self, output: str, context: ToolContext) -> GuardrailFunctionOutput:
        pass


class FunctionInputGuardrail(InputGuardrail):
    """Function-based input guardrail."""

    def __init__(
        self,
        func: Callable,
        name: Optional[str] = None,
    ):
        self.func = func
        self.name = name or func.__name__

    async def check(self, input: str, context: ToolContext) -> GuardrailFunctionOutput:
        if asyncio.iscoroutinefunction(self.func):
            result = await self.func(input, context)
        else:
            result = self.func(input, context)

        if isinstance(result, GuardrailFunctionOutput):
            return result
        return GuardrailFunctionOutput(output_info=result, tripwire_triggered=bool(result))


class FunctionOutputGuardrail(OutputGuardrail):
    """Function-based output guardrail."""

    def __init__(
        self,
        func: Callable,
        name: Optional[str] = None,
    ):
        self.func = func
        self.name = name or func.__name__

    async def check(self, output: str, context: ToolContext) -> GuardrailFunctionOutput:
        if asyncio.iscoroutinefunction(self.func):
            result = await self.func(output, context)
        else:
            result = self.func(output, context)

        if isinstance(result, GuardrailFunctionOutput):
            return result
        return GuardrailFunctionOutput(output_info=result, tripwire_triggered=bool(result))


def input_guardrail(
    func: Callable = None,
    *,
    name: Optional[str] = None,
) -> FunctionInputGuardrail:
    """Decorator to create an input guardrail."""
    if func is None:
        return lambda f: input_guardrail(f, name=name)
    return FunctionInputGuardrail(func, name=name)


def output_guardrail(
    func: Callable = None,
    *,
    name: Optional[str] = None,
) -> FunctionOutputGuardrail:
    """Decorator to create an output guardrail."""
    if func is None:
        return lambda f: output_guardrail(f, name=name)
    return FunctionOutputGuardrail(func, name=name)