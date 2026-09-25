"""Workflow nodes for mem20orcaz.

Pure-stdlib port of OrKa's node types: BaseNode plus the control-flow nodes
(fork, join, router, loop, failing, failover, memory reader/writer, rag) used by
the orchestration runtime. Nodes mirror OrKa's behavior: ``run()`` wraps timing
and errors into OrkaResponse dicts via ResponseBuilder, and control-flow nodes
carry the routing/parallelism metadata the execution engine acts on.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Dict, List, Optional

from .contracts import new_trace_id, now_iso
from .response_builder import ResponseBuilder


class BaseNode:
    """Abstract workflow node.

    Node instances are identified by ``node_id``; ``type`` derives from the
    class name lowercased (e.g. ``ForkNode -> "forknode"``) so control-flow
    detection matches OrKa's ResponseExtractor CONTROL_FLOW_TYPES.
    """

    def __init__(self, node_id: str, prompt: str = "", queue: Optional[List[str]] = None,
                 params: Optional[Dict[str, Any]] = None,
                 config: Optional[Dict[str, Any]] = None, **kwargs: Any) -> None:
        params = params or {}
        merged = dict(config or {})
        merged.update(params)
        for k, v in kwargs.items():
            if k not in merged:
                merged[k] = v
        self.node_id = node_id
        self.prompt = (prompt or "") or (merged.get("prompt") or "")
        self.queue = queue or []
        self.params: Dict[str, Any] = merged
        self.config: Dict[str, Any] = merged
        self.attributes: Dict[str, Any] = dict(kwargs)

    @property
    def type(self) -> str:
        return type(self).__name__.lower()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<{self.type} {self.node_id}>"

    async def run(self, input_data: Any, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        start = now_iso()
        trace_id = (context or {}).get("trace_id") or new_trace_id()
        try:
            result = await self._run_impl(input_data, context or {})
            return ResponseBuilder.from_plain_response(
                result, component_id=self.node_id, component_type=self.type,
                execution_start_time=start, trace_id=trace_id,
            ) if isinstance(result, dict) else ResponseBuilder.create_success_response(
                result, component_id=self.node_id, component_type=self.type,
                execution_start_time=start, trace_id=trace_id,
            )
        except Exception as error:
            return ResponseBuilder.create_error_response(
                error, component_id=self.node_id, component_type=self.type,
                execution_start_time=start, trace_id=trace_id,
            )

    async def _run_impl(self, input_data: Any, context: Dict[str, Any]) -> Any:  # pragma: no cover
        raise NotImplementedError(f"{type(self).__name__} must implement _run_impl")


class ForkNode(BaseNode):
    """Spawns a parallel branch group targeting ``targets`` (mode sequential/parallel)."""

    def __init__(self, *args: Any, targets: Optional[List[str]] = None, mode: str = "parallel",
                 memory_logger: Any = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.targets: List[str] = list(targets or self.config.get("targets") or [])
        self.mode: str = str(mode or self.config.get("mode") or "parallel")
        self.memory_logger = memory_logger

    async def _run_impl(self, input_data: Any, context: Dict[str, Any]) -> Any:
        return {
            "response": {
                "type": "fork",
                "targets": self.targets,
                "mode": self.mode,
                "fork_group_id": self.config.get("fork_group_id"),
                "node_id": self.node_id,
            },
            "targets": self.targets,
            "mode": self.mode,
            "fork_group_id": self.config.get("fork_group_id"),
        }


class JoinNode(BaseNode):
    """Waits for a fork group to complete; resolves its output key."""

    def __init__(self, *args: Any, group: Optional[str] = None, max_retries: int = 30,
                 fork_manager: Any = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.group_id: str = str(group or self.config.get("group") or "")
        self.max_retries: int = int(max_retries or self.config.get("max_retries") or 30)
        self.output_key: str = str(self.config.get("output_key") or f"{self.node_id}:output")
        self.fork_manager = fork_manager
        self._retry_key: str = str(self.config.get("_retry_key") or f"{self.node_id}:join_retry_count")

    async def _run_impl(self, input_data: Any, context: Dict[str, Any]) -> Any:
        group_id = self.group_id or (context.get("_fork_group_id") or "")
        if group_id and self.fork_manager is not None:
            pending = self.fork_manager.list_pending_agents(group_id)
            if pending:
                return {"response": None, "pending_agents": pending, "join_complete": False}
            members = self.fork_manager.status_map(group_id)
            done = [aid for aid, st in members.items() if st.get("status") == "done"]
            return {"response": {self.output_key: done}, "join_complete": True, "members": members, "group_id": group_id}
        return {"response": {self.output_key: []}, "join_complete": True, "group_id": group_id}


class RouterNode(BaseNode):
    """Routes to a single next agent based on a configured/classified value."""

    def __init__(self, *args: Any, routes: Optional[List[Dict[str, Any]]] = None,
                 default_agent: Optional[str] = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.routes: List[Dict[str, Any]] = list(routes or self.config.get("routes") or [])
        self.default_agent: Optional[str] = default_agent or self.config.get("default_agent") or None

    async def _run_impl(self, input_data: Any, context: Dict[str, Any]) -> Any:
        value = str(self._routed_value(context) if self.routes else input_data).strip().lower()
        target: Optional[str] = None
        for route in self.routes:
            match = route.get("match") or []
            if isinstance(match, str):
                match = [match]
            if any(str(v).strip().lower() == value for v in match):
                target = route.get("target")
                break
        if target is None:
            target = self.default_agent or self.config.get("default") or None
        if isinstance(target, dict):
            target = target.get("target")
        return {"response": str(target or ""), "next_agent": str(target or ""),
                "routed_value": value, "fallback": target is None}

    def _routed_value(self, context: Dict[str, Any]) -> Any:
        src = self.config.get("source") or self.config.get("routed_value")
        if not src or src == "input":
            return context.get("input")
        node = context
        for part in str(src).split("."):
            node = node.get(part) if isinstance(node, dict) else None
            if node is None:
                return None
        return node


class LoopNode(BaseNode):
    """Loop node: re-queues an agent until a condition (or max iterations)."""

    def __init__(self, *args: Any, loop_agent: Optional[str] = None, max_iterations: int = 3,
                 condition: Optional[Callable[[Any], bool]] = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.loop_agent: Optional[str] = loop_agent or self.config.get("loop_agent") or None
        self.max_iterations: int = int(max_iterations or self.config.get("max_iterations") or 3)
        self.condition = condition

    async def _run_impl(self, input_data: Any, context: Dict[str, Any]) -> Any:
        iteration = int(context.get("_loop_iteration") or 0)
        should_loop = self.condition(input_data) if self.condition is not None else (
            iteration < self.max_iterations
        )
        return {
            "response": {"loop": True, "iteration": iteration} if should_loop else {"loop": False, "iteration": iteration},
            "loop": should_loop,
            "iteration": iteration,
            "loop_agent": self.loop_agent,
        }


class LoopValidatorNode(BaseNode):
    """Validates loop output: True keeps looping, False exits."""

    def __init__(self, *args: Any, validator: Optional[Callable[[Any], bool]] = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.validator = validator

    async def _run_impl(self, input_data: Any, context: Dict[str, Any]) -> Any:
        valid = self.validator(input_data) if self.validator is not None else False
        return {"response": bool(valid), "valid": bool(valid), "keep_looping": not bool(valid)}


class FailingNode(BaseNode):
    """Deliberately throws inside a wrapped run (for failover testing/policy)."""

    agent_type = "failing"

    async def _run_impl(self, input_data: Any, context: Dict[str, Any]) -> Any:
        message = str(self.config.get("message") or f"{self.node_id} failed deliberately")
        raise RuntimeError(message)


class FailoverNode(BaseNode):
    """Runs a primary agent; on failure runs fallback agent(s) in order."""

    def __init__(self, *args: Any, primary: Optional[str] = None, fallbacks: Optional[List[str]] = None,
                 runner: Any = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.primary = primary or self.config.get("primary")
        self.fallbacks: List[str] = list(fallbacks or self.config.get("fallbacks") or [])
        self.runner = runner

    async def _run_impl(self, input_data: Any, context: Dict[str, Any]) -> Any:
        runner = self.runner or context.get("_runner")
        if runner is None:
            raise ValueError("FailoverNode requires a runner to execute primary/fallback agents")
        last_error: Optional[BaseException] = None
        attempts: List[str] = []
        chain = [a for a in [self.primary] + self.fallbacks if a]
        for agent_id in chain:
            attempts.append(agent_id)
            try:
                result = await self._run_agent(runner, agent_id, input_data, context)
                if isinstance(result, dict) and result.get("error"):
                    last_error = RuntimeError(str(result["error"]))
                    continue
                return {"response": result, "used_agent": agent_id, "attempts": attempts}
            except Exception as error:
                last_error = error
        raise RuntimeError(f"all failover agents failed: {last_error}")

    async def _run_agent(self, runner: Any, agent_id: str, input_data: Any, context: Dict[str, Any]) -> Any:
        inner = dict(context or {})
        inner["input"] = input_data
        inner["_runner"] = runner
        if hasattr(runner, "run") and callable(getattr(runner, "run")):
            return await runner.run(agent_id, inner)
        return await runner(agent_id, input_data, context)


class MemoryReaderNode(BaseNode):
    """Reads memories into the workflow context."""

    def __init__(self, *args: Any, memory: Any = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.memory = memory

    async def _run_impl(self, input_data: Any, context: Dict[str, Any]) -> Any:
        memory = context.get("_memory_logger") or self.memory or self.config.get("memory_logger")
        if memory is None:
            raise ValueError("MemoryReaderNode requires a memory logger")
        query = str(self.config.get("query") or input_data or "")
        hits = memory.search_memories(query, k=int(self.config.get("k", 5)))
        return {"response": [h["value"] for h in hits], "hits": hits}


class MemoryWriterNode(BaseNode):
    """Writes a value into the memory logger."""

    def __init__(self, *args: Any, memory: Any = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.memory = memory

    async def _run_impl(self, input_data: Any, context: Dict[str, Any]) -> Any:
        memory = context.get("_memory_logger") or self.memory or self.config.get("memory_logger")
        if memory is None:
            raise ValueError("MemoryWriterNode requires a memory logger")
        key = str(self.config.get("key") or f"{self.node_id}:{new_trace_id()[:8]}")
        value = self.config.get("value")
        if value is None:
            source = self.config.get("source_agent_id")
            value = input_data
            if source:
                entry = (context.get("previous_outputs") or {}).get(source)
                value = entry.get("response") if isinstance(entry, dict) else entry
        namespace = str(self.config.get("namespace") or "mem20orcaz")
        entry = memory.log_memory(key, value, namespace=namespace)
        return {"response": value, "memory_key": key, "entry": entry}


class RAGNode(BaseNode):
    """Retrieval-augmented generation: reads memories then synthesizes via llm."""

    def __init__(self, *args: Any, memory: Any = None, llm: Any = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.memory = memory
        self.llm = llm

    async def _run_impl(self, input_data: Any, context: Dict[str, Any]) -> Any:
        memory = context.get("_memory_logger") or self.memory
        if memory is None:
            raise ValueError("RAGNode requires a memory logger")
        query = str(input_data or "")
        hits = memory.search_memories(query, k=int(self.config.get("k", 5)))
        context_docs = "\n".join(str(h["value"]) for h in hits)
        rendered = self.prompt
        if "{{" in rendered:
            from .prompt_rendering import render_template

            rendered = render_template(rendered, {**context, "input": input_data, "retrieved": context_docs})
        response = context_docs
        llm = context.get("_llm") or self.llm
        if llm is not None and rendered:
            try:
                call = llm(rendered) if callable(llm) else llm.complete(rendered)
                if hasattr(call, "__await__"):
                    call = await call
                response = call if not isinstance(call, dict) else call.get("response", call)
            except Exception:
                response = context_docs
        return {"response": response, "hits": hits, "context": context_docs}


class GraphScoutAgent(BaseNode):
    """Scouts the workflow graph and reports reachable nodes/paths."""

    def __init__(self, *args: Any, graph_api: Any = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.graph_api = graph_api

    async def _run_impl(self, input_data: Any, context: Dict[str, Any]) -> Any:
        api = self.graph_api or self.config.get("graph_api")
        if api is None:
            return {"response": [], "paths": [], "note": "no graph_api provided"}
        state = await api.get_graph_state(context.get("_orchestrator"), context.get("_run_id") or "")
        # paths: topological frontier based on depends_on edges
        deps: Dict[str, str] = {}
        for edge in state.edges:
            deps[edge.dst] = edge.src
        paths = []
        for nid, node in state.nodes.items():
            path = [str(state.current_node)]
            cursor = nid
            seen = 0
            while cursor in deps and seen < 10:
                path.append(cursor)
                cursor = deps[cursor]
                seen += 1
            if state.current_node == (candidate := str(nid)):
                paths.append([f"{nid}(current)"])
            else:
                path_set = [p for p in path if p]
                paths.append([p for p in path_set[::-1]])
        return {"response": list(state.nodes.keys()), "paths": paths, "node_count": len(state.nodes)}


NODE_CLASSES: Dict[str, Any] = {
    "forknode": ForkNode,
    "join": JoinNode,
    "joinnode": JoinNode,
    "router": RouterNode,
    "routernode": RouterNode,
    "loop": LoopNode,
    "loopnode": LoopNode,
    "loop_validator": LoopValidatorNode,
    "loopvalidatornode": LoopValidatorNode,
    "failing": FailingNode,
    "failingnode": FailingNode,
    "failover": FailoverNode,
    "failovernode": FailoverNode,
    "memory_reader": MemoryReaderNode,
    "memory_reader_node": MemoryReaderNode,
    "memory_writer": MemoryWriterNode,
    "memory_writer_node": MemoryWriterNode,
    "rag": RAGNode,
    "ragnode": RAGNode,
    "graph_scout": GraphScoutAgent,
    "graph-scout": GraphScoutAgent,
    "graphscout": GraphScoutAgent,
}


def _dot_get(root: Any, path: str) -> Any:
    node = root
    for part in str(path).split("."):
        if isinstance(node, dict):
            node = node.get(part)
        else:
            return None
        if node is None:
            return None
    return node