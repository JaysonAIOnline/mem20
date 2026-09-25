"""Agent factory for mem20orcaz.

Pure-stdlib port of OrKa's AgentFactory: a registry that maps agent type names
to deterministic classes (and structured/custom agent types), and lazily builds
agent instances from a config map. Created agents share the resource registry so
the LLM gateway is injected without any provider being imported.
"""

from __future__ import annotations

import inspect
from typing import Any, Callable, Dict, Optional

from .agents import AGENT_CLASSES
from .nodes import NODE_CLASSES
from .registry import ResourceRegistry


class AgentFactoryError(Exception):
    """Raised for unknown agent types or factory misuse."""


class AgentFactory:
    """Creates agent instances from a type/class registry + configs."""

    def __init__(self, config_map: Optional[Dict[str, Any]] = None,
                 registry: Optional[ResourceRegistry] = None) -> None:
        self.config_map: Dict[str, Any] = dict(config_map or {})
        self.registry = registry or ResourceRegistry()
        self.classes: Dict[str, Any] = {}
        self.structured_classes: Dict[str, Any] = {}
        self.custom_agents: Dict[str, Any] = {}
        self._cache: Dict[str, Any] = {}
        self._register_defaults()

    # -- registration --------------------------------------------------------
    def _register_defaults(self) -> None:
        for name, cls in AGENT_CLASSES.items():
            self.register_agent_class(name, cls)
        for name, cls in NODE_CLASSES.items():
            self.register_agent_class(name, cls)

    def register_agent_class(self, type_name: str, cls: Any) -> None:
        self.classes[str(type_name)] = cls
        self._cache.clear()

    def register_node_class(self, type_name: str, cls: Any) -> None:
        self.classes[str(type_name)] = cls
        self._cache.clear()

    def register_structured_class(self, type_name: str, cls: Any) -> None:
        self.structured_classes[str(type_name)] = cls
        self._cache.clear()

    def register_custom_agent(self, type_name: str, agent: Any) -> None:
        self.custom_agents[str(type_name)] = agent
        self._cache.clear()

    def register_type(self, type_name: str, cls: Any) -> None:
        self.register_agent_class(type_name, cls)

    def unregister(self, type_name: str) -> None:
        self.classes.pop(str(type_name), None)
        self._cache.clear()

    # -- metadata -------------------------------------------------------------
    @property
    def agent_types(self) -> Dict[str, Any]:
        return dict(self.classes)

    def get_agent_meta(self, agent_id: str) -> Dict[str, Any]:
        cfg = self.config_map.get(str(agent_id)) or {}
        return {"id": str(agent_id), "type": cfg.get("type") if isinstance(cfg, dict) else "custom",
                "config": cfg}

    def get_agent_config(self, agent_id: str) -> Dict[str, Any]:
        cfg = self.config_map.get(str(agent_id), {})
        return dict(cfg) if isinstance(cfg, dict) else {"config": cfg}

    # -- creation -------------------------------------------------------------
    def create(self, agent_id: str, config: Optional[Dict[str, Any]] = None, registry: Any = None) -> Any:
        agent_id = str(agent_id)
        cfg = config if config is not None else self.get_agent_config(agent_id)
        reg = registry or self.registry
        cache_key = f"{agent_id}::{cfg.get('type') if isinstance(cfg, dict) else ''}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        ctype = str(cfg.get("type") or "llm")
        custom = self.custom_agents.get(ctype) or self.custom_agents.get(agent_id)
        if custom is not None:
            self._cache[cache_key] = custom
            return custom

        cls = self.classes.get(ctype)
        if cls is None:
            raise AgentFactoryError(
                f"unknown agent type {ctype!r} for agent {agent_id!r} "
                f"(known: {sorted(self.classes)})")
        instance = self._instantiate(cls, agent_id, cfg, reg)
        self._cache[cache_key] = instance
        return instance

    def create_for(self, agent_id: str) -> Any:
        return self.create(agent_id)

    def _instantiate(self, cls: Any, agent_id: str, cfg: Dict[str, Any], registry: Any) -> Any:
        prompt = cfg.get("prompt") or cfg.get("description") or ""
        params = dict(cfg.get("params") or {})
        sig = inspect.signature(cls.__init__)
        plist = list(sig.parameters.values())
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
            return cls(agent_id, prompt, **params)

    def build_all(self, agent_ids: Optional[list] = None) -> Dict[str, Any]:
        ids = agent_ids or list(self.config_map.keys())
        return {aid: self.create(aid) for aid in ids}


def default_factory(config_map: Optional[Dict[str, Any]] = None,
                    registry: Optional[ResourceRegistry] = None) -> AgentFactory:
    return AgentFactory(config_map=config_map, registry=registry)