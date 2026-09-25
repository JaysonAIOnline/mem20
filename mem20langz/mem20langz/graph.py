"""mem20langz — StateGraph builder and graph compilation.

Creates a typed-state graph via add_node / add_edge / add_conditional_edges /
set_entry_point, then compile()s it into a Pregel runtime. Channel reducers are
declared in the state schema dictionary, e.g.:
    {"messages": {"reducer": "add_messages"}, "total": {}}
"""

from __future__ import annotations

from typing import Any, Callable, Optional, Union

from ._runtime import EdgeSpec, NodeSpec, Pregel
from .types import END, START, LangzError, Send


class _DefaultSchema:
    pass


def _schema_from_hint(hint: Any) -> dict[str, Any]:
    """Best-effort expansion of a schema.

    Accepts:
      - dict[str, Any] -> returned as-is (values may be {"reducer": ...}).
      - a TypedDict-like object exposing __annotations__.
    """
    if hint is None:
        return {}
    if isinstance(hint, dict):
        return dict(hint)
    ann = getattr(hint, "__annotations__", None)
    if isinstance(ann, dict):
        out: dict[str, Any] = {}
        for k, v in ann.items():
            out[k] = {}
            src = getattr(v, "__metadata__", None)
            if src:
                try:
                    txt = "".join(getattr(m, "__name__", "") for m in src)
                    if "add_messages" in txt:
                        out[k]["reducer"] = "add_messages"
                    elif "operator.add" in txt or "add" in txt:
                        out[k]["reducer"] = "operator.add"
                except Exception:
                    pass
        return out
    return {}


class StateGraph:
    def __init__(self, state_schema: Any = None) -> None:
        self.schema = _schema_from_hint(state_schema)
        self._nodes: dict[str, NodeSpec] = {}
        self._edges: list[EdgeSpec] = []
        self._entry: Optional[str] = None
        self._finish: Any = None
        self._conditional_entry: Optional[tuple[Callable[[dict[str, Any]], Any], dict[Any, str]]] = None

    # ------------------------------------------------------------------ nodes
    def add_node(self, node: Union[str, Callable[[dict[str, Any]], Any]], action: Optional[Callable[[dict[str, Any]], Any]] = None) -> "StateGraph":
        key = node if isinstance(node, str) else getattr(node, "__name__", "node")
        func = action if callable(action) else node
        if not callable(func):
            raise LangzError(f"Node '{key}' requires a callable action")
        self._nodes[key] = NodeSpec(name=key, func=func)
        return self

    def add_sequence(self, nodes: list[Any]) -> "StateGraph":
        keys: list[str] = []
        for i, n in enumerate(nodes):
            name = getattr(n, "__name__", None)
            key = n if isinstance(n, str) else (name if name and name != "<lambda>" else f"node{i}")
            func = n if callable(n) else None
            if func is None and not isinstance(n, str):
                raise LangzError(f"Sequence node '{key}' must be callable")
            if func is None:
                raise LangzError(f"Sequence node '{key}' must be callable")
            self.add_node(key, func)
            keys.append(key)
        for i in range(1, len(keys)):
            self._edges.append(EdgeSpec(source=keys[i - 1], target=keys[i]))
        if keys:
            self.set_entry_point(keys[0])
        return self

    # ------------------------------------------------------------------ edges
    def add_edge(self, start_key: Union[str, list[str]], end_key: Union[str, Any]) -> "StateGraph":
        sources = start_key if isinstance(start_key, list) else [start_key]
        for src in sources:
            self._edges.append(EdgeSpec(source=src, target=end_key))
        return self

    def add_conditional_edges(
        self,
        source: str,
        path: Callable[[dict[str, Any]], Any],
        path_map: Union[dict[Any, str], list[str], None] = None,
    ) -> "StateGraph":
        if isinstance(path_map, list):
            mapping = {i: k for i, k in enumerate(path_map)}
        elif isinstance(path_map, dict):
            mapping = dict(path_map)
        else:
            mapping = None
        # conditional edge: one EdgeSpec; target resolved at runtime via path()
        self._edges.append(EdgeSpec(source=source, target=None, conditional_path=path, path_map=mapping))
        return self

    def set_entry_point(self, key: str) -> "StateGraph":
        if key is START:
            self._entry = None
        else:
            if key not in self._nodes:
                raise LangzError(f"Entry point '{key}' is not a registered node")
            self._entry = key
        return self

    def set_conditional_entry_point(
        self,
        path: Callable[[dict[str, Any]], Any],
        path_map: Optional[dict[Any, str]] = None,
    ) -> "StateGraph":
        self._conditional_entry = (path, path_map or {})
        return self

    def set_finish_point(self, key: str) -> "StateGraph":
        self._finish = key
        return self

    def validate(self) -> None:
        for e in self._edges:
            if e.source != START and e.source not in self._nodes:
                raise LangzError(f"Edge source '{e.source}' is not a registered node")
        if self._entry is not None and self._entry not in self._nodes:
            raise LangzError(f"Entry point '{self._entry}' not registered")
        if not self._nodes:
            raise LangzError("Graph has no nodes")

    def compile(
        self,
        checkpointer: Any = None,
        interrupt_before: Optional[list[str]] = None,
        interrupt_after: Optional[list[str]] = None,
        debug: bool = False,
        name: Optional[str] = None,
    ) -> Pregel:
        self.validate()

        start_overrides: list[EdgeSpec] = []
        if self._entry is not None:
            start_overrides.append(EdgeSpec(source=str(START), target=self._entry))
        elif self._conditional_entry is not None:
            path, mapping = self._conditional_entry
            start_overrides.append(EdgeSpec(source="__conditional__", target=None, conditional_path=path, path_map=mapping))

        edges = start_overrides + self._edges
        start = self._entry if self._entry is not None else ("__conditional__" if self._conditional_entry else str(START))
        finish = self._finish if self._finish is not None else END
        if finish is not None and finish not in self._nodes and finish is not END:
            edges.append(EdgeSpec(source=finish, target=END))

        return Pregel(
            nodes=self._nodes,
            edges=edges,
            start=start,
            end=finish,
            state_schema=self.schema,
            checkpointer=checkpointer,
            interrupt_before=interrupt_before,
            interrupt_after=interrupt_after,
            name=name or "StateGraph",
        )

    @property
    def nodes(self) -> dict[str, NodeSpec]:
        return self._nodes