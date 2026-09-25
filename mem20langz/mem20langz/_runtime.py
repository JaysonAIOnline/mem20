"""mem20langz — Pregel runtime.

Executes a compiled graph as a series of BFS supersteps. Each superstep runs
every scheduled task concurrently; tasks that emit Send schedule new tasks for
the next superstep. Supports invoke, stream (modes: values/updates), batch,
checkpoint resume, and interrupt/resume (human-in-the-loop).

Reducer resolution per channel:
  - ``messages`` -> add_messages (append + id-dedup)
  - ``append``   -> list concat (Annotated[list, operator.add])
  - plain dict field -> overwrite
"""

from __future__ import annotations

import copy
import threading
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Iterator, Optional

from .checkpointer import BaseCheckpointSaver
from .types import (
    Command,
    END,
    GraphRecursionError,
    InterruptReceived,
    START,
    Send,
    normalize_node_return,
)

# ---------------------------------------------------------------------------
# Interrupt plumbing: types.interrupt() consults the thread-local slot while a
# node executes so it can distinguish "in a node" from "outside a graph".
# ---------------------------------------------------------------------------
_tls = threading.local()


class _InterruptSlot:
    __slots__ = ("payload", "event", "resume_value")

    def __init__(self) -> None:
        self.payload: Any = None
        self.event: Optional[dict[str, Any]] = None
        self.resume_value: Any = None


@dataclass
class NodeSpec:
    name: str
    func: Callable[[dict[str, Any]], Any]


@dataclass
class EdgeSpec:
    source: str
    target: Any
    conditional_path: Optional[Callable[[dict[str, Any]], Any]] = None
    path_map: Optional[dict[Any, str]] = None


@dataclass
class Task:
    node: str
    send_input: Any = None


@dataclass
class Config:
    thread_id: str
    checkpoint_ns: str = ""
    checkpoint_id: Optional[str] = None
    recursion_limit: int = 25

    @staticmethod
    def from_config(config: Optional[dict[str, Any]]) -> "Config":
        c = dict(config or {})
        nested = c.get("configurable") or {}
        return Config(
            thread_id=str(nested.get("thread_id") or c.get("thread_id") or "default"),
            checkpoint_ns=str(nested.get("checkpoint_ns") or c.get("checkpoint_ns") or ""),
            checkpoint_id=nested.get("checkpoint_id"),
            recursion_limit=int(c.get("recursion_limit") or nested.get("recursion_limit") or 25),
        )

    def as_config(self) -> dict[str, Any]:
        cc: dict[str, Any] = {"thread_id": self.thread_id, "checkpoint_ns": self.checkpoint_ns}
        if self.checkpoint_id:
            cc["checkpoint_id"] = self.checkpoint_id
        return {"configurable": cc, "recursion_limit": self.recursion_limit}


