"""Orchestrator for mem20orcaz.

Pure-stdlib port of OrKa's OrchestratorBase/Orchestrator. Trims OrKa's
transcendental dependencies (Redis, custom LLM providers, mem20 chain substrate inputs) to
keep the core fully deterministic and importable anywhere: the LLM gateway is a
pluggable resource, the memory logger is an in-memory store, and fork/join are
handled natively.
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, Callable, Dict, List, Optional, Union

from .agent_factory import AgentFactory, AgentFactoryError
from .concurrency import ConcurrencyManager
from .contracts import new_trace_id, now_iso
from .execution import (AgentRunner, ContextManager, MemoryRouter,
                        MetricsCollector, QueueProcessor, ResponseExtractor,
                        ResponseNormalizer, ResponseProcessor, TraceBuilder)
from .fork_group_manager import ForkGroupManager
from .graph_api import GraphAPI
from .loader import ConfigError, YAMLLoader
from .memory import InMemoryMemoryLogger, create_memory_logger
from .parallel_executor import ParallelExecutor
from .registry import ResourceRegistry
from .response_builder import ResponseBuilder


class OrchestratorBase:
    """Base orchestrator: config handling, traits and resource plumbing."""

    def __init__(self, id: str, config: Optional[Dict[str, Any]] = None) -> None:
        self.orchestrator_id = id
        self.config: Dict[str, Any] = dict(config or {})
        self.attributes: Dict[str, bool] = {
            "accepts_markdown": bool(self.config.get("accepts_markdown", False)),
            "accepts_csv": bool(self.config.get("workflow", {}).get("inputs", {}).get("files")),
            "gateway_set": False,
            "override_final_response": bool(
                self.config.get("orchestration", {}).get("override_final_response")),
        }

        # loaders and registries
        self.loader = YAMLLoader()
        self.resource_registry = ResourceRegistry()
        self.agent_factory: Optional[AgentFactory] = None
        self.dynamic_agents: Dict[str, Dict[str, Any]] = {}
        self.fork_registry: Dict[str, Dict[str, Any]] = {}
        self.join_registry: Dict[str, Dict[str, Any]] = {}
        self.queue_processor: Optional[QueueProcessor] = None
        self.current_context: Optional[Dict[str, Any]] = None
        self._previous_outputs: Dict[str, Any] = {}
        self._latest_values: Dict[str, Any] = {}

        # workflow resolution
        self.agents_config_map: Dict[str, Any] = {}
        self.initial_queue: List[str] = []
        self._resolve_workflow()

    # -- workflow resolution ----------------------------------------------------
    def _resolve_workflow(self) -> None:
        workflow = self.config.get("workflow", {})
        yaml_path = workflow.get("yaml_file_path") or workflow.get("workflow_yaml_path")
        if yaml_path:
            self.loader.load_yaml(yaml_path)
            self.agents_config_map = self.loader.agent_config_map() or {}
            self.initial_queue = self.loader.initial_queue() or []
        else:
            raw_agents = workflow.get("agents") or []
            self.agents_config_map, self.initial_queue = _normalize_agents_config(raw_agents)
        self.initial_queue = [str(a) for a in self.initial_queue if a]

    # -- resources ---------------------------------------------------------------
    def set_llm_gateway(self, gateway: Any) -> None:
        """Register a callable (or object with ``complete``) as the LLM resource."""
        if gateway is None:
            raise ValueError("LLM gateway cannot be None")
        self.resource_registry.register_instance("llm", gateway)
        self.attributes["gateway_set"] = True

    def register_resource(self, name: str, instance: Any) -> None:
        self.resource_registry.register_instance(name, instance)

    def register_agent_class(self, type_name: str, cls: Any) -> None:
        if self.agent_factory is None:
            self.agent_factory = AgentFactory(config_map=self.agents_config_map,
                                              registry=self.resource_registry)
        self.agent_factory.register_agent_class(type_name, cls)

    # -- dynamic topology --------------------------------------------------------
    def register_dynamic_agent(self, agent_name: str, config: Optional[Dict[str, Any]] = None) -> None:
        cfg = dict(config or {})
        cfg.setdefault("type", "llm")
        self.dynamic_agents[str(agent_name)] = cfg
        self.agents_config_map[str(agent_name)] = cfg
        if str(agent_name) not in self.initial_queue:
            self.initial_queue.append(str(agent_name))

    def register_fork(self, name: str, targets: List[str], mode: str = "sequential") -> None:
        self.fork_registry[str(name)] = {
            "type": "forknode", "targets": list(targets), "mode": mode,
        }
        self.agents_config_map[str(name)] = {
            "type": "forknode",
            "prompt": "Fork base prompt.",
            "params": {"targets": list(targets), "mode": mode},
            "queue": list(targets), "metadata": {"is_fork_node": True},
        }

    def register_join(self, name: str, group: str, fork_group_id: str,
                      max_retries: int = 30, output_key: str = "") -> None:
        self.join_registry[str(name)] = {
            "type": "joinnode", "group": group, "fork_group_id": fork_group_id,
        }
        self.agents_config_map[str(name)] = {
            "type": "joinnode",
            "prompt": "Join base prompt.",
            "params": {"group": group, "max_retries": int(max_retries),
                       "output_key": output_key or f"{name}:output"},
            "metadata": {"is_join_node": True},
        }

    # -- context accessors ---------------------------------------------------------
    def get_context(self) -> Dict[str, Any]:
        return dict(self.current_context or {"trace_id": new_trace_id()})

    def get_previous_outputs(self) -> Dict[str, Any]:
        return dict(self._previous_outputs)

    def get_latest_values(self) -> Dict[str, Any]:
        return dict(self._latest_values)

    def save_trace(self, trace: Any, save_memory: bool = True) -> None:
        memory = self.resource_registry.get("memory")
        if memory is not None and save_memory:
            memory.save_enhanced_trace(trace)

    def save_to_markdown(self, trace: Optional[Dict[str, Any]] = None) -> str:
        entries = (trace or {}).get("entries", [])
        lines = [f"# {self.orchestrator_id} trace",
                 f"- run_id: {(trace or {}).get('run_id', '')}",
                 f"- trace_id: {(trace or {}).get('trace_id', '')}", ""]
        if not entries:
            lines.append("_no entries_")
        for entry in entries:
            status = entry.get("status", "success")
            lines.append(f"## {entry.get('agent_id')} ({entry.get('component_type')}) -- {status}")
            lines.append(f"- input: {_preview(entry.get('input'))}")
            lines.append(f"- output: {_preview(entry.get('output'))}")
            lines.append(f"- time: {entry.get('execution_time_seconds')}s")
            if entry.get("memory_key"):
                lines.append(f"- memory: {entry['memory_key']}")
        return "\n".join(lines)


class Orchestrator(OrchestratorBase):
    """Concrete orchestrator with the full QueueProcessor run pipeline."""

    def __init__(self, id: str, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(id, config)
        cfg = self.config
        self.max_executions = int(cfg.get("orchestration", {}).get("max_executions", 100))
        self.save_trace_enabled = bool(cfg.get("orchestration", {}).get("save_trace", True))
        self.metrics = MetricsCollector()
        self.parallel_executor: Optional[ParallelExecutor] = None
        self.fork_manager = ForkGroupManager()
        self.graph_api = GraphAPI()
        self.override_value: Any = cfg.get("orchestration", {}).get("override_final_response")

    # -- runtime assembly -----------------------------------------------------------
    def _build_runtime(self, memory_engine: Optional[Any] = None) -> Dict[str, Any]:
        cfg = self.config
        # memory logger (pure stdlib; redis engine is not ported)
        memory_cfg = (cfg.get("memory") or {}).get("engine") or "memory"
        memory_logger = memory_engine
        if memory_logger is None:
            try:
                memory_logger = create_memory_logger(memory_cfg)
            except (ValueError, ImportError):
                memory_logger = InMemoryMemoryLogger()
        self.resource_registry.register_instance("memory", memory_logger)

        # agent / node wiring
        factory = AgentFactory(config_map=self.agents_config_map,
                               registry=self.resource_registry)
        self.agent_factory = factory

        concurrency = ConcurrencyManager(
            max_concurrency=int(cfg.get("concurrency", {}).get("max_concurrent_requests", 10)),
        )
        self.parallel_executor = ParallelExecutor(
            max_concurrency=int(cfg.get("concurrency", {}).get("max_concurrent_requests", 10)),
            fork_group_manager=self.fork_manager,
            memory_logger=memory_logger,
            concurrency_manager=concurrency,
        )
        self.resource_registry.register_instance("fork_group_manager", self.fork_manager)
        self.resource_registry.register_instance("parallel_executor", self.parallel_executor)
        self.resource_registry.register_instance("graph_api", self.graph_api)

        runner = AgentRunner(
            agent_classes=factory.classes, node_classes=factory.classes,
            config_map=self.agents_config_map,
            resource_registry=self.resource_registry,
            agent_factory=factory,
        )
        response_processor = ResponseProcessor(
            normalizer=ResponseNormalizer(),
            extractor=ResponseExtractor(ResponseNormalizer()),
            fork_group_manager=self.fork_manager,
            parallel_executor=self.parallel_executor,
        )
        qp = QueueProcessor(
            agent_runner=runner,
            context_manager=ContextManager(),
            response_processor=response_processor,
            memory_router=MemoryRouter(memory_logger),
            memory_logger=memory_logger,
            fork_group_manager=self.fork_manager,
            parallel_executor=self.parallel_executor,
            max_executions=self.max_executions,
            save_final_response=bool(cfg.get("orchestration", {}).get("save_final_response", True)),
        )
        self.queue_processor = qp
        return {"memory_logger": memory_logger, "runner": runner,
                "queue_processor": qp, "factory": factory}

    # -- run ------------------------------------------------------------------------
    def run(self, initial_user_input: Any,
            show_errors: bool = False, verbose: bool = False,
            override_final_response: Any = None, input_type: str = "string",
            result_to_img_generator: Any = None, trace_id: Optional[str] = None,
            session_id: Optional[str] = None, **kwargs: Any) -> Dict[str, Any]:
        return asyncio.run(self.arun(
            initial_user_input, show_errors=show_errors, verbose=verbose,
            override_final_response=override_final_response, input_type=input_type,
            trace_id=trace_id, session_id=session_id))

    async def arun(self, initial_user_input: Any,
                   show_errors: bool = False, verbose: bool = False,
                   override_final_response: Any = None, input_type: str = "string",
                   result_to_img_generator: Any = None, trace_id: Optional[str] = None,
                   session_id: Optional[str] = None, **kwargs: Any) -> Dict[str, Any]:
        tid = trace_id or new_trace_id()
        rid = new_trace_id()

        context_manager = ContextManager(trace_id=tid, run_id=rid,
                                         session_id=session_id or "")
        context_manager.set_context_extension("session_id", session_id or "")
        context_manager.set_context_extension("trace_id", tid)
        context_manager.set_context_extension("run_id", rid)
        context_manager.set_context_extension(
            "input", initial_user_input if input_type != "string" or isinstance(
                initial_user_input, (dict, list)) else str(initial_user_input))

        runtime = self._build_runtime()
        memory_logger = runtime["memory_logger"]
        qp = runtime["queue_processor"]

        ctx = context_manager.get_context()
        ctx.update({
            "_context_manager": context_manager,
            "_run_id": rid,
            "_runner": runtime["runner"],
            "_llm": self.resource_registry.get("llm"),
            "_memory_logger": memory_logger,
            "_orchestrator": self,
            "_parallel_mode": False,
        })

        self.metrics.start()
        result = await qp.run(self.initial_queue, context=ctx,
                              final_response_provider=self._final_provider(override_final_response),
                              metrics=self.metrics)
        self.metrics.stop()

        # persist outcomes
        self.current_context = context_manager.get_context()
        self._previous_outputs = context_manager.previous_outputs()
        self._latest_values = context_manager.latest_values()

        trace_builder = TraceBuilder()
        trace = trace_builder.build_trace(result["results"], run_id=rid, trace_id=tid,
                                          session_id=session_id or "")
        if self.save_trace_enabled:
            memory_logger.save_enhanced_trace(trace)

        final = result.get("final_response") or {}
        response_value = final.get("response") if isinstance(final, dict) else final
        response = ResponseBuilder.create_success_response(
            response_value, agent_id=None, component_type="orchestrator",
            trace_id=tid, run_id=rid,
            metadata={"orchestrator_id": self.orchestrator_id,
                      "execution_count": result.get("execution_count")},
        )
        response["results"] = result["results"]
        response["trace"] = trace
        response["metrics"] = self.metrics.summary()
        response["remaining_queue"] = result.get("queue")
        if verbose:
            context_manager.set_context_extension("verbose", True)
            response["context"] = context_manager.get_context()
        return response

    def _final_provider(self, override_final_response: Any) -> Optional[Callable]:
        value = override_final_response if override_final_response is not None else self.override_value

        def _handler(results: Dict[str, Any], trail: Any = None) -> Any:
            if isinstance(value, str):
                return {"response": value}
            if callable(value):
                out = value(results, trail=trail) if _accepts(value, ("trail",)) else value(results)
                return {"response": out}
            return None  # keep the natural final response

        return _handler if value is not None else None


def _normalize_agents_config(raw_agents: Any) -> tuple[Dict[str, Any], List[str]]:
    config_map: Dict[str, Any] = {}
    queue: List[str] = []
    if isinstance(raw_agents, dict):
        for aid, cfg in raw_agents.items():
            config_map[str(aid)] = dict(cfg) if isinstance(cfg, dict) else {"type": "echo"}
    elif isinstance(raw_agents, list):
        for item in raw_agents or []:
            if not isinstance(item, dict):
                continue
            aid = item.get("id") or item.get("agent_id")
            if not aid:
                continue
            cfg = dict(item)
            cfg.pop("id", None)
            cfg.pop("agent_id", None)
            config_map[str(aid)] = cfg
    for aid, cfg in config_map.items():
        deps = cfg.get("depends_on") if isinstance(cfg, dict) else None
        if deps:
            if isinstance(deps, str):
                deps = [deps]
            if not all(str(d) in config_map for d in deps):
                raise ConfigError(
                    f"agent {aid!r} depends on unknown agent(s): "
                    f"{[d for d in deps if str(d) not in config_map]}"
                )
        queue.append(aid)  # stable order; depends_on validated above
    return config_map, queue


def _preview(value: Any, limit: int = 80) -> str:
    text = str(value)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _accepts(fn: Callable, names: tuple) -> bool:
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return True
    return any(p.kind == p.VAR_KEYWORD for p in sig.parameters.values()) or any(
        p.name in names for p in sig.parameters.values())