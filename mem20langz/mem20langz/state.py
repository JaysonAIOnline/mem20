"""mem20langz — state helpers: Message + add_messages reducer.

Mirrors mem20 graph substrate.graph.message: a minimal immutable Message (role/content/id)
and the additive reducer semantics used with Annotated[list, add_messages].
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable, Union


@dataclass
class Message:
    role: str
    content: Any
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    metadata: dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"Message(role={self.role!r}, content={self.content!r})"

    def to_dict(self) -> dict[str, Any]:
        return {"role": self.role, "content": self.content, "id": self.id, "metadata": self.metadata}


def _to_message(item: Any, fallback_role: str = "assistant") -> Message:
    if isinstance(item, Message):
        return item
    if isinstance(item, dict):
        keys = {k.lower() for k in item.keys()}
        if "role" in keys or "content" in keys:
            role = item.get("role") or item.get("Role") or fallback_role
            return Message(
                role=str(role),
                content=item.get("content", ""),
                id=str(item.get("id") or uuid.uuid4()),
                metadata=dict(item.get("metadata") or {}),
            )
        return Message(role=fallback_role, content=item)
    if isinstance(item, (list, tuple)) and len(item) >= 2 and isinstance(item[0], str):
        return Message(role=item[0], content=item[1], id=str(uuid.uuid4()))
    if isinstance(item, str):
        return Message(role="user", content=item)
    return Message(role=fallback_role, content=item)


def add_messages(left: Any, right: Any) -> list[Message]:
    """Reducer: append messages to a list, replacing any with matching ids.

    Coerces dicts / (role, content) tuples / plain strings into Message.
    Duplicate ids are replaced in place of appended.
    """
    existing: list[Message] = []
    if left is not None:
        if isinstance(left, list):
            existing = [_to_message(x) for x in left]
        elif isinstance(left, Message):
            existing = [left]

    incoming: list[Message]
    if right is None:
        incoming = []
    elif isinstance(right, list):
        incoming = [_to_message(x) for x in right]
    elif isinstance(right, Message):
        incoming = [right]
    else:
        incoming = [_to_message(right)]

    merged: list[Message] = []
    by_id: dict[str, int] = {}
    counter = 0
    for m in existing:
        by_id[m.id] = counter
        merged.append(m)
        counter += 1
    for m in incoming:
        idx = by_id.get(m.id)
        if idx is not None:
            merged[idx] = m
        else:
            by_id[m.id] = counter
            merged.append(m)
            counter += 1
    return merged


HumanMessage = Message
AIMessage = Message


def merge_state_reducer(channel: str, existing: Any, incoming: Any) -> Any:
    """Apply mem20 graph substrate-style reducer semantics to one channel update.

    - If the channel is declared with an Annotated reducer, call reducer(existing, incoming).
    - Otherwise a plain dict field is overwritten.
    """
    if existing is None:
        # still allow list channels to start from a single append
        if isinstance(incoming, list) and channel in _LIST_APPEND_CHANNELS:
            return list(incoming)
        return incoming
    if channel in _LIST_APPEND_CHANNELS:
        reducer = _REDUCERS.get(channel)
        if reducer is not None:
            return reducer(existing, incoming)
        if isinstance(existing, list) and isinstance(incoming, list):
            return existing + incoming
        if isinstance(existing, list):
            existing.append(incoming)
            return existing
    return incoming


_LIST_APPEND_CHANNELS: set[str] = set()
_REDUCERS: dict[str, Any] = {}


def register_reducer(channel: str, reducer: Any) -> None:
    _LIST_APPEND_CHANNELS.add(channel)
    _REDUCERS[channel] = reducer


def register_messages_channel(channel: str = "messages") -> None:
    register_reducer(channel, add_messages)