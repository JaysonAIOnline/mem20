from __future__ import annotations

import asyncio
import inspect
import json
import uuid
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass, field
from typing import Any

from .agents import BaseAgent
from .config import DEFAULT_CONFIG, GoogleADKConfig
from .events import Event
from .memory import BaseMemoryService, FileMemoryService, InMemoryMemoryService, MemoryEntry
from .providers import ModelProvider, ModelResponse
from .sessions import (
    BaseSessionService,
    DatabaseSessionService,
    InMemorySessionService,
    Session,
)
from .tools import ToolContext


@dataclass
class RunConfig:
    model: str = "fast"
    max_turns: int = 10
    temperature: float = 1.0
    top_p: float = 1.0
    top_k: int = 40
    max_tokens: int | None = None
    save_input_blobs_as_artifacts: bool = False
    response_modalities: list[str] = field(default_factory=list)
    speech_config: dict | None = None


@dataclass
class RunResult:
    session: Session
    events: list[Event]
    final_output: str | None = None
    error: str | None = None


def events_to_messages(events: list[Event]) -> list[dict]:
    messages: list[dict] = []
    for event in events:
        if event.is_tool_response():
            response = event.tool_response() or {}
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": str(response.get("id") or response.get("name", "")),
                    "name": response.get("name", ""),
                    "content": json.dumps(response.get("response"), default=str),
                }
            )
        elif event.is_tool_call():
            call = event.tool_call() or {}
            messages.append(
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": call.get("id") or call.get("name", ""),
                            "name": call.get("name", ""),
                            "arguments": call.get("arguments") or {},
                        }
                    ],
                }
            )
        elif event.author == "user":
            text = event.text()
            if text:
                messages.append({"role": "user", "content": text})
        elif event.author == "model":
            text = event.text()
            if text:
                messages.append({"role": "assistant", "content": text})
        elif event.author == "system":
            text = event.text() or event.error_message
            if text:
                messages.append({"role": "system", "content": text})
    return messages


def _last_model_text(events: list[Event]) -> str:
    for event in reversed(events):
        if event.author == "model" and event.text():
            return event.text()
    return ""


def _tools_schema(agent: BaseAgent) -> list[dict]:
    return [tool.to_schema() for tool in agent.config.tools]


def _ensure_system(messages: list[dict], instruction: str, memory_context: str = "") -> list[dict]:
    without_system = [message for message in messages if message.get("role") != "system"]
    system_parts = [part for part in (instruction.strip(), memory_context.strip()) if part]
    if not system_parts:
        return without_system
    return [{"role": "system", "content": "\n\n".join(system_parts)}, *without_system]


def _trailing_user_matches(messages: list[dict], value: str) -> bool:
    return bool(
        messages
        and messages[-1].get("role") == "user"
        and messages[-1].get("content") == value
    )


async def _call_provider(
    provider: ModelProvider,
    messages: list[dict],
    tools: list[dict] | None,
    model: str,
    config: RunConfig,
) -> Any:
    candidates = {
        "model": model,
        "temperature": config.temperature,
        "top_p": config.top_p,
        "top_k": config.top_k,
        "max_tokens": config.max_tokens,
    }
    try:
        parameters = inspect.signature(provider.generate).parameters
    except (TypeError, ValueError):
        parameters = {}
    if any(parameter.kind == parameter.VAR_KEYWORD for parameter in parameters.values()):
        accepted = candidates
    else:
        accepted = {key: value for key, value in candidates.items() if key in parameters}
    return await provider.generate(messages, tools, **accepted)


async def _notify(callback: Callable | None, *args: Any) -> Any:
    if callback is None:
        return None
    try:
        parameters = inspect.signature(callback).parameters.values()
        if not any(parameter.kind == parameter.VAR_POSITIONAL for parameter in parameters):
            args = args[: len(parameters)]
    except (TypeError, ValueError):
        pass
    result = callback(*args)
    if inspect.isawaitable(result):
        return await result
    return result


