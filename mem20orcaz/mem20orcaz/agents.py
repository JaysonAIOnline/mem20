"""Agent execution primitives for mem20orcaz.

BaseAgent (abstract executor interface) and concrete agent types, mirroring
OrKa's agent types but pure-stdlib: the heavy lift (actual model calls) is
delegated to a pluggable ``llm`` gateway resolved from the resource registry, so
the package is fully usable and testable without any provider. Deterministic
agents (echo/counter) work with no gateway at all.
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, Callable, Dict, List, Optional

from .contracts import new_trace_id, now_iso
from .prompt_rendering import SimplifiedPromptRenderer, render_template, safe_get_response
from .response_builder import ResponseBuilder
from .registry import ResourceRegistry


class BaseAgent:
    """Abstract agent.

    Subclasses implement ``_run_impl``; ``run`` wraps it with timing, trace id,
    optional timeout and response-builder normalization, so plain dict results
    are converted into full OrkaResponse dicts without data loss.
    """

    agent_type: str = "base"
    requires_gateway: bool = False

    def __init__(self, agent_id: str, prompt: str = "", config: Optional[Dict[str, Any]] = None,
                 registry: Optional[ResourceRegistry] = None, **kwargs: Any) -> None:
        self.agent_id = agent_id
        self.prompt = prompt or ""
        self.config: Dict[str, Any] = dict(config or {})
        self.attributes = dict(kwargs)
        self.registry = registry or ResourceRegistry()
        self.renderer = SimplifiedPromptRenderer(allow_unresolved=True)

    async def run(self, input_data: Any, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        start = now_iso()
        trace_id = (context or {}).get("trace_id") or new_trace_id()
        try:
            prompt = self.render_prompt(input_data, context)
            result = await self._run_impl(input_data, context or {}, prompt)
            if isinstance(result, dict) and ("response" in result or "result" in result) and (
                "component_id" in result or "error" in result
            ):
                return result
            value = result.get("response") if isinstance(result, dict) else result
            extra: Dict[str, Any] = {}
            if isinstance(result, dict):
                for k in ("memory_key", "confidence", "internal_reasoning", "metrics"):
                    if result.get(k) is not None:
                        extra[k] = result[k]
            return ResponseBuilder.create_success_response(
                value, agent_id=self.agent_id, component_type=self.agent_type,
                execution_start_time=start, trace_id=trace_id, **extra,
            )
        except Exception as error:
            return ResponseBuilder.create_error_response(
                error, agent_id=self.agent_id, component_type=self.agent_type,
                execution_start_time=start, trace_id=trace_id,
                execution_time_seconds=0.0,
            )

    async def _run_impl(self, input_data: Any, context: Dict[str, Any], prompt: str) -> Any:  # pragma: no cover
        raise NotImplementedError(f"{type(self).__name__} must implement _run_impl")

    def render_prompt(self, input_data: Any, context: Optional[Dict[str, Any]] = None) -> str:
        ctx = dict(context or {})
        if "input" not in ctx:
            ctx["input"] = input_data
        if "agent_id" not in ctx:
            ctx["agent_id"] = self.agent_id
        if "config" not in ctx:
            ctx["config"] = self.config
        return self.renderer.render(self.prompt, ctx)

    # -- helpers for subclasses -------------------------------------------------
    def _llm(self) -> Any:
        return self.registry.get("llm")

    async def _call_gateway(self, prompt: str, **kwargs: Any) -> Any:
        llm = self._llm()
        if llm is None:
            raise ValueError(
                f"agent {self.agent_id!r} ({self.agent_type}) requires an LLM gateway "
                "but no 'llm' resource is registered"
            )
        if callable(llm):
            result = llm(prompt, **kwargs)
            if inspect.isawaitable(result):
                result = await result
            return result
        method = getattr(llm, "complete", None)
        if method is None:
            raise TypeError("llm resource must be callable or expose .complete(prompt)")
        result = method(prompt, **kwargs)
        if inspect.isawaitable(result):
            result = await result
        return result


class EchoAgent(BaseAgent):
    """Deterministic echo agent: returns the rendered prompt as its response."""

    agent_type = "echo"

    async def _run_impl(self, input_data: Any, context: Dict[str, Any], prompt: str) -> Any:
        return {"response": prompt, "confidence": 1.0}


class CounterAgent(BaseAgent):
    """Deterministic counter agent: returns the literal input value."""

    agent_type = "counter"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        try:
            self._count = int(self.config.get("start") or 0)
        except (TypeError, ValueError):
            self._count = 0

    async def _run_impl(self, input_data: Any, context: Dict[str, Any], prompt: str) -> Any:
        self._count += 1
        return {"response": self._count, "confidence": 1.0}


class ConstantAgent(BaseAgent):
    """Deterministic constant agent: returns a configured constant value.

    Honors ``config.output`` and template variables in it via ``{{ input }}``.
    """

    agent_type = "constant"

    async def _run_impl(self, input_data: Any, context: Dict[str, Any], prompt: str) -> Any:
        value = self.config.get("output") or self.attributes.get("output") or ""
        if isinstance(value, str) and "{{" in value:
            value = render_template(value, {**context, "input": input_data})
        return {"response": value, "confidence": 1.0}


class LLMAgent(BaseAgent):
    """LLM agent: delegates to the registered gateway."""

    agent_type = "llm"
    requires_gateway = True

    async def _run_impl(self, input_data: Any, context: Dict[str, Any], prompt: str) -> Any:
        response = await self._call_gateway(
            prompt,
            model=self.config.get("model"),
            agent_id=self.agent_id,
            temperature=self.config.get("temperature"),
            max_tokens=self.config.get("max_tokens"),
        )
        return {"response": response}


class BinaryClassifierAgent(BaseAgent):
    """Deterministic boolean classifier: returns True/False for a routed value.

    Uses ``config.true_values`` / ``config.false_values``; falls back to a
    simple keyword match on the input response so routing works without a model.
    """

    agent_type = "binary"

    async def _run_impl(self, input_data: Any, context: Dict[str, Any], prompt: str) -> Any:
        target = self._routed_value(context)
        text = str(target if target is not None else input_data).strip().lower()
        true_vals = {str(v).strip().lower() for v in self.config.get("true_values", ["true", "yes", "pass", "valid"])}
        false_vals = {str(v).strip().lower() for v in self.config.get("false_values", ["false", "no", "fail", "invalid"])}
        if text in true_vals:
            return {"response": True, "confidence": 1.0}
        if text in false_vals:
            return {"response": False, "confidence": 1.0}

        llm = self._llm()
        if llm is not None:
            try:
                raw = await self._call_gateway(prompt, agent_id=self.agent_id)
                norm = str(raw).strip().lower()
                return {"response": "true" in norm or "yes" in norm, "confidence": 0.7}
            except Exception:
                pass
        # deterministic fallback keeps routing working without a model
        return {"response": "yes" in text or "true" in text or "pass" in text, "confidence": 0.6}

    def _routed_value(self, context: Dict[str, Any]) -> Any:
        src = self.config.get("source")
        if not src:
            return None
        return _dot_get(context, str(src))


class MemoryAgent(BaseAgent):
    """Memory read/write agent: operates on the registered memory logger."""

    agent_type = "memory"

    async def _run_impl(self, input_data: Any, context: Dict[str, Any], prompt: str) -> Any:
        memory = self.registry.get("memory")
        if memory is None:
            raise ValueError("agent type 'memory' requires a registered 'memory' resource")
        operation = str(self.config.get("operation") or "read").lower()
        namespace = str(self.config.get("namespace") or "mem20orcaz")
        key = str(self.config.get("key") or f"{self.agent_id}:{new_trace_id()[:8]}")

        if operation == "write":
            value = self.config.get("value")
            if value is None:
                value = safe_get_response(self.config.get("source_agent_id") or "input", input_data, context.get("previous_outputs") or {})
            entry = memory.log_memory(key, value, namespace=namespace, metadata={"agent_id": self.agent_id})
            return {"response": value, "memory_key": key, "metadata": entry}
        if operation == "get":
            return {"response": memory.get_memory_by_key(key), "memory_key": key}
        # default read: no query -> list most recent
        query = str(self.config.get("query") or input_data or "")
        hits = memory.search_memories(query, k=int(self.config.get("k", 5)))
        values = [h["value"] for h in hits]
        return {"response": values, "memory_key": None, "hits": hits}


class RouterAgent(BaseAgent):
    """Router agent: picks the next agent id from config or deterministic match."""

    agent_type = "router"

    async def _run_impl(self, input_data: Any, context: Dict[str, Any], prompt: str) -> Any:
        routes = self.config.get("routes") or []
        target = self.config.get("routed_value")
        value = str(self._routed_value(context) if target else input_data).strip().lower()
        for route in routes or []:
            if not isinstance(route, dict):
                continue
            if any(str(v).strip().lower() == value for v in route.get("match", [])):
                return {"response": route.get("target", ""), "confidence": 1.0}
        default = self.config.get("default_agent") or self.config.get("default")
        if isinstance(default, dict):
            default = default.get("target")
        return {"response": str(default or ""), "confidence": 0.5}

    def _routed_value(self, context: Dict[str, Any]) -> Any:
        src = self.config.get("source") or self.config.get("routed_value")
        if not src or src == "input":
            return context.get("input")
        return _dot_get(context, str(src))


class ValidationStructuringAgent(BaseAgent):
    """Validate + structure agent: passes input through (structure kept)."""

    agent_type = "validate_and_structure"

    async def _run_impl(self, input_data: Any, context: Dict[str, Any], prompt: str) -> Any:
        source = self.config.get("source_agent_id")
        value = input_data
        if source:
            value = _dot_get(context, f"previous_outputs.{source}.response", default=input_data)
        return {"response": value, "confidence": 1.0}


# agent types -> class map (registry for AgentFactory)
AGENT_CLASSES: Dict[str, Any] = {
    "echo": EchoAgent,
    "counter": CounterAgent,
    "constant": ConstantAgent,
    "llm": LLMAgent,
    "openai-answer": LLMAgent,
    "local_llm": LLMAgent,
    "binary": BinaryClassifierAgent,
    "openai-binary": BinaryClassifierAgent,
    "classification": BinaryClassifierAgent,
    "router": RouterAgent,
    "routernode": RouterAgent,
    "memory": MemoryAgent,
    "validate_and_structure": ValidationStructuringAgent,
    "validation_and_structuring_agent": ValidationStructuringAgent,
}


def _dot_get(root: Any, path: str, default: Any = None) -> Any:
    node = root
    for part in str(path).split("."):
        if isinstance(node, dict):
            node = node.get(part)
        else:
            return default
        if node is None:
            return default
    return default if node is None else node