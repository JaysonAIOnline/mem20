"""mem20langz — native mem20 graph substrate absorption: core types.

START/END sentinel nodes, Command (goto/resume/update), Send (dynamic fan-out),
interrupt()/Interrupt (human-in-loop pause), and LangzError hierarchy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


class LangzError(Exception):
    """Base error for mem20langz."""


class InvalidUpdateError(LangzError):
    """Node returned something that cannot be applied to state."""


class GraphRecursionError(LangzError):
    """Recursion limit exceeded before reaching END."""


class InvalidCheckpointerError(LangzError):
    """Checkpoint error (missing thread_id, duplicate checkpoint, etc.)."""


class Interrupt:
    """Represents a paused run awaiting external input.

    Mirrors mem20 graph substrate.types.Interrupt: carries the value surfaced to the
    caller when the node called interrupt().
    """

    __slots__ = ("value",)

    def __init__(self, value: Any) -> None:
        self.value = value

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"Interrupt(value={self.value!r})"


class _StartNode:
    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return "START"

    def __len__(self) -> int:
        return 0


class _EndNode:
    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return "END"

    def __len__(self) -> int:
        return 0


START = _StartNode()
END = _EndNode()
"""Sentinel node markers used in edges: every graph begins after START and ends at END."""


@dataclass(frozen=True)
class Send:
    """Schedule the given ``node`` to run with ``arg`` as its input.

    Returned (potentially a list of them) from a node to dynamically fan out
    work to multiple invocations of the same node.
    """

    node: str
    arg: Any
    timeout: Optional[float] = None

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"Send(node={self.node!r}, arg={self.arg!r})"


@dataclass
class Command:
    """Multi-field update returned by a node.

    - ``update``: partial state to merge/reduce before the next node runs.
    - ``goto``:   next node to schedule (overrides the static edge).
    - ``resume``: value supplied to a previously interrupted node.
    """

    update: dict[str, Any] = field(default_factory=dict)
    goto: Any = None
    resume: Any = None

    class Interrupt:  # type: ignore[no-redef]
        """Namespace mirroring mem20 graph substrate's ``Command.Interrupt`` marker."""

        def __init__(self, value: Any) -> None:
            self.value = value


def interrupt(value: Any) -> Any:
    """Pause the run and surface ``value`` to the caller (human-in-the-loop).

    On a resumed run, the caller-supplied value is returned in place of this
    function (mem20 graph substrate resume semantics); otherwise the current run pauses
    and raises InterruptReceived internally.
    """
    from ._runtime import _tls

    slot = getattr(_tls, "interrupt_slot", None)
    if slot is not None:
        if slot.resume_value is not None:
            return slot.resume_value
        slot.payload = value
        raise InterruptReceived(value)
    raise LangzError("interrupt() called outside of a running graph")


class InterruptReceived(LangzError):
    """Internal: raised inside a node that called interrupt()."""

    def __init__(self, payload: Any, storage: "Optional[dict[str, Any]]" = None) -> None:
        super().__init__("graph interrupted")
        self.payload = payload
        self.storage = storage or {}


def is_command_result(obj: Any) -> bool:
    return isinstance(obj, Command)


def normalize_node_return(state_type: Callable[[dict[str, Any]], dict[str, Any]], result: Any) -> tuple[dict[str, Any], list[Send], Any]:
    """Normalize a node return value.

    Accepts a plain partial-state dict, a Command (update+goto+resume), a bare
    Send or list of Sends (pure fan-out, no state write), or None (no write).
    Returns (updates, sends, goto).
    """
    updates: dict[str, Any]
    sends: list[Send]
    goto: Any = None

    if isinstance(result, Command):
        updates = dict(result.update or {})
        sends = []
        if isinstance(result.goto, Send):
            sends.append(result.goto)
        elif isinstance(result.goto, list) and all(isinstance(x, Send) for x in result.goto):
            sends.extend(result.goto)
        elif result.goto is not None:
            goto = result.goto
        if result.resume is not None:
            updates["__resume__"] = result.resume
        return updates, sends, goto

    if isinstance(result, Send):
        return {}, [result], None
    if isinstance(result, list) and all(isinstance(x, Send) for x in result):
        return {}, list(result), None

    if result is None:
        return {}, [], None

    if not isinstance(result, dict):
        raise InvalidUpdateError(
            f"Expected dict, Command, Send, or list[Send], got {type(result).__name__}"
        )
    return dict(result), [], None