class Pregel:
    """Compiled, executable graph."""

    def __init__(
        self,
        nodes: dict[str, NodeSpec],
        edges: list[EdgeSpec],
        start: str,
        end: str,
        state_schema: Optional[dict[str, Any]] = None,
        checkpointer: Optional[BaseCheckpointSaver] = None,
        interrupt_before: Optional[Iterable[str]] = None,
        interrupt_after: Optional[Iterable[str]] = None,
        name: str = "Memmem20",
    ) -> None:
        self.nodes = nodes
        self.edges = edges
        self.start = start
        self.end = end
        self.state_schema = state_schema or {}
        self.checkpointer = checkpointer
        self.interrupt_before = set(interrupt_before or [])
        self.interrupt_after = set(interrupt_after or [])
        self.name = name

    # ------------------------------------------------------------------ public
    def invoke(self, input_data: Any, config: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        cfg = Config.from_config(config)
        self._last_streamed_state = None
        for _ in self._stream(cfg, input_data, []):
            pass
        return self._clean_state(self._last_streamed_state or {})

    def _clean_state(self, state: dict[str, Any]) -> dict[str, Any]:
        out = {}
        for k, v in state.items():
            if k == "_interrupt":
                out["_interrupt"] = copy.deepcopy(v)
            elif not k.startswith("_"):
                out[k] = copy.deepcopy(v)
        return out

    def stream(self, input_data: Any, config: Optional[dict[str, Any]] = None, stream_mode: Any = "values") -> Iterator[Any]:
        cfg = Config.from_config(config)
        modes = stream_mode if isinstance(stream_mode, (list, tuple)) else [stream_mode]
        yield from self._stream(cfg, input_data, modes)

    def batch(self, inputs: list[Any], config: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
        return [self.invoke(i, config) for i in inputs]

    async def ainvoke(self, input_data: Any, config: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        import asyncio

        return await asyncio.to_thread(self.invoke, input_data, config)

    async def astream(self, input_data: Any, config: Optional[dict[str, Any]] = None, stream_mode: Any = "values"):
        import asyncio

        cfg = Config.from_config(config)
        modes = stream_mode if isinstance(stream_mode, (list, tuple)) else [stream_mode]
        for event in await asyncio.to_thread(self._stream_to_list, cfg, input_data, modes):
            yield event

    def _stream_to_list(self, cfg: Config, input_data: Any, modes: list[Any]) -> list[Any]:
        return list(self._stream(cfg, input_data, modes))

    # ---------------------------------------------------------------- execution
    def _stream(self, cfg: Config, input_data: Any, modes: list[Any]) -> Iterator[Any]:
        state = self._current_state(cfg)
        if state is None:
            initial = self._build_input(input_data)
            state = dict(initial)
            if self.checkpointer is not None:
                self.checkpointer.put(cfg.thread_id, copy.deepcopy(state), interrupt=False)

        tasks: list[Task] = []
        pending = self.checkpointer.get_pending(cfg.thread_id) if self.checkpointer else None
        interrupted = self._checkpoint_interrupted(cfg)
        resume_active = False
        resume_nodes: set[str] = set()
        if interrupted is not None:
            resume_active = True
            resume = self._resume_value(input_data)
            resume_nodes = set(interrupted.get("_pending") or [self._interrupted_node(cfg)])
            tasks = [Task(node=n) for n in resume_nodes]
            if resume is not None:
                state["__resume__"] = resume
        else:
            if self.start == "__conditional__":
                key = None
                for e in self.edges:
                    if e.source == "__conditional__":
                        key = e.conditional_path(state) if e.conditional_path else None
                        target = (e.path_map or {}).get(key, None)
                        tasks = [Task(node=target)] if target and target is not END else []
                        break
                if tasks:
                    pass
                elif not tasks and key is None:
                    raise GraphRecursionError("Conditional entry point mapped to END or unknown key")
            else:
                tasks = [Task(node=self.start)]

        steps = 0
        while True:
            if not tasks:
                break
            if steps >= cfg.recursion_limit:
                raise GraphRecursionError(
                    f"Recursion limit ({cfg.recursion_limit}) reached before END; "
                    f"next node(s): {[t.node for t in tasks]}."
                )
            steps += 1
            next_tasks: list[Task] = []
            superstep_updates: list[dict[str, Any]] = []
            interrupted_here = False

            for task in tasks:
                node = self.nodes[task.node]
                fn_input: Any = dict(state) if not task.send_input else task.send_input

                slot = _InterruptSlot()
                prior = getattr(_tls, "interrupt_slot", None)
                _tls.interrupt_slot = slot
                if resume_active and task.node in resume_nodes:
                    slot.resume_value = state.get("__resume__")
                    state.pop("__resume__", None)
                try:
                    if task.send_input is not None and isinstance(task.send_input, dict) and not any(
                        k in task.send_input for k in state
                    ):
                        result = node.func(task.send_input)
                    else:
                        result = node.func(fn_input)
                except InterruptReceived as ir:
                    interrupted_here = True
                    slot.payload = ir.payload
                    self._record_interrupt(cfg, state, task.node, ir.payload)
                    _tls.interrupt_slot = prior
                    continue
                finally:
                    _tls.interrupt_slot = prior

                updates, sends, goto = normalize_node_return(node.func, result)

                if updates:
                    state = dict(state)
                    for k, v in updates.items():
                        state[k] = self._apply_update(k, state.get(k), v)
                    superstep_updates.append({task.node: updates})

                if sends:
                    for s in sends:
                        next_tasks.append(Task(node=s.node, send_input=s.arg))

                if goto is not None:
                    if goto is not END:
                        next_tasks.append(Task(node=str(goto)))
                else:
                    for e in self.edges:
                        if e.source != task.node:
                            continue
                        target = e.target
                        if e.conditional_path is not None:
                            key = e.conditional_path(state)
                            target = (e.path_map or {}).get(key, target)
                        if target is END:
                            continue
                        if target is not None:
                            next_tasks.append(Task(node=str(target)))

            if interrupted_here:
                self._last_streamed_state = copy.deepcopy(state)
                if "updates" in modes:
                    yield ("updates", {"__interrupt__": self._last_interrupt(cfg)})
                if "values" in modes:
                    yield ("values", copy.deepcopy(state))
                return

            if self.checkpointer is not None and (superstep_updates or not next_tasks):
                self.checkpointer.put(cfg.thread_id, copy.deepcopy(state), interrupt=False)

            if "values" in modes and (superstep_updates or not next_tasks):
                yield ("values", copy.deepcopy(state))
            if "updates" in modes:
                for ev in superstep_updates:
                    yield ("updates", ev)

            tasks = next_tasks

        self._last_streamed_state = copy.deepcopy(state)
        if self.checkpointer is not None:
            self.checkpointer.put(cfg.thread_id, copy.deepcopy(state), interrupt=False)

    # ------------------------------------------------------------ state helpers
    def _apply_update(self, channel: str, existing: Any, incoming: Any) -> Any:
        kind = self._channel_kind(channel)
        if kind == "messages":
            from .state import add_messages

            return add_messages(existing, incoming)
        if kind == "append":
            if existing is None:
                return list(incoming) if isinstance(incoming, list) else [incoming]
            if isinstance(existing, list):
                if isinstance(incoming, list):
                    return existing + incoming
                return existing + [incoming]
            if isinstance(incoming, list):
                return [existing] + incoming
            return [existing, incoming]
        return copy.deepcopy(incoming)

    def _channel_kind(self, channel: str) -> str:
        t = self.state_schema.get(channel)
        if t is None:
            return "overwrite"
        if isinstance(t, dict) and t.get("reducer") in ("add_messages", "operator.add", "append"):
            return "messages" if t.get("reducer") == "add_messages" else "append"
        if isinstance(t, str):
            if "add_messages" in t:
                return "messages"
            if "operator.add" in t or "append" in t:
                return "append"
        return "overwrite"

    def _build_input(self, raw: Any) -> dict[str, Any]:
        if raw is None:
            return {}
        if isinstance(raw, Command):
            return dict(raw.update or {})
        if isinstance(raw, dict):
            return dict(raw)
        return {"input": raw}

    def update_state(self, config: Optional[dict[str, Any]], values: dict[str, Any]) -> None:
        cfg = Config.from_config(config)
        if self.checkpointer is None:
            return
        state = self._current_state(cfg) or {}
        merged = dict(copy.deepcopy(state))
        for k, v in values.items():
            merged[k] = self._apply_update(k, state.get(k), v)
        self.checkpointer.put(cfg.thread_id, merged, interrupt=False)

    # ------------------------------------------------------------- interrupt
    def _record_interrupt(self, cfg: Config, state: dict[str, Any], node: str, payload: Any) -> None:
        if self.checkpointer is None:
            self._last_payload = payload
            self._last_node = node
            self._pending_nodes = [node]
            return
        snap = copy.deepcopy(state)
        snap["_interrupt"] = payload
        snap["_pending"] = [node]
        self.checkpointer.put(cfg.thread_id, snap, interrupt=True)

    def _last_interrupt(self, cfg: Config) -> Optional[Any]:
        if self.checkpointer is not None:
            st = self.checkpointer.get(cfg.thread_id)
            if st and st["state"].get("_interrupt") is not None:
                return st["state"]["_interrupt"]
        return getattr(self, "_last_payload", None)

    def _checkpoint_interrupted(self, cfg: Config) -> Optional[dict[str, Any]]:
        if self.checkpointer is None:
            return None
        st = self.checkpointer.get(cfg.thread_id)
        if st and st.get("interrupt"):
            return st["state"]
        return None

    def _interrupted_node(self, cfg: Config) -> str:
        if self.checkpointer is not None:
            st = self.checkpointer.get(cfg.thread_id)
            if st and st["state"].get("_pending"):
                return st["state"]["_pending"][0]
        return getattr(self, "_last_node", self.start)

    def _resume_value(self, input_data: Any) -> Any:
        if isinstance(input_data, Command) and input_data.resume is not None:
            return input_data.resume
        return None

    def _final_state(self, cfg: Config, input_data: Any) -> dict[str, Any]:
        st = self._current_state(cfg)
        if st is None:
            return {}
        out = {k: copy.deepcopy(v) for k, v in st.items() if not k.startswith("_")}
        if st.get("_interrupt") is not None:
            out["_interrupt"] = copy.deepcopy(st["_interrupt"])
        return out

    # ---------------------------------------------------------- checkpointer
    def _current_state(self, cfg: Config) -> Optional[dict[str, Any]]:
        if self.checkpointer is None:
            return None
        cp = self.checkpointer.get(cfg.thread_id)
        return copy.deepcopy(cp["state"]) if cp else None

    # ----------------------------------------------------------- introspection
    def get_state(self, config: Optional[dict[str, Any]] = None) -> Optional[dict[str, Any]]:
        cfg = Config.from_config(config)
        if self.checkpointer is None:
            return None
        cp = self.checkpointer.get(cfg.thread_id)
        return copy.deepcopy(cp["state"]) if cp else None

    def get_state_history(self, config: Optional[dict[str, Any]] = None, limit: int = 50) -> list[dict[str, Any]]:
        cfg = Config.from_config(config)
        if self.checkpointer is None:
            return []
        return self.checkpointer.list(cfg.thread_id, limit=limit)

    def get_graph(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "start": self.start,
            "end": ("END" if self.end is END else self.end),
            "nodes": [n.name for n in self.nodes.values()],
            "edges": [
                {
                    "source": e.source,
                    "target": "END" if e.target is END else e.target,
                    "conditional": e.conditional_path is not None,
                }
                for e in self.edges
            ],
        }

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"Pregel(name={self.name!r}, nodes={list(self.nodes)!r})"