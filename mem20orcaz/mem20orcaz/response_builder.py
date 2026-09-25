"""Response construction for mem20orcaz.

Pure-stdlib port of OrKa's ResponseBuilder: builds a normalized
:class:`mem20orcaz.contracts.OrkaResponse` dict for successful and failed
component executions, tracking timing and metadata without data loss.
"""

from __future__ import annotations

import datetime
import time
from typing import Any, Dict, Optional

from .contracts import OrkaResponse, now_iso


def _iso_seconds(iso: str) -> Optional[float]:
    try:
        d = datetime.datetime.fromisoformat(iso)
        if d.tzinfo is None:
            d = d.replace(tzinfo=datetime.timezone.utc)
        return d.timestamp()
    except (ValueError, TypeError):
        try:
            return time.mktime(time.strptime(iso, "%Y-%m-%dT%H:%M:%S"))
        except (ValueError, TypeError):
            return None


class ResponseBuilder:
    """Static helpers for constructing verbalized execution responses."""

    @staticmethod
    def create_success_response(
        result: Any,
        component_id: Optional[str] = None,
        component_type: str = "component",
        execution_start_time: Optional[str] = None,
        trace_id: Optional[str] = None,
        **kwargs: Any,
    ) -> OrkaResponse:
        """Build a success response for a completed component.

        ``component_id`` is the canonical identity; agents may pass ``agent_id``
        via kwargs as an alias for it.
        """
        if component_id is None:
            component_id = kwargs.pop("agent_id", None) or ""
        start = execution_start_time or now_iso()
        end = now_iso()
        elapsed = kwargs.pop("execution_time_seconds", 0.0) or 0.0
        s = _iso_seconds(start)
        e = _iso_seconds(end)
        if s is not None and e is not None:
            elapsed = max(0.0, e - s)
        elif s is not None:
            elapsed = max(0.0, time.time() - s)

        _metrics = dict(kwargs.pop("_metrics", {}) or {})
        _metrics.setdefault("execution_time_seconds", elapsed)

        resp: OrkaResponse = {
            "response": result,
            "result": result,
            "status": "success",
            "component_id": component_id,
            "component_type": component_type,
            "execution_start_time": start,
            "execution_end_time": end,
            "execution_time_seconds": elapsed,
            "trace_id": trace_id or "",
            "_metrics": _metrics,
        }
        for k, v in kwargs.items():
            if v is not None:
                resp.setdefault(k, v)  # type: ignore[typeddict-item]
        return resp

    @staticmethod
    def create_error_response(
        error: BaseException,
        component_id: Optional[str] = None,
        component_type: str = "component",
        execution_start_time: Optional[str] = None,
        trace_id: Optional[str] = None,
        **kwargs: Any,
    ) -> OrkaResponse:
        """Build an error response for a failed component."""
        if component_id is None:
            component_id = kwargs.pop("agent_id", None) or ""
        resp: OrkaResponse = {
            "response": None,
            "result": None,
            "status": "error",
            "component_id": component_id,
            "component_type": component_type,
            "execution_start_time": execution_start_time or now_iso(),
            "execution_end_time": now_iso(),
            "execution_time_seconds": kwargs.pop("execution_time_seconds", 0.0),
            "trace_id": trace_id or "",
            "error": f"{type(error).__name__}: {error}",
            "_metrics": dict(kwargs.pop("_metrics", {}) or {}),
        }
        return resp

    @staticmethod
    def from_plain_response(
        resp: OrkaResponse,
        component_id: str,
        component_type: str,
        **kwargs: Any,
    ) -> OrkaResponse:
        """Normalize a plain dict response into a full OrkaResponse.

        Reserved keys map onto the canonical fields; every other key (including
        control-flow fields produced by nodes such as ``group_id``, ``targets``,
        ``join_complete``) is carried through at the top level so the
        ResponseExtractor can act on it.
        """
        reserved = {
            "response", "result", "status", "agent_id", "component_id",
            "component_type", "execution_start_time", "execution_end_time",
            "execution_time_seconds", "trace_id", "error", "_metrics",
            "input", "metadata", "diag",
        }
        normalized: OrkaResponse = {
            "response": resp.get("response", resp.get("result")),
            "result": resp.get("result", resp.get("response")),
            "status": resp.get("status", "error" if resp.get("error") else "success"),
            "agent_id": resp.get("agent_id"),
            "component_id": resp.get("component_id", component_id),
            "component_type": resp.get("component_type", component_type),
            "execution_start_time": resp.get("execution_start_time", now_iso()),
            "execution_end_time": resp.get("execution_end_time"),
            "execution_time_seconds": resp.get("execution_time_seconds", 0.0),
            "trace_id": resp.get("trace_id", ""),
            "error": resp.get("error"),
            "_metrics": dict(resp.get("_metrics") or {}),
        }
        for extra in ("confidence", "internal_reasoning", "memory_key", "metrics"):
            if resp.get(extra) is not None:
                normalized[extra] = resp[extra]  # type: ignore[typeddict-item]
        # carry through node/agent-specific result keys
        for k, v in resp.items():
            if k not in reserved and v is not None:
                normalized.setdefault(k, v)  # type: ignore[typeddict-item]
        payload = resp.get("response")
        if isinstance(payload, dict):
            for k, v in payload.items():
                if k not in reserved and v is not None:
                    normalized.setdefault(k, v)  # type: ignore[typeddict-item]
        for k, v in kwargs.items():
            if v is not None:
                normalized.setdefault(k, v)  # type: ignore[typeddict-item]
        return normalized