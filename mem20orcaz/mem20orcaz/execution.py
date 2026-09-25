"""Execution core for mem20orcaz.

Pure-stdlib port of OrKa's orchestration execution layer: the context manager,
response normalization/extraction, memory routing, agent runner, response
processor and the QueueProcessor main run loop, plus a lightweight metrics
collector. Everything here is deterministic and works with no LLM gateway; the
gateway is resolved lazily per-agent from the resource registry.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Any, Dict, List, Optional

from .concurrency import ConcurrencyManager
from .contracts import new_trace_id, now_iso
from .graph_api import CONTROL_FLOW_TYPES
from .response_builder import ResponseBuilder


# --------------------------------------------------------------------------- #
# Context
# --------------------------------------------------------------------------- #
class ContextManager:
    """Tracks the run-time context across agent executions."""

    def __init__(self, trace_id: str = "", run_id: str = "", session_id: str = "") -> None:
        self.trace_id = trace_id or new_trace_id()
        self.run_id = run_id or new_trace_id()
        self.session_id = session_id or ""
        self.extensions: Dict[str, Any] = {}
        self._previous_outputs: Dict[str, Any] = {}
        self._latest_values: Dict[str, Any] = {}
        self._fork_registry: Dict[str, List[str]] = {}

    # -- ids ----------------------------------------------------------------
    def set_trace_id(self, trace_id: str) -> None:
        self.trace_id = trace_id

    def set_run_id(self, run_id: str) -> None:
        self.run_id = run_id

    def set_session_id(self, session_id: str) -> None:
        self.session_id = session_id

    def set_context_extension(self, key: str, value: Any) -> None:
        self.extensions[key] = value

    # -- outputs ------------------------------------------------------------
    def update_previous_outputs(self, agent_id: str, response: Any) -> None:
        self._previous_outputs[str(agent_id)] = response

    def set_latest_values(self, key: str, value: Any) -> None:
        self._latest_values[str(key)] = value

    def latest_values(self) -> Dict[str, Any]:
        return dict(self._latest_values)

    def previous_outputs(self) -> Dict[str, Any]:
        return dict(self._previous_outputs)

    # -- fork registry -------------------------------------------------------
    def register_fork(self, fork_group_id: str, targets: List[str]) -> None:
        self._fork_registry[str(fork_group_id)] = list(targets)

    def get_fork(self, fork_group_id: str) -> List[str]:
        return list(self._fork_registry.get(str(fork_group_id), []))

    # -- context assembly -----------------------------------------------------
    def get_context(self) -> Dict[str, Any]:
        ctx: Dict[str, Any] = {
            "trace_id": self.trace_id,
            "run_id": self.run_id,
            "session_id": self.session_id,
            "previous_outputs": self.previous_outputs(),
            "latest_values": self.latest_values(),
            "_fork_registry": dict(self._fork_registry),
        }
        ctx.update(self.extensions)
        return ctx


# --------------------------------------------------------------------------- #
# Normalizer / extactor
# --------------------------------------------------------------------------- #
class ResponseNormalizer:
    """Coerce raw agent/node outputs into a canonical response dict."""

    STATUS = {"status", "success", "error"}

    def normalize(self, response: Any) -> Dict[str, Any]:
        if isinstance(response, dict):
            if "response" in response or "error" in response or "component_id" in response:
                return self._clean(response)
            return {"response": response, "status": "success"}
        return {"response": response, "status": "success"}

    def _clean(self, response: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(response)
        if "status" not in out:
            out["status"] = "error" if out.get("error") is not None else "success"
        return out


class ResponseExtractor:
    """Classifies a normalized response's control-flow to drive the queue."""

    def __init__(self, normalizer: Optional[ResponseNormalizer] = None) -> None:
        self.normalizer = normalizer or ResponseNormalizer()

    def extract(self, normalized: Dict[str, Any], agent_type: str = "") -> Dict[str, Any]:
        flow = agent_type.lower() if isinstance(agent_type, str) else ""
        value = normalized.get("response")

        if flow in CONTROL_FLOW_TYPES:
            if isinstance(value, dict):
                kind = str(value.get("type") or value.get("control_flow") or "").lower()
                if kind == "fork" or flow.startswith("fork"):
                    return {
                        "control_flow": "fork",
                        "targets": list(value.get("targets") or normalized.get("targets") or []),
                        "mode": str(value.get("mode") or normalized.get("mode") or "parallel"),
                        "fork_group_id": value.get("fork_group_id") or normalized.get("fork_group_id"),
                        "leftovers": value,
                    }
                if kind == "join" or flow.startswith("join"):
                    return {
                        "control_flow": "join",
                        "join_complete": bool(value.get("join_complete", True)),
                        "group_id": value.get("group_id") or normalized.get("group_id") or "",
                        "output_key": value.get("output_key"),
                        "leftovers": value,
                    }
                if kind == "router" or flow.startswith("router"):
                    return {
                        "control_flow": "router",
                        "next_agent": value.get("next_agent") or value.get("routed") or "",
                        "leftovers": value,
                    }
                if kind == "loop" or flow.startswith("loop"):
                    return {
                        "control_flow": "loop",
                        "loop_agent": value.get("loop_agent"),
                        "iteration": value.get("iteration"),
                        "should_loop": bool(value.get("loop", False)),
                        "leftovers": value,
                    }
            # structured control-flow nodes without a classified value
            if flow.startswith("fork"):
                return {"control_flow": "fork", "targets": [], "mode": "parallel",
                        "fork_group_id": normalized.get("fork_group_id"), "leftovers": value or {}}
            if flow.startswith("join"):
                return {"control_flow": "join", "join_complete": True, "group_id": "",
                        "output_key": None, "leftovers": value or {}}
            if flow.startswith("router"):
                return {"control_flow": "router", "next_agent": "", "leftovers": value or {}}
            if flow.startswith("loop"):
                return {"control_flow": "loop", "loop_agent": None, "iteration": 0,
                        "should_loop": False, "leftovers": value or {}}

        # generic: honor explicit routing keys on any response
        if isinstance(value, dict):
            for key in ("next_agent", "routed", "next"):
                if value.get(key):
                    return {"control_flow": "next", "next_agent": str(value[key]), "leftovers": value}
        if isinstance(normalized.get("next_agent"), str) and normalized["next_agent"]:
            return {"control_flow": "next", "next_agent": normalized["next_agent"], "leftovers": normalized}
        return {"control_flow": "next", "next_agent": None, "leftovers": normalized}


