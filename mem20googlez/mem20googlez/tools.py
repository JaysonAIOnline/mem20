from __future__ import annotations

import asyncio
import copy
import inspect
import os
import re
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from html import unescape
from pathlib import Path
from typing import Any, ClassVar, get_type_hints

import httpx
from pydantic import create_model


@dataclass
class ToolContext:
    agent_name: str = ""
    session_id: str = ""
    invocation_id: str = ""
    state: dict = field(default_factory=dict)
    artifacts: dict = field(default_factory=dict)


class BaseTool:
    name: str = "tool"
    description: str = "A callable tool."
    parameters_schema: ClassVar[dict] = {"type": "object", "properties": {}}

    def __init__(
        self,
        name: str | None = None,
        description: str | None = None,
        parameters_schema: dict | None = None,
    ):
        self.name = name or getattr(type(self), "name", None) or type(self).__name__.lower()
        self.description = (
            description
            or getattr(type(self), "description", None)
            or f"Tool: {self.name}"
        )
        self.__dict__["parameters_schema"] = copy.deepcopy(
            parameters_schema
            or getattr(type(self), "parameters_schema", None)
            or {"type": "object", "properties": {}}
        )

    async def run_async(self, args: dict, context: ToolContext) -> Any:
        raise TypeError(f"{type(self).__name__} must implement run_async")

    def run(self, args: dict, context: ToolContext) -> Any:
        return asyncio.run(self.run_async(args, context))

    def to_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": copy.deepcopy(self.parameters_schema),
            },
        }


class FunctionTool(BaseTool):
    def __init__(
        self,
        func: Callable,
        name: str | None = None,
        description: str | None = None,
        parameters_schema: dict | None = None,
    ):
        self.func = func
        inferred_name = name or getattr(func, "__name__", "function")
        inferred_description = description or inspect.getdoc(func) or f"Tool: {inferred_name}"
        super().__init__(inferred_name, inferred_description, parameters_schema)
        if not self.parameters_schema.get("properties"):
            self.__dict__["parameters_schema"] = self._infer_schema(func)

    def _infer_schema(self, func: Callable) -> dict:
        signature = inspect.signature(func)
        try:
            hints = get_type_hints(func)
        except (NameError, TypeError):
            hints = {}
        fields: dict[str, tuple[Any, Any]] = {}
        required: list[str] = []
        for parameter_name, parameter in signature.parameters.items():
            if parameter_name in {"context", "ctx", "tool_context", "self", "cls"}:
                continue
            if parameter.kind in {parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD}:
                continue
            annotation = hints.get(parameter_name, parameter.annotation)
            if annotation is inspect.Parameter.empty:
                annotation = Any
            default = ... if parameter.default is inspect.Parameter.empty else parameter.default
            fields[parameter_name] = (annotation, default)
            if default is ...:
                required.append(parameter_name)
        model = create_model(f"{self.name.replace('-', '_')}Params", **fields)
        schema = model.model_json_schema()
        if required:
            schema["required"] = required
        else:
            schema.pop("required", None)
        return schema

    async def run_async(self, args: dict, context: ToolContext) -> Any:
        call_args = dict(args or {})
        signature = inspect.signature(self.func)
        for context_name in ("context", "ctx", "tool_context"):
            if context_name in signature.parameters:
                call_args[context_name] = context
                break
        if inspect.iscoroutinefunction(self.func):
            return await self.func(**call_args)
        return await asyncio.to_thread(self.func, **call_args)


class BaseToolset:
    async def get_tools(self, context: ToolContext | None = None) -> list[BaseTool]:
        return []

    def get_tool(self, name: str, context: ToolContext | None = None) -> BaseTool | None:
        tools = self.get_tools(context)
        if inspect.isawaitable(tools):
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                tools = asyncio.run(tools)
            else:
                raise RuntimeError("use an awaitable toolset lookup inside an event loop")
        return next((tool for tool in tools if tool.name == name), None)


class Toolset(BaseToolset):
    def __init__(self, tools: list[BaseTool]):
        self._tools = list(tools)

    async def get_tools(self, context: ToolContext | None = None) -> list[BaseTool]:
        return list(self._tools)


