"""Workflow graph API for mem20orcaz.

Pure-stdlib port of OrKa's GraphAPI: node/edge descriptors and complete graph
state built from orchestrator agent configs. Used by graph-scout agents and by
the orchestration runtime for path discovery and validation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


@dataclass
class NodeDescriptor:
    """Describes a node in the workflow graph."""

    id: str
    type: str
    prompt_summary: str
    capabilities: List[str] = field(default_factory=list)
    contract: Dict[str, Any] = field(default_factory=dict)
    cost_model: Dict[str, Any] = field(default_factory=dict)
    safety_tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EdgeDescriptor:
    """Describes an edge between nodes."""

    src: str
    dst: str
    condition: Optional[Dict[str, Any]] = None
    weight: float = 1.0
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        if self.metadata is None:
            self.metadata = {}


@dataclass
class GraphState:
    """Complete graph state for path discovery."""

    nodes: Dict[str, NodeDescriptor]
    edges: List[EdgeDescriptor]
    current_node: str
    visited_nodes: Set[str] = field(default_factory=set)
    runtime_state: Dict[str, Any] = field(default_factory=dict)
    budgets: Dict[str, Any] = field(default_factory=dict)
    constraints: Dict[str, Any] = field(default_factory=dict)


# Agent types that influence routing (mirrors OrKa ResponseExtractor).
CONTROL_FLOW_TYPES: Set[str] = {
    "forknode", "joinnode", "routernode", "loopnode", "graph-scout",
    "fork", "join", "router", "loop", "graphscout",
}

DEFAULT_BUDGETS = {
    "cost_tokens": None,
    "latency_ms": None,
    "max_depth": 10,
    "max_branches": 32,
}


class GraphAPI:
    """Runtime interface to the workflow graph structure."""

    def __init__(self) -> None:
        self.cache: Dict[str, Any] = {}

    async def get_graph_state(self, orchestrator: Any, run_id: str) -> GraphState:
        nodes = await self._extract_nodes(orchestrator)
        edges = await self._build_edges(orchestrator)
        current_node = await self._get_current_node(orchestrator, run_id)
        visited = await self._get_visited_nodes(orchestrator, run_id)
        runtime_state = await self._get_runtime_state(orchestrator, run_id)
        budgets = self._get_budgets(orchestrator)
        constraints = self._get_constraints(orchestrator)
        return GraphState(
            nodes=nodes,
            edges=edges,
            current_node=current_node,
            visited_nodes=visited,
            runtime_state=runtime_state,
            budgets=budgets,
            constraints=constraints,
        )

    async def _extract_nodes(self, orchestrator: Any) -> Dict[str, NodeDescriptor]:
        nodes: Dict[str, NodeDescriptor] = {}
        cfg_map = getattr(orchestrator, "agents_config_map", None) or {}
        for aid, cfg in (cfg_map or {}).items():
            meta = cfg.get("metadata") or {}
            desc = NodeDescriptor(
                id=aid,
                type=str(cfg.get("type") or "unknown"),
                prompt_summary=_shorten(cfg.get("prompt") or cfg.get("description") or ""),
                capabilities=_as_list(meta.get("capabilities") or cfg.get("capabilities")),
                contract=dict(cfg.get("contract") or {}),
                cost_model=dict(cfg.get("cost_model") or {}),
                safety_tags=_as_list(meta.get("safety_tags") or cfg.get("safety_tags")),
                metadata=dict(meta),
            )
            nodes[aid] = desc
        return nodes

    async def _build_edges(self, orchestrator: Any) -> List[EdgeDescriptor]:
        cfg_map = getattr(orchestrator, "agents_config_map", None) or {}
        edges: List[EdgeDescriptor] = []
        for aid, cfg in (cfg_map or {}).items():
            deps = cfg.get("depends_on") or []
            if isinstance(deps, str):
                deps = [deps]
            for dep in deps:
                if dep in (cfg_map or {}):
                    edges.append(EdgeDescriptor(src=str(dep), dst=str(aid), weight=1.0))
        return edges

    async def _get_current_node(self, orchestrator: Any, run_id: str) -> str:
        queue = getattr(orchestrator, "queue", None)
        if isinstance(queue, list) and queue:
            return str(queue[0])
        exec_state = getattr(orchestrator, "execution_state", None) or {}
        return str(exec_state.get("current_agent") or "")

    async def _get_visited_nodes(self, orchestrator: Any, run_id: str) -> Set[str]:
        execution_state = getattr(orchestrator, "execution_state", None) or {}
        visited = execution_state.get("visited_agents") or []
        return set(str(a) for a in visited)

    async def _get_runtime_state(self, orchestrator: Any, run_id: str) -> Dict[str, Any]:
        base = getattr(orchestrator, "execution_state", None)
        return dict(base or {})

    def _get_budgets(self, orchestrator: Any) -> Dict[str, Any]:
        cfg = getattr(orchestrator, "orchestrator_cfg", None) or {}
        budget = cfg.get("budgets") or DEFAULT_BUDGETS.get("cost_tokens")
        if isinstance(budget, dict):
            return dict(budget)
        return dict(DEFAULT_BUDGETS)

    def _get_constraints(self, orchestrator: Any) -> Dict[str, Any]:
        cfg = getattr(orchestrator, "orchestrator_cfg", None) or {}
        return dict(cfg.get("constraints") or {})

    def clear_cache(self) -> None:
        self.cache.clear()


def _shorten(text: str, limit: int = 120) -> str:
    text = str(text or "").strip()
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _as_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(v) for v in value]