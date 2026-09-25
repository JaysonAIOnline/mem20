"""Resource registry for mem20orcaz.

Pure-stdlib port of OrKa's ResourceRegistry: lazily injects runtime resources
(the LLM gateway, embedders, custom handlers) so agents only touch them when
needed. No transcendental dependencies; a resource that is not configured
stays None.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

_DEFAULT_RESOURCES = ("llm", "embedder", "custom")


class ResourceRegistry:
    """Lazy dependency-injection container for runtime resources."""

    def __init__(self) -> None:
        self._factories: Dict[str, Callable[[], Any]] = {}
        self._instances: Dict[str, Any] = {}
        self._resolved: set[str] = set()

    def register(self, name: str, factory: Callable[[], Any]) -> None:
        if not callable(factory):
            raise TypeError(f"resource {name!r} factory must be callable")
        self._factories[name] = factory
        self._instances.pop(name, None)
        self._resolved.discard(name)

    def register_instance(self, name: str, instance: Any) -> None:
        self._instances[name] = instance
        self._resolved.add(name)

    def has(self, name: str) -> bool:
        return name in self._factories or name in self._instances

    def get(self, name: str) -> Optional[Any]:
        if name in self._instances:
            return self._instances[name]
        factory = self._factories.get(name)
        if factory is None:
            return None
        if name not in self._resolved:
            try:
                self._instances[name] = factory()
            except Exception as error:  # lazy: surface on first use
                logger.warning("resource %r failed to initialize: %s", name, error)
                self._instances[name] = None
            self._resolved.add(name)
        return self._instances.get(name)

    def set(self, name: str, value: Any) -> None:
        self._instances[name] = value
        self._resolved.add(name)

    def get_or_raise(self, name: str) -> Any:
        value = self.get(name)
        if value is None:
            raise LookupError(
                f"resource {name!r} is not configured; a default LLM gateway is required for live runs"
            )
        return value

    def names(self) -> list[str]:
        return sorted(set(self._factories) | set(self._instances))

    def clear(self) -> None:
        self._factories.clear()
        self._instances.clear()
        self._resolved.clear()


def init_registry(resources: Optional[Dict[str, Any]] = None) -> ResourceRegistry:
    """Build a registry, optionally pre-wiring instances from a config dict."""
    registry = ResourceRegistry()
    for name, instance in (resources or {}).items():
        registry.register_instance(name, instance)
    return registry