async def _run_tool_loop(
    agent: BaseAgent,
    messages: list[dict],
    provider: ModelProvider,
    config: RunConfig,
    turn_budget: int,
    session: Session | None,
    on_event: Callable[[Event], Any] | None = None,
    memory_context: str = "",
    invocation_id: str | None = None,
) -> tuple[list[Event], list[dict]]:
    events: list[Event] = []
    tool_by_name = {tool.name: tool for tool in agent.config.tools}
    subagent_by_name = {subagent.name: subagent for subagent in agent.config.sub_agents}
    context = ToolContext(
        agent_name=agent.name,
        session_id=session.id if session else "",
        invocation_id=invocation_id or "",
        state=session.state.data if session else {},
        artifacts={},
    )
    invocation = invocation_id or uuid.uuid4().hex[:16]
    context.invocation_id = invocation
    remaining_turns = max(1, int(turn_budget))
    turns = 0
    messages = list(messages)

    while turns < remaining_turns:
        request_messages = _ensure_system(messages, agent.config.instruction, memory_context)
        before = await _notify(
            agent.config.before_model_callback,
            request_messages,
            agent,
            provider,
        )
        if isinstance(before, list):
            request_messages = before
        response = await _call_provider(
            provider,
            request_messages,
            _tools_schema(agent) or None,
            agent.config.model or config.model,
            config,
        )
        after = await _notify(
            agent.config.after_model_callback,
            response,
            agent,
            provider,
        )
        if isinstance(after, ModelResponse):
            response = after
        turns += 1
        calls = list(response.tool_calls)
        text = response.text or ""
        if text or calls:
            model_event = Event.from_model(
                invocation,
                "model",
                text,
                turn_complete=not calls,
            )
            if text:
                events.append(model_event)
                await _notify(on_event, model_event)
            assistant_message: dict[str, Any] = {
                "role": "assistant",
                "content": text,
            }
            if calls:
                assistant_message["tool_calls"] = [
                    {
                        "id": call.id or call.name,
                        "name": call.name,
                        "arguments": call.arguments,
                    }
                    for call in calls
                ]
            messages.append(assistant_message)

        if not calls:
            break

        for call in calls:
            call_id = call.id or call.name
            call_event = Event.from_tool_call(
                invocation,
                "model",
                call.name,
                call.arguments,
                call_id=call_id,
            )
            events.append(call_event)
            await _notify(on_event, call_event)

            if call.name in subagent_by_name and call.name not in tool_by_name:
                subagent = subagent_by_name[call.name]
                sub_events, _ = await _run_tool_loop(
                    subagent,
                    messages,
                    provider,
                    config,
                    max(1, remaining_turns - turns),
                    session,
                    on_event,
                    memory_context,
                    invocation,
                )
                events.extend(sub_events)
                payload: Any = {
                    "agent": subagent.name,
                    "output": _last_model_text(sub_events),
                }
            else:
                tool = tool_by_name.get(call.name)
                if tool is None:
                    payload = {"error": f"unknown tool: {call.name}"}
                else:
                    try:
                        before = await _notify(agent.config.before_tool_callback, call.arguments, context)
                        if isinstance(before, dict):
                            call.arguments = before
                        payload = await tool.run_async(call.arguments, context)
                        after = await _notify(agent.config.after_tool_callback, call.name, payload, context)
                        if after is not None:
                            payload = after
                    except Exception as exc:
                        payload = {"error": f"{type(exc).__name__}: {exc}"}
                if tool is not None and isinstance(context.state, dict):
                    context.state.setdefault("last_tool", {"name": call.name, "result": payload})

            response_event = Event.from_tool_response(
                invocation,
                "tool",
                call.name,
                payload,
                call_id=call_id,
            )
            events.append(response_event)
            await _notify(on_event, response_event)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "name": call.name,
                    "content": json.dumps(payload, default=str),
                }
            )

    return events, messages


async def run_agent(
    agent: BaseAgent,
    session: Session | None,
    input: str,
    config: RunConfig | None = None,
    provider: ModelProvider | None = None,
    max_turns: int | None = None,
    on_event: Callable[[Event], Any] | None = None,
    memory_context: str = "",
) -> list[Event]:
    cfg = config or RunConfig()
    active_provider = provider
    if active_provider is None:
        from .providers import resolve_provider

        active_provider = await resolve_provider(DEFAULT_CONFIG)
    if session is not None and session.events:
        messages = events_to_messages(session.events)
    else:
        messages = []
    if input and not _trailing_user_matches(messages, input):
        messages.append({"role": "user", "content": input})
    events, _ = await _run_tool_loop(
        agent,
        messages,
        active_provider,
        cfg,
        max_turns or cfg.max_turns,
        session,
        on_event,
        memory_context,
    )
    return events


class BaseRunner:
    async def run_async(
        self,
        agent: BaseAgent,
        session: Session,
        input: str,
        config: RunConfig | None = None,
    ) -> RunResult:
        raise TypeError(f"{type(self).__name__} must implement run_async")

    def run_stream_async(
        self,
        agent: BaseAgent,
        session: Session,
        input: str,
        config: RunConfig | None = None,
    ) -> AsyncGenerator[Event, None]:
        raise TypeError(f"{type(self).__name__} must implement run_stream_async")


