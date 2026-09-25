"""Flow — @start / @listen over roadmap phases (cleanroom mem20 crews Flow).

A Flow is a small event-driven pipeline: @start handlers run first, then any
state they emit (returned string/list or via self.emit) dispatches to @listen
handlers. Each handler is a roadmap phase, so flow.run() leaves dotted roadmap
provenance identical to a Crew run. {var} interpolation is available to handlers
through the injected context (inputs / state).

Two supported styles (same run engine):
  class-level  — subclass Flow and decorate methods with the module-level
                 `start` / `listen` helpers (mem20 crews-idiomatic):
                     class Pipeline(Flow):
                         @start
                         def begin(self, ctx, state): return "collect"
                         @listen("collect")
                         def collect(self, ctx, state): ...
  instance     — flow = Flow(); flow.start()(fn); flow.listen("s")(fn)

Both run through Flow.run(inputs=...) which persists phases to the roadmap.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .context import interpolate
from .roadmap import ROADMAP_DIR, Roadmap

START_STATE = "__start__"


def start(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Class-level decorator: register fn as a start handler on a Flow subclass."""
    fn._flow_triggers = [START_STATE]
    fn._flow_once = False
    return fn


def listen(*states: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Class-level decorator: register fn to run on one of `states`."""
    def wrapper(fn: Callable[..., Any]) -> Callable[..., Any]:
        fn._flow_triggers = list(states)
        fn._flow_once = False
        return fn
    return wrapper


def listen_once(*states: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Class-level decorator like listen() but the handler fires at most once."""
    def wrapper(fn: Callable[..., Any]) -> Callable[..., Any]:
        fn._flow_triggers = list(states)
        fn._flow_once = True
        return fn
    return wrapper


def router(*states: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """@router decorator (mem20 crews-idiomatic): a handler that listens on `states`
    and whose return value (a str or list) becomes the *only* state dispatched
    onward, rather than being appended to the full emission list. The handler's
    return is a single routing decision — typically used to pick one of several
    downstream branches."""
    def wrapper(fn: Callable[..., Any]) -> Callable[..., Any]:
        fn._flow_triggers = list(states)
        fn._flow_once = False
        fn._flow_router = True
        return fn
    return wrapper


@dataclass
class FlowResult:
    flow: str
    inputs: dict
    emitted: list = field(default_factory=list)
    runs: list = field(default_factory=list)
    roadmap: Optional[Roadmap] = None

    def to_dict(self) -> dict:
        return {
            "flow": self.flow, "inputs": self.inputs,
            "emitted": list(self.emitted), "runs": list(self.runs),
            "roadmap_path": self.roadmap.path if self.roadmap else None,
            "roadmap": self.roadmap.view() if self.roadmap else [],
        }


def _flow_triggers(fn: Any) -> tuple[list, bool, bool]:
    tags = getattr(fn, "_flow_triggers", None)
    if tags is None:
        return [], False, False
    return (list(tags), bool(getattr(fn, "_flow_once", False)),
            bool(getattr(fn, "_flow_router", False)))


class Flow:
    def __init__(self, name: Optional[str] = None, roadmap: bool = True,
                 brain=None, guards=None, roadmap_root: Optional[str] = None) -> None:
        self.name = name or type(self).__name__
        self._handlers: dict[str, Callable[..., Any]] = {}
        self._triggers: dict[str, dict] = {}
        self._once: set[str] = set()
        self._bound: set[str] = set()
        self.state: dict[str, Any] = {}
        self.roadmap_enabled = roadmap
        self.roadmap_root = roadmap_root or ROADMAP_DIR
        self.brain = brain
        self.guards = guards
        self._collect_class_handlers()

    # ------------------------------------------------------- class scanning
    def _collect_class_handlers(self) -> None:
        """Harvest methods decorated with module-level start/listen/router."""
        for attr in dir(type(self)):
            if attr.startswith("_"):
                continue
            try:
                raw = getattr(type(self), attr)
            except Exception:
                continue
            if not callable(raw) or not hasattr(raw, "_flow_triggers"):
                continue
            states, once, is_router = _flow_triggers(raw)
            bound = getattr(self, attr)
            self._handlers[attr] = bound
            self._triggers[attr] = {"on": states, "once": once,
                                    "router": is_router}
            self._bound.add(attr)

    # ------------------------------------------------------------------ api
    def register(self, name: str, fn: Callable[..., Any], *states: str,
                 once: bool = False, router: bool = False) -> None:
        """Instance-style registration (what start()/listen() instance methods
        delegate to)."""
        if not states:
            states = (START_STATE,)
        self._handlers[name] = fn
        self._triggers[name] = {"on": list(states), "once": once,
                                "router": router}

    def router(self, *states: str) -> Any:
        """Instance-decorator form — flow.router()(fn); the handler's return
        value becomes the single state dispatched onward."""
        def wrapper(fn: Callable[..., Any]) -> Callable[..., Any]:
            self.register(fn.__name__, fn, *states, router=True)
            return fn
        return wrapper

    def start(self, fn: Optional[Callable[..., Any]] = None) -> Any:
        """Instance-decorator form — flow.start()(fn)."""
        return self._deco(START_STATE, once=False) if fn is None else \
            self._register_deco(fn, START_STATE, once=False)

    def listen(self, *states: str) -> Any:
        return self._deco(*states, once=False)

    def listen_once(self, *states: str) -> Any:
        return self._deco(*states, once=True)

    def emit(self, *states: str) -> None:
        """Programmatic emission from inside a handler."""
        for s in states:
            if s not in self._pending:
                self._pending.append(s)

    # ------------------------------------------------------------ machinery
    def _deco(self, *states: str, once: bool):
        def wrapper(fn: Callable[..., Any]):
            self.register(fn.__name__, fn, *states, once=once)
            return fn
        return wrapper

    def _register_deco(self, fn: Callable[..., Any], state: str,
                       once: bool) -> Callable[..., Any]:
        self.register(fn.__name__, fn, state, once=once)
        return fn

    def _listeners(self, state: str) -> list[str]:
        return [name for name, t in self._triggers.items()
                if state in t["on"]]

    def run(self, inputs: Optional[dict] = None, max_states: int = 20) -> FlowResult:
        inputs = inputs or {}
        rmap = Roadmap(f"flow-{self.name}", root_dir=self.roadmap_root) \
            if self.roadmap_enabled else None
        result = FlowResult(flow=self.name, inputs=inputs, roadmap=rmap)
        self.state = dict(inputs)
        self._pending: list[str] = []
        self._processed: set[str] = set()
        queue: list[str] = [START_STATE]

        while queue and len(result.runs) < max_states:
            state = queue.pop(0)
            if state in self._processed:
                continue
            self._processed.add(state)
            for fn_name in self._listeners(state):
                if self._triggers[fn_name]["once"] and fn_name in self._once:
                    continue
                if fn_name in self._handlers:
                    result.runs.append({"state": state, "handler": fn_name})
                    if rmap:
                        rmap.running(fn_name)
                    emitted = self._invoke(fn_name, state, inputs)
                    emitted = [s for s in emitted if s]
                    result.emitted.extend(emitted)
                    queue.extend(s for s in emitted if s not in queue)
                    if rmap:
                        rmap.done(fn_name, state=state,
                                  emitted=",".join(emitted) if emitted else "")
                    self._once.add(fn_name)

        if self.guards:
            self.guards.sweep()
        return result

    def _invoke(self, fn_name: str, state: str, inputs: dict) -> list[str]:
        fn = self._handlers[fn_name]
        is_router = bool((self._triggers.get(fn_name) or {}).get("router", False))
        self._pending = []
        ctx = {"inputs": inputs, "state": self.state,
               "flow": self, "name": fn_name}
        out = self._call(fn, ctx, state)
        emitted = [str(s) for s in self._pending if s]
        if isinstance(out, str):
            emitted.append(out)
        elif isinstance(out, (list, tuple)):
            emitted.extend(str(s) for s in out if isinstance(s, str))
        # {var} interpolation of emitted states against current state vars
        result = [interpolate(s, self.state) for s in emitted]
        # a router emits exactly ONE route decision, not every listener hit.
        if is_router and result:
            return [result[0]]
        return result

    @staticmethod
    def _call(fn: Callable[..., Any], ctx: dict, state: str) -> Any:
        import inspect
        try:
            sig = inspect.signature(fn)
        except (TypeError, ValueError):
            return fn(**ctx)
        params = [p for p in sig.parameters.values()
                  if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
        if len(params) >= 2:
            return fn(ctx, state)
        if len(params) == 1:
            return fn(ctx)
        return fn(**ctx)