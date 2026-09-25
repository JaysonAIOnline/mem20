"""Tracing primitives — native absorption of OpenAI Agents SDK tracing."""

from __future__ import annotations

import contextvars
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Optional

current_trace = contextvars.ContextVar("current_trace", default=None)
current_span = contextvars.ContextVar("current_span", default=None)


@dataclass
class Span:
    """Trace span."""
    name: str
    trace_id: str
    span_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    parent_id: Optional[str] = None
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    data: dict = field(default_factory=dict)
    error: Optional[str] = None

    def finish(self, error: Optional[str] = None):
        self.end_time = time.time()
        self.error = error

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_id": self.parent_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": (self.end_time or time.time()) - self.start_time,
            "data": self.data,
            "error": self.error,
        }


@dataclass
class Trace:
    """Execution trace."""
    name: str
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex[:32])
    spans: list[Span] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def add_span(self, span: Span):
        self.spans.append(span)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "trace_id": self.trace_id,
            "spans": [s.to_dict() for s in self.spans],
            "metadata": self.metadata,
        }


@contextmanager
def trace(name: str, metadata: Optional[dict] = None):
    """Create a trace context."""
    tr = Trace(name=name, metadata=metadata or {})
    token = current_trace.set(tr)
    try:
        yield tr
    finally:
        current_trace.reset(token)


@contextmanager
def span(name: str, data: Optional[dict] = None):
    """Create a span within current trace."""
    tr = current_trace.get()
    parent = current_span.get()
    sp = Span(name=name, trace_id=tr.trace_id if tr else "", parent_id=parent.span_id if parent else None, data=data or {})
    token = current_span.set(sp)
    tr.add_span(sp) if tr else None
    try:
        yield sp
    except Exception as e:
        sp.finish(error=str(e))
        raise
    finally:
        sp.finish()
        current_span.reset(token)


def get_current_trace() -> Optional[Trace]:
    return current_trace.get()


def get_current_span() -> Optional[Span]:
    return current_span.get()