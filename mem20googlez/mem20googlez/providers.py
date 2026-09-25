from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

import httpx

from .config import DEFAULT_CONFIG, GoogleADKConfig

logger = logging.getLogger(__name__)

TIER_MODELS = ("fast", "balanced", "strong")


class ProviderError(RuntimeError):
    """Raised when a configured model endpoint cannot complete a request."""


@dataclass
class ModelToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class ModelResponse:
    text: str = ""
    tool_calls: list[ModelToolCall] = field(default_factory=list)
    finish_reason: str = "stop"
    raw: dict = field(default_factory=dict)


def _coerce_arguments(arguments: Any) -> dict:
    if isinstance(arguments, dict):
        return dict(arguments)
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
        except (TypeError, ValueError):
            return {"value": arguments}
        return dict(parsed) if isinstance(parsed, dict) else {"value": parsed}
    return {"value": arguments}


def _content_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "".join(parts)
    return ""


def _tool_schema_names(tools: list[dict] | None) -> set[str]:
    names: set[str] = set()
    for tool in tools or []:
        function = tool.get("function", tool) if isinstance(tool, dict) else {}
        name = function.get("name") if isinstance(function, dict) else None
        if name:
            names.add(str(name))
    return names


class ModelProvider:
    name = "unknown"

    @property
    def model(self) -> str:
        return str(getattr(self, "default_model", ""))

    async def generate(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        model: str | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        top_k: int | None = None,
        max_tokens: int | None = None,
    ) -> ModelResponse:
        raise TypeError(f"{type(self).__name__} must implement generate")

    async def health(self) -> tuple[bool, str]:
        return False, f"{type(self).__name__} has no health implementation"


class OllamaProvider(ModelProvider):
    name = "ollama"

    def __init__(
        self,
        url: str,
        default_model: str = "qwen2.5-coder:0.5b",
        client: httpx.AsyncClient | None = None,
        timeout: float = 120.0,
    ):
        self.url = url.rstrip("/")
        self.default_model = default_model
        self._client = client
        self.timeout = timeout

    @property
    def model(self) -> str:
        return self.default_model

    @asynccontextmanager
    async def _http(self) -> AsyncIterator[httpx.AsyncClient]:
        if self._client is not None:
            yield self._client
        else:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                yield client

    def _translate_messages(self, messages: list[dict]) -> list[dict]:
        translated: list[dict] = []
        for message in messages:
            role = message.get("role", "user")
            if role == "assistant" and message.get("tool_calls"):
                calls = []
                for index, call in enumerate(message["tool_calls"]):
                    arguments = call.get("arguments") or {}
                    calls.append(
                        {
                            "id": call.get("id") or f"call_{index}",
                            "type": "function",
                            "function": {
                                "name": call.get("name", ""),
                                "arguments": _coerce_arguments(arguments),
                            },
                        }
                    )
                translated.append(
                    {
                        "role": "assistant",
                        "content": _content_text(message.get("content", "")),
                        "tool_calls": calls,
                    }
                )
            elif role == "tool":
                translated.append(
                    {
                        "role": "tool",
                        "content": _content_text(message.get("content", "")),
                        "tool_name": message.get("name", ""),
                    }
                )
            else:
                translated.append({"role": role, "content": _content_text(message.get("content", ""))})
        return translated

    @staticmethod
    def _parse_tool_call_text(content: str, tools: list[dict] | None) -> ModelToolCall | None:
        text = content.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if len(lines) >= 3:
                text = "\n".join(lines[1:-1]).strip()
        if not (text.startswith("{") and text.endswith("}")):
            return None
        try:
            data = json.loads(text)
        except (TypeError, ValueError):
            return None
        if not isinstance(data, dict):
            return None
        function = data.get("function") if isinstance(data.get("function"), dict) else data
        name = function.get("name")
        arguments = function.get("arguments", {})
        if not name or name not in _tool_schema_names(tools):
            return None
        return ModelToolCall(
            id=str(data.get("id") or name),
            name=str(name),
            arguments=_coerce_arguments(arguments),
        )

    def _options(
        self,
        temperature: float | None,
        top_p: float | None,
        top_k: int | None,
        max_tokens: int | None,
    ) -> dict:
        options: dict[str, Any] = {}
        if temperature is not None:
            options["temperature"] = temperature
        if top_p is not None:
            options["top_p"] = top_p
        if top_k is not None:
            options["top_k"] = top_k
        if max_tokens is not None:
            options["num_predict"] = max_tokens
        return options

    async def generate(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        model: str | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        top_k: int | None = None,
        max_tokens: int | None = None,
    ) -> ModelResponse:
        requested = model or self.default_model
        if requested in TIER_MODELS or not requested:
            requested = self.default_model
        has_tool_result = any(message.get("role") == "tool" for message in messages)
        request_tools = None if has_tool_result else tools
        known_tools = tools or []
        payload: dict[str, Any] = {
            "model": requested,
            "messages": self._translate_messages(messages),
            "stream": False,
        }
        if request_tools:
            payload["tools"] = request_tools
        options = self._options(temperature, top_p, top_k, max_tokens)
        if options:
            payload["options"] = options
        async with self._http() as client:
            try:
                response = await client.post(f"{self.url}/api/chat", json=payload)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise ProviderError(f"Ollama request failed at {self.url}: {exc}") from exc
            data = response.json()
        message = data.get("message") or {}
        text = _content_text(message.get("content", ""))
        calls: list[ModelToolCall] = []
        for index, raw_call in enumerate(message.get("tool_calls") or []):
            function = raw_call.get("function", raw_call) if isinstance(raw_call, dict) else {}
            if not isinstance(function, dict):
                continue
            name = function.get("name")
            if not name:
                continue
            calls.append(
                ModelToolCall(
                    id=str(raw_call.get("id") or name or index),
                    name=str(name),
                    arguments=_coerce_arguments(function.get("arguments", {})),
                )
            )
        if not calls and text:
            parsed = self._parse_tool_call_text(text, known_tools)
            if parsed is not None:
                calls.append(parsed)
                text = ""
        return ModelResponse(
            text=text,
            tool_calls=calls,
            finish_reason=str(data.get("done_reason") or "stop"),
            raw=data,
        )

    async def health(self) -> tuple[bool, str]:
        try:
            async with self._http() as client:
                response = await client.get(f"{self.url}/api/tags")
            if response.status_code != 200:
                return False, f"ollama ({self.url}) HTTP {response.status_code}"
            names = [item.get("name") for item in response.json().get("models", [])]
            available = self.default_model in names
            suffix = "model present" if available else "default model absent"
            return available, f"ollama ({self.url}) {suffix}: {', '.join(str(name) for name in names)}"
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            return False, f"ollama ({self.url}) unreachable: {exc}"