class Runner(BaseRunner):
    def __init__(
        self,
        agent: BaseAgent,
        session_service: BaseSessionService,
        memory_service: BaseMemoryService | None = None,
        config: RunConfig | None = None,
        provider: ModelProvider | None = None,
        config_data: GoogleADKConfig | None = None,
    ):
        self.agent = agent
        self.session_service = session_service
        self.memory_service = memory_service
        self.config = config or RunConfig()
        self.provider = provider
        self.config_data = config_data or DEFAULT_CONFIG

    async def _get_provider(self) -> ModelProvider:
        if self.provider is None:
            from .providers import resolve_provider

            self.provider = await resolve_provider(self.config_data)
        return self.provider

    async def _memory_context(self, session: Session, query: str) -> str:
        if self.memory_service is None:
            return ""
        memories = await self.memory_service.search_memory(
            session.app_name,
            session.user_id,
            query,
            limit=5,
        )
        if not memories:
            return ""
        lines = [f"- {memory.content}" for memory in memories if memory.content]
        if not lines:
            return ""
        return "Relevant persisted memory:\n" + "\n".join(lines)

    async def _remember(self, session: Session, text: str, author: str, event_id: str) -> None:
        if self.memory_service is None or not text:
            return
        await self.memory_service.add_memory(
            session.app_name,
            session.user_id,
            session.id,
            MemoryEntry(
                content=text,
                author=author,
                metadata={"event_id": event_id, "session_id": session.id},
            ),
        )

    async def _append(self, session: Session, event: Event) -> None:
        await self.session_service.append_event(session, event)
        if event.author in {"user", "model"} and event.text():
            await self._remember(session, event.text(), event.author, event.id)

    async def run_async(
        self,
        agent: BaseAgent,
        session: Session,
        input: str,
        config: RunConfig | None = None,
    ) -> RunResult:
        cfg = config or self.config
        invocation = uuid.uuid4().hex[:16]
        memory_context = await self._memory_context(session, input)
        user_event = Event.from_model(invocation, "user", input)
        run_events: list[Event] = [user_event]
        await self._append(session, user_event)
        try:
            provider = await self._get_provider()
            agent_events = await run_agent(
                agent,
                session,
                input,
                cfg,
                provider=provider,
                max_turns=cfg.max_turns,
                memory_context=memory_context,
            )
            for event in agent_events:
                await self._append(session, event)
                run_events.append(event)
        except Exception as exc:
            error_event = Event(
                id=f"evt_{uuid.uuid4().hex}",
                invocation_id=invocation,
                author="system",
                content=None,
                error_code=type(exc).__name__,
                error_message=str(exc),
                turn_complete=True,
            )
            await self.session_service.append_event(session, error_event)
            run_events.append(error_event)
            return RunResult(session=session, events=run_events, error=str(exc))
        return RunResult(
            session=session,
            events=run_events,
            final_output=_last_model_text(agent_events),
        )

    async def run_stream_async(
        self,
        agent: BaseAgent,
        session: Session,
        input: str,
        config: RunConfig | None = None,
    ) -> AsyncGenerator[Event, None]:
        cfg = config or self.config
        invocation = uuid.uuid4().hex[:16]
        memory_context = await self._memory_context(session, input)
        user_event = Event.from_model(invocation, "user", input)
        await self._append(session, user_event)
        yield user_event
        queue: asyncio.Queue[Event | None] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def emit(event: Event | None) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, event)

        async def worker() -> None:
            try:
                provider = await self._get_provider()
                await run_agent(
                    agent,
                    session,
                    input,
                    cfg,
                    provider=provider,
                    max_turns=cfg.max_turns,
                    on_event=emit,
                    memory_context=memory_context,
                )
            except Exception as exc:
                emit(
                    Event(
                        id=f"evt_{uuid.uuid4().hex}",
                        invocation_id=invocation,
                        author="system",
                        error_code=type(exc).__name__,
                        error_message=str(exc),
                        turn_complete=True,
                    )
                )
            finally:
                emit(None)

        task = asyncio.create_task(worker())
        while True:
            event = await queue.get()
            if event is None:
                break
            await self._append(session, event)
            yield event
        await task


class InMemoryRunner(Runner):
    def __init__(
        self,
        agent: BaseAgent,
        app_name: str,
        session_service: BaseSessionService | None = None,
        memory_service: BaseMemoryService | None = None,
        config: RunConfig | None = None,
        provider: ModelProvider | None = None,
        config_data: GoogleADKConfig | None = None,
    ):
        super().__init__(
            agent,
            session_service or InMemorySessionService(),
            memory_service or InMemoryMemoryService(),
            config,
            provider,
            config_data,
        )
        self.app_name = app_name

    async def run(
        self,
        user_id: str,
        session_id: str | None = None,
        input: str = "",
        config: RunConfig | None = None,
    ) -> RunResult:
        session = (
            await self.session_service.get_session(self.app_name, user_id, session_id)
            if session_id
            else None
        )
        if session is None:
            session = await self.session_service.create_session(
                self.app_name,
                user_id,
                session_id,
            )
        return await self.run_async(self.agent, session, input, config)


class DurableRunner(Runner):
    def __init__(
        self,
        agent: BaseAgent,
        app_name: str,
        session_service: BaseSessionService | None = None,
        memory_service: BaseMemoryService | None = None,
        config: RunConfig | None = None,
        provider: ModelProvider | None = None,
        config_data: GoogleADKConfig | None = None,
    ):
        cfg = config_data or DEFAULT_CONFIG
        super().__init__(
            agent,
            session_service or DatabaseSessionService(cfg.session_db_path),
            memory_service or FileMemoryService(cfg.memory_dir),
            config,
            provider,
            cfg,
        )
        self.app_name = app_name

    async def run(
        self,
        user_id: str,
        session_id: str | None = None,
        input: str = "",
        config: RunConfig | None = None,
    ) -> RunResult:
        session = (
            await self.session_service.get_session(self.app_name, user_id, session_id)
            if session_id
            else None
        )
        if session is None:
            session = await self.session_service.create_session(
                self.app_name,
                user_id,
                session_id,
            )
        return await self.run_async(self.agent, session, input, config)