# --------------------------------------------------------------------------- #
# Trace building
# --------------------------------------------------------------------------- #
class TraceBuilder:
    """Builds a structured trace from per-agent results."""

    def __init__(self, skip_component_data: bool = False) -> None:
        self.skip_component_data = skip_component_data

    def build_entry(self, agent_id: str, response: Any) -> Dict[str, Any]:
        resp = response if isinstance(response, dict) else {"response": response}
        entry = {
            "agent_id": str(agent_id),
            "component_id": resp.get("component_id") or str(agent_id),
            "component_type": resp.get("component_type") or "agent",
            "input": resp.get("input"),
            "output": resp.get("response"),
            "execution_start_time": resp.get("execution_start_time"),
            "execution_end_time": resp.get("execution_end_time"),
            "execution_time_seconds": resp.get("execution_time_seconds"),
            "status": resp.get("status", "success"),
            "trace_id": resp.get("trace_id"),
            "memory_key": resp.get("memory_key"),
            "metadata": resp.get("metadata"),
            "diag": resp.get("diag"),
        }
        if not self.skip_component_data:
            entry["usage"] = resp.get("usage")
        return entry

    def build_trace(self, results: Dict[str, Any], run_id: str = "", trace_id: str = "",
                    session_id: str = "") -> Dict[str, Any]:
        entries = [self.build_entry(aid, resp) for aid, resp in (results or {}).items()]
        return {
            "run_id": run_id,
            "trace_id": trace_id,
            "session_id": session_id,
            "n_entries": len(entries),
            "entries": entries,
        }


# --------------------------------------------------------------------------- #
# Memory routing
# --------------------------------------------------------------------------- #
class MemoryRouter:
    """Decides what to persist to the memory logger after each agent run."""

    def __init__(self, memory_logger: Any = None) -> None:
        self.memory_logger = memory_logger

    async def route_memories(self, agent_id: str, response: Any, context: Dict[str, Any]) -> None:
        if self.memory_logger is None:
            return
        resp = response if isinstance(response, dict) else {"response": response}
        namespace = str(context.get("memory_namespace") or "mem20orcaz")
        memory_key = resp.get("memory_key")
        if memory_key:
            self.memory_logger.log_memory(memory_key, resp.get("response"),
                                          namespace=namespace,
                                          metadata={"agent_id": str(agent_id)})
        # always store a run record (blob-deduped by the logger)
        self.memory_logger.log_memory(
            f"agent:{agent_id}",
            {"type": resp.get("component_type") or "agent", "input": resp.get("input"),
             "output": resp.get("response"), "status": resp.get("status")},
            namespace=namespace,
            metadata={"agent_id": str(agent_id), "status": resp.get("status", "success")},
        )