class OpenAICompatibleProvider(ModelProvider):
    name = "gateway"

    def __init__(
        self,
        base_url: str,
        default_model: str = "fast",
        api_key: str | None = None,
        client: httpx.AsyncClient | None = None,
        timeout: float = 120.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self.api_key = api_key
        self._client = client
        self.timeout = timeout

    @property
    def model(self) -> str:
        return self.default_model

    @asynccontextmanager
    async def _http(self) -> AsyncIterator[httpx.AsyncClient]:
        if self._client is not None:
            yield self._client
        else:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                yield client

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _translate_messages(self, messages: list[dict]) -> list[dict]:
        translated: list[dict] = []
        for message in messages:
            role = message.get("role", "user")
            if role == "assistant" and message.get("tool_calls"):
                calls = []
                for index, call in enumerate(message["tool_calls"]):
                    calls.append(
                        {
                            "id": call.get("id") or f"call_{index}",
                            "type": "function",
                            "function": {
                                "name": call.get("name", ""),
                                "arguments": json.dumps(_coerce_arguments(call.get("arguments", {}))),
                            },
                        }
                    )
                translated.append(
                    {
                        "role": "assistant",
                        "content": _content_text(message.get("content", "")),
                        "tool_calls": calls,
                    }
                )
            elif role == "tool":
                translated.append(
                    {
                        "role": "tool",
                        "tool_call_id": message.get("tool_call_id", ""),
                        "name": message.get("name", ""),
                        "content": _content_text(message.get("content", "")),
                    }
                )
            else:
                translated.append({"role": role, "content": _content_text(message.get("content", ""))})
        return translated

    async def generate(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        model: str | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        top_k: int | None = None,
        max_tokens: int | None = None,
    ) -> ModelResponse:
        requested = model or self.default_model
        payload: dict[str, Any] = {
            "model": requested,
            "messages": self._translate_messages(messages),
        }
        if tools:
            payload["tools"] = tools
        if temperature is not None:
            payload["temperature"] = temperature
        if top_p is not None:
            payload["top_p"] = top_p
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        async with self._http() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/v1/chat/completions",
                    json=payload,
                    headers=self._headers(),
                )
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise ProviderError(f"gateway request failed at {self.base_url}: {exc}") from exc
            data = response.json()
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        text = _content_text(message.get("content", ""))
        calls: list[ModelToolCall] = []
        for index, raw_call in enumerate(message.get("tool_calls") or []):
            function = raw_call.get("function", raw_call) if isinstance(raw_call, dict) else {}
            if not isinstance(function, dict) or not function.get("name"):
                continue
            calls.append(
                ModelToolCall(
                    id=str(raw_call.get("id") or f"call_{index}"),
                    name=str(function["name"]),
                    arguments=_coerce_arguments(function.get("arguments", {})),
                )
            )
        return ModelResponse(
            text=text,
            tool_calls=calls,
            finish_reason=str(choice.get("finish_reason") or "stop"),
            raw=data,
        )

    async def health(self) -> tuple[bool, str]:
        try:
            async with self._http() as client:
                response = await client.get(f"{self.base_url}/v1/models", headers=self._headers())
            if response.status_code != 200:
                return False, f"gateway ({self.base_url}) HTTP {response.status_code}"
            return True, f"gateway ({self.base_url}) reachable"
        except (httpx.HTTPError, ValueError) as exc:
            return False, f"gateway ({self.base_url}) unreachable: {exc}"


async def resolve_provider(
    config: GoogleADKConfig | None = None,
    provider: str | None = None,
) -> ModelProvider:
    cfg = config or DEFAULT_CONFIG
    choice = (provider or cfg.provider or "auto").lower()
    if choice in {"ollama", "ollama-native"}:
        return OllamaProvider(
            cfg.ollama_url,
            cfg.default_model,
            timeout=cfg.request_timeout,
        )
    if choice in {"openai", "gateway", "litellm"}:
        return OpenAICompatibleProvider(
            cfg.gateway_url,
            cfg.gateway_model,
            timeout=cfg.request_timeout,
        )
    ollama = OllamaProvider(cfg.ollama_url, cfg.default_model, timeout=cfg.request_timeout)
    healthy, _ = await ollama.health()
    if healthy:
        return ollama
    logger.warning("Ollama unavailable at %s; using gateway %s", cfg.ollama_url, cfg.gateway_url)
    return OpenAICompatibleProvider(cfg.gateway_url, cfg.gateway_model, timeout=cfg.request_timeout)