_DDG_URL = "https://html.duckduckgo.com/html/"


class GoogleSearchTool(BaseTool):
    name = "google_search"
    description = "Search the web and return titled results with URLs and snippets."
    parameters_schema: ClassVar[dict] = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer", "default": 5, "minimum": 1, "maximum": 20},
        },
        "required": ["query"],
    }

    def __init__(self, client: httpx.AsyncClient | None = None):
        super().__init__(self.name, self.description, self.parameters_schema)
        self._client = client

    async def run_async(self, args: dict, context: ToolContext) -> Any:
        query = str((args or {}).get("query", "")).strip()
        max_results = max(1, min(int((args or {}).get("max_results", 5)), 20))
        if not query:
            return {"query": "", "results": [], "count": 0, "error": "query is required"}
        headers = {"User-Agent": "mem20googlez/0.2"}
        if self._client is not None:
            response = await self._client.get(_DDG_URL, params={"q": query}, headers=headers)
        else:
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True, headers=headers) as client:
                response = await client.get(_DDG_URL, params={"q": query})
        response.raise_for_status()
        results: list[dict] = []
        for match in re.finditer(
            r'<a[^>]*class=["\']result__a["\'][^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
            response.text,
            re.IGNORECASE | re.DOTALL,
        ):
            title = unescape(re.sub(r"<[^>]+>", "", match.group(2))).strip()
            results.append({"title": title or match.group(1), "url": match.group(1), "snippet": ""})
            if len(results) >= max_results:
                break
        return {"query": query, "results": results, "count": len(results)}


class CodeExecutorTool(BaseTool):
    name = "code_executor"
    description = "Execute Python code in a subprocess and return stdout, stderr and exit code."
    parameters_schema: ClassVar[dict] = {
        "type": "object",
        "properties": {
            "code": {"type": "string"},
            "timeout": {"type": "integer", "default": 30, "minimum": 1, "maximum": 120},
        },
        "required": ["code"],
    }

    async def run_async(self, args: dict, context: ToolContext) -> Any:
        code = str((args or {}).get("code", ""))
        timeout = max(1, min(int((args or {}).get("timeout", 30)), 120))
        if not code.strip():
            return {"output": "", "stderr": "code is required", "exit_code": 2}
        with tempfile.TemporaryDirectory(prefix="mem20googlez_exec_") as directory:
            script_path = os.path.join(directory, "script.py")
            await asyncio.to_thread(
                Path(script_path).write_text,
                code,
                encoding="utf-8",
            )
            result = await run_subprocess([sys.executable, script_path], directory, timeout)
        return {
            "output": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
        }


class BashTool(BaseTool):
    name = "bash"
    description = "Run a bash command and return stdout, stderr and exit code."
    parameters_schema: ClassVar[dict] = {
        "type": "object",
        "properties": {
            "command": {"type": "string"},
            "timeout": {"type": "integer", "default": 30, "minimum": 1, "maximum": 120},
        },
        "required": ["command"],
    }

    async def run_async(self, args: dict, context: ToolContext) -> Any:
        command = str((args or {}).get("command", ""))
        timeout = max(1, min(int((args or {}).get("timeout", 30)), 120))
        if not command.strip():
            return {"output": "", "stderr": "command is required", "exit_code": 2}
        result = await run_subprocess(["bash", "-c", command], tempfile.gettempdir(), timeout)
        return {
            "output": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
        }


@dataclass
class ExecResult:
    stdout: str
    stderr: str
    returncode: int


async def run_subprocess(argv: list[str], cwd: str, timeout: int) -> ExecResult:
    process = await asyncio.create_subprocess_exec(
        *argv,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except TimeoutError:
        process.kill()
        await process.wait()
        return ExecResult(stdout="", stderr="process timed out", returncode=-9)
    return ExecResult(
        stdout=stdout.decode("utf-8", errors="replace"),
        stderr=stderr.decode("utf-8", errors="replace"),
        returncode=process.returncode if process.returncode is not None else -1,
    )


def function_tool(
    func: Callable | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
) -> Any:
    if func is None:
        return lambda candidate: function_tool(candidate, name=name, description=description)
    return FunctionTool(func, name=name, description=description)