# --------------------------------------------------------------------------- #
# Agent runner
# --------------------------------------------------------------------------- #
class AgentRunner:
    """Resolves an agent/node by id and runs it with the shared context."""

    def __init__(self, agent_classes: Optional[Dict[str, Any]] = None,
                 node_classes: Optional[Dict[str, Any]] = None,
                 config_map: Optional[Dict[str, Any]] = None,
                 resource_registry: Any = None, agent_factory: Any = None,
                 **kwargs: Any) -> None:
        from .agents import AGENT_CLASSES as _AGENTS
        from .nodes import NODE_CLASSES as _NODES

        self.agent_classes = agent_classes or _AGENTS
        self.node_classes = node_classes or _NODES
        self.config_map: Dict[str, Any] = dict(config_map or {})
        self.resource_registry = resource_registry
        self.agent_factory = agent_factory
        self._instances: Dict[str, Any] = {}
        self.extra_kwargs = kwargs

    def get_agent_config(self, agent_id: str) -> Dict[str, Any]:
        cfg = self.config_map.get(str(agent_id), {})
        return dict(cfg) if isinstance(cfg, dict) else {"response": cfg}

    def _resolve(self, agent_id: str) -> Any:
        if agent_id in self._instances:
            return self._instances[agent_id]
        cfg = self.get_agent_config(agent_id)
        ctype = str(cfg.get("type") or "llm")
        factory = self.agent_factory
        if factory is not None:
            instance = factory.create(agent_id=agent_id, config=cfg,
                                      registry=self.resource_registry)
        else:
            from .registry import ResourceRegistry

            cls = self.node_classes.get(ctype) or self.agent_classes.get(ctype)
            if cls is None:
                cls = self.node_classes.get("llm") or self.agent_classes.get("llm")
            registry = self.resource_registry if self.resource_registry is not None else ResourceRegistry()
            instance = self._instantiate(cls, agent_id, cfg, registry)
        self._instances[agent_id] = instance
        return instance

    def _instantiate(self, cls: Any, agent_id: str, cfg: Dict[str, Any], registry: Any) -> Any:
        prompt = cfg.get("prompt") or cfg.get("description") or ""
        params = dict(self.extra_kwargs)
        params.update({k: v for k, v in (cfg.get("params") or {}).items()})
        import inspect as _inspect

        plist = list(_inspect.signature(cls.__init__).parameters.values())
        names = {p.name for p in plist}
        has_var_kw = any(p.kind == p.VAR_KEYWORD for p in plist)
        kwargs: Dict[str, Any] = {}
        if "config" in names or has_var_kw:
            kwargs["config"] = cfg
        if "registry" in names or has_var_kw:
            kwargs["registry"] = registry
        if "prompt" in names or has_var_kw:
            kwargs["prompt"] = prompt
        kwargs.update(params)
        try:
            return cls(agent_id, **kwargs)
        except (TypeError, ValueError):
            merged = dict(cfg)
            merged.setdefault("prompt", prompt)
            merged.update(params)
            try:
                return cls(agent_id=agent_id, config=merged, registry=registry, **params)
            except TypeError:
                return cls(agent_id, prompt, **merged)

    async def run(self, agent_id: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        ctx = dict(context or {})
        try:
            instance = self._resolve(agent_id)
            ctx.setdefault("trace_id", ctx.get("trace_id") or new_trace_id())
            ctx.setdefault("agent_id", agent_id)
            response = await instance.run(ctx.get("input"), ctx)
            if isinstance(response, dict):
                response.setdefault("agent_id", agent_id)
                response.setdefault("trace_id", ctx.get("trace_id"))
            return response
        except Exception as error:
            return ResponseBuilder.create_error_response(
                error, agent_id=str(agent_id), trace_id=ctx.get("trace_id"),
            )


# --------------------------------------------------------------------------- #
# Response processing (queue extension / fork-join orchestration)
# --------------------------------------------------------------------------- #
class ResponseProcessor:
    """Normalize + extract a response and extend the run queue accordingly."""

    def __init__(self, normalizer: Optional[ResponseNormalizer] = None,
                 extractor: Optional[ResponseExtractor] = None,
                 fork_group_manager: Any = None,
                 parallel_executor: Any = None) -> None:
        self.normalizer = normalizer or ResponseNormalizer()
        self.extractor = extractor or ResponseExtractor(self.normalizer)
        self.fork_group_manager = fork_group_manager
        self.parallel_executor = parallel_executor

    async def process(self, response: Any, agent_runner: AgentRunner, context: Dict[str, Any],
                      queue: Any, results: Dict[str, Any]) -> Dict[str, Any]:
        agent_id = str((response.get("agent_id") if isinstance(response, dict) else None) or "")
        normalized = self.normalizer.normalize(response)
        agent_type = str(normalized.get("component_type") or
                         self._config_type(agent_runner, agent_id) or "agent")
        extracted = self.extractor.extract(normalized, agent_type)

        flow = extracted.get("control_flow")
        if flow == "fork":
            await self._handle_fork(extracted, agent_runner, context, queue, results)
        elif flow == "join":
            await self._handle_join(extracted, agent_runner, context, queue, results)
        elif flow == "router":
            next_agent = extracted.get("next_agent")
            if next_agent:
                self._enqueue(queue, next_agent)
        elif flow == "loop":
            if extracted.get("should_loop"):
                self._enqueue(queue, extracted["loop_agent"])
        else:
            next_agent = extracted.get("next_agent")
            if next_agent:
                self._enqueue(queue, next_agent)

        return {"normalized": normalized, "extracted": extracted, "queue": queue, "results": results}

    def _config_type(self, runner: AgentRunner, agent_id: str) -> str:
        if not agent_id:
            return ""
        return str(runner.get_agent_config(agent_id).get("type") or "")

    async def _handle_fork(self, extracted: Dict[str, Any], runner: AgentRunner,
                           context: Dict[str, Any], queue: Any, results: Dict[str, Any]) -> None:
        targets = [str(t) for t in (extracted.get("targets") or []) if t]
        mode = extracted.get("mode") or "parallel"
        group_id = extracted.get("fork_group_id") or (context.get("_fork_registry") and None) or None

        fgm = self.fork_group_manager
        if fgm is not None and group_id is None:
            group_id = fgm.generate_group_id("forkgroup")
            fgm.create_group(group_id)
            fgm.add_members(group_id, targets)
        elif fgm is not None and group_id and not fgm.group_exists(group_id):
            fgm.create_group(group_id)
            fgm.add_members(group_id, targets)

        context_manager = context.get("_context_manager")
        if context_manager is not None and group_id:
            context_manager.register_fork(group_id, targets)
            context["_fork_group_id"] = group_id

        if targets:
            if mode == "parallel" and self.parallel_executor is not None:
                await self.parallel_executor.execute_parallel(
                    targets, context, runner, fork_group_id=group_id)
            else:
                for target in targets:
                    self._enqueue(queue, target)

    async def _handle_join(self, extracted: Dict[str, Any], runner: AgentRunner,
                           context: Dict[str, Any], queue: Any, results: Dict[str, Any]) -> None:
        group_id = extracted.get("group_id") or context.get("_fork_group_id") or ""
        fgm = self.fork_group_manager

        if fgm is not None and group_id:
            if self._pending_group(fgm, group_id, context):
                return  # wait: remaining branches still executing
            if not fgm.is_group_done(group_id):
                return
            fgm.delete_group(group_id)

        # group complete (or no manager): route onward via the join config
        agent_id = context.get("agent_id") or ""
        cfg = runner.get_agent_config(agent_id) if agent_id else {}
        next_agent = extracted.get("output_key")
        next_agent = next_agent or cfg.get("next_agent") or cfg.get("next") or (
            (cfg.get("params") or {}).get("next") or None)
        if next_agent and not isinstance(next_agent, str):
            next_agent = None
        if next_agent:
            self._enqueue(queue, next_agent)

    def _pending_group(self, fgm: Any, group_id: str, context: Dict[str, Any]) -> bool:
        pending = fgm.list_pending_agents(group_id)
        # sequential mode: branches may not all be queued yet; treat visible
        # pending as in-flight only when a parallel executor was used
        parallel = context.get("_parallel_mode")
        return bool(pending) if parallel else bool(pending)

    def _enqueue(self, queue: Any, agent_id: Any) -> None:
        if agent_id is None or str(agent_id) == "":
            return
        queue.append(str(agent_id))


# --------------------------------------------------------------------------- #
# Queue processor (main loop)
# --------------------------------------------------------------------------- #
class QueueProcessor:
    """The orchestrator's core execution loop over the agent queue."""

    def __init__(self, agent_runner: AgentRunner, context_manager: ContextManager,
                 response_processor: ResponseProcessor,
                 memory_router: Optional[MemoryRouter] = None,
                 memory_logger: Any = None,
                 fork_group_manager: Any = None,
                 parallel_executor: Any = None,
                 max_executions: int = 100,
                 save_final_response: bool = True,
                 **kwargs: Any) -> None:
        self.agent_runner = agent_runner
        self.context_manager = context_manager
        self.response_processor = response_processor
        self.memory_router = memory_router or MemoryRouter(memory_logger)
        self.memory_logger = memory_logger
        self.fork_group_manager = fork_group_manager or response_processor.fork_group_manager
        self.parallel_executor = parallel_executor
        self.max_executions = int(max_executions)
        self.save_final_response = save_final_response
        self.extra = kwargs
        self.lock = asyncio.Lock()

    async def run(self, initial_queue: List[str], context: Optional[Dict[str, Any]] = None,
                  final_response_provider: Any = None, metrics: Any = None) -> Dict[str, Any]:
        queue: Any = deque(str(a) for a in (initial_queue or []))
        ctx = dict(context or self.context_manager.get_context())
        results: Dict[str, Any] = {}
        last_response: Optional[Dict[str, Any]] = None
        execution_count = 0

        while queue and execution_count < self.max_executions:
            async with self.lock:
                if not queue:
                    break
                agent_id = queue.popleft()
                ctx.setdefault("agent_id", agent_id)
                ctx.setdefault("_context_manager", self.context_manager)
                if self.parallel_executor is not None:
                    ctx["_parallel_mode"] = True
                # refresh previous outputs so later agents see earlier results
                ctx["previous_outputs"] = self.context_manager.previous_outputs()
                ctx["latest_values"] = self.context_manager.latest_values()
                response = await self.agent_runner.run(agent_id, ctx)
                ctx["agent_id"] = agent_id
                execution_count += 1

                if metrics is not None:
                    latency = 0.0
                    if isinstance(response, dict):
                        try:
                            latency = float(response.get("execution_time_seconds") or 0.0)
                        except (TypeError, ValueError):
                            latency = 0.0
                    metrics.record(agent_id, agent_type=str(
                        (response or {}).get("component_type") or "agent"),
                        latency=latency,
                        status="error" if (isinstance(response, dict) and response.get("error")) else "success")

                results[agent_id] = response
                last_response = response
                self.context_manager.update_previous_outputs(agent_id, response)

                if self.fork_group_manager is not None:
                    for gid, targets in getattr(self.context_manager, "_fork_registry", {}).items():
                        if agent_id in targets:
                            self.fork_group_manager.mark_agent_done(gid, agent_id)

                await self.memory_router.route_memories(agent_id, response, ctx)

                await self.response_processor.process(
                    response, self.agent_runner, ctx, queue, results)

                self.context_manager.set_context_extension("last_executed", agent_id)

        final_response = last_response
        if final_response_provider is not None:
            final_response = await final_response_provider(results, trail=queue)

        if self.save_final_response and self.memory_logger is not None:
            self.memory_logger.set_final_response(final_response)

        return {
            "final_response": final_response,
            "results": results,
            "queue": list(queue),
            "max_executions": self.max_executions,
            "execution_count": execution_count,
        }


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #
class MetricsCollector:
    """Lightweight execution metrics (counts, latencies, per-type breakdown)."""

    def __init__(self) -> None:
        self.started_at: float = 0.0
        self.finished_at: float = 0.0
        self.total: int = 0
        self.by_type: Dict[str, int] = {}
        self.latencies: Dict[str, float] = {}
        self.statuses: Dict[str, int] = {}

    def start(self) -> None:
        self.started_at = time.time()

    def stop(self) -> None:
        self.finished_at = time.time()

    def record(self, agent_id: str, agent_type: str = "agent", latency: float = 0.0,
               status: str = "success") -> None:
        self.total += 1
        self.by_type[agent_type] = self.by_type.get(agent_type, 0) + 1
        self.latencies[str(agent_id)] = max(self.latencies.get(str(agent_id), 0.0), latency)
        self.statuses[status] = self.statuses.get(status, 0) + 1

    def summary(self) -> Dict[str, Any]:
        return {
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "total_executions": self.total,
            "by_type": dict(self.by_type),
            "statuses": dict(self.statuses),
        }