"""Tool primitives — native absorption of OpenAI Agents SDK tools."""

from __future__ import annotations

import asyncio
import inspect
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, get_type_hints

from pydantic import BaseModel, create_model


@dataclass
class ToolContext:
    """Context passed to tool functions."""
    agent_name: str = ""
    run_id: str = ""
    metadata: dict = field(default_factory=dict)


class Tool(ABC):
    """Base tool class."""

    name: str
    description: str
    params_schema: dict

    @abstractmethod
    async def invoke(self, args: dict, context: ToolContext) -> Any:
        pass


class FunctionTool(Tool):
    """Function-based tool."""

    def __init__(
        self,
        func: Callable,
        name: Optional[str] = None,
        description: Optional[str] = None,
        params_schema: Optional[dict] = None,
    ):
        self.func = func
        self.name = name or func.__name__
        self.description = description or func.__doc__ or f"Tool: {self.name}"
        self.params_schema = params_schema or self._infer_schema(func)

    def _infer_schema(self, func: Callable) -> dict:
        """Infer JSON schema from function signature."""
        sig = inspect.signature(func)
        hints = get_type_hints(func)
        fields = {}
        required = []

        for param_name, param in sig.parameters.items():
            if param_name in ("context", "self", "cls"):
                continue
            param_type = hints.get(param_name, Any)
            default = ... if param.default == inspect.Parameter.empty else param.default
            if default is ...:
                required.append(param_name)
            fields[param_name] = (param_type, default)

        model = create_model(f"{self.name}Params", **fields)
        schema = model.model_json_schema()
        schema["required"] = required
        return schema

    async def invoke(self, args: dict, context: ToolContext) -> Any:
        call_args = args.copy()
        sig = inspect.signature(self.func)
        if "context" in sig.parameters:
            call_args["context"] = context
        elif "ctx" in sig.parameters:
            call_args["ctx"] = context
        if inspect.iscoroutinefunction(self.func):
            return await self.func(**call_args)
        return self.func(**call_args)


class ComputerTool(Tool):
    """Computer interaction tool."""

    name = "computer"
    description = "Control a computer (mouse, keyboard, screenshot)"
    params_schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["click", "type", "scroll", "screenshot", "move"]},
            "x": {"type": "integer"},
            "y": {"type": "integer"},
            "text": {"type": "string"},
        },
        "required": ["action"],
    }

    async def invoke(self, args: dict, context: ToolContext) -> Any:
        return {"status": "simulated", "action": args.get("action")}


class WebSearchTool(Tool):
    """Web search tool."""

    name = "web_search"
    description = "Search the web"
    params_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer", "default": 10},
        },
        "required": ["query"],
    }

    async def invoke(self, args: dict, context: ToolContext) -> Any:
        return {"results": [], "query": args.get("query")}


class FileSearchTool(Tool):
    """File search tool."""

    name = "file_search"
    description = "Search files"
    params_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer", "default": 10},
        },
        "required": ["query"],
    }

    async def invoke(self, args: dict, context: ToolContext) -> Any:
        return {"results": [], "query": args.get("query")}


def function_tool(
    func: Callable = None,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
) -> FunctionTool:
    """Decorator to create a FunctionTool."""
    if func is None:
        return lambda f: function_tool(f, name=name, description=description)
    return FunctionTool(func, name=name, description=description)