"""Shared data contracts for mem20orcaz.

Pure-standard-library TypedDicts (and small helpers) mirroring OrKa's contracts:
the runtime Context, per-agent Output, ResourceConfig (dependency injection
descriptor), Trace (enhanced execution trace) and MemoryEntry records.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional, TypedDict


class Context(TypedDict, total=False):
    """Runtime context handed to agents during a run.

    Matches OrKa's Context contract: input data, previous outputs (keyed by
    agent id), metadata and a trace_id for correlation.
    """

    input: Any
    previous_outputs: Dict[str, Any]
    metadata: Dict[str, Any]
    trace_id: str


class Output(TypedDict, total=False):
    """An individual agent output entry."""

    agent_id: str
    response: Any
    confidence: Optional[float]
    internal_reasoning: Optional[str]
    metrics: Dict[str, Any]
    error: Optional[str]


class ResourceConfig(TypedDict, total=False):
    """Descriptor for a lazily-injected runtime resource (llm, embedder...)."""

    type: str
    name: str
    options: Dict[str, Any]


class Trace(TypedDict, total=False):
    """Enhanced execution trace for a run."""

    trace_id: str
    run_id: str
    timestamp: str
    version: str
    execution_metadata: Dict[str, Any]
    agent_executions: List[Dict[str, Any]]
    memory_stats: Dict[str, Any]
    logs: List[Dict[str, Any]]


class MemoryEntry(TypedDict, total=False):
    """A single memory record."""

    key: str
    value: Any
    namespace: str
    timestamp: str
    metadata: Dict[str, Any]


class OrkaResponse(TypedDict, total=False):
    """An agent/node execution response."""

    response: Any
    result: Any
    agent_id: str
    component_id: str
    component_type: str
    trace_id: str
    execution_start_time: str
    execution_end_time: str
    execution_time_seconds: float
    confidence: float
    internal_reasoning: str
    memory_key: Optional[str]
    metrics: Dict[str, Any]
    error: Optional[str]
    # Extensions (kept distinct from OrKa fields to avoid data loss)
    _metrics: Dict[str, Any]


def new_trace_id() -> str:
    """Generate a fresh trace id (uuid4 hex)."""
    return uuid.uuid4().hex


def now_iso() -> str:
    """Current time in ISO 8601 format (UTC)."""
    import datetime

    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def set_current_trace_id(context: Optional[Context]) -> str:
    """Return (and if missing, set) the trace_id on a context dict."""
    tid = (context or {}).get("trace_id") or new_trace_id()
    if context is not None and "trace_id" not in context:
        context["trace_id"] = tid
    return tid