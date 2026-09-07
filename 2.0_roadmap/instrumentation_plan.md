# Instrumentation & Feedback Loop (Step 16)

Status: **partially implemented**. The `/metrics` endpoint (ADR-0003) is live
and exposes the event taxonomy and per-tool counters. This plan defines the
remaining durable pipeline and the feedback loop back into product decisions.

## Event taxonomy (implemented)
Emitted by `Mem20MCPServer`: `tool.call`, `tool.success`, `tool.error`.
Counters: `tool_calls` (per tool), `tool_errors` (per tool), `tool_calls_total`,
`tool_errors_total`, `request_count`, `request_errors`, `memory_system_available`,
`uptime_seconds`.

## Extension plan (2.0)
1. **Engine audit metrics into `/metrics`** — fetch `audit_contamination()`,
   `audit_grounding()`, and `safe_eval_condition` violation counts on a 30s timer
   and merge into `metrics()` so the dashboard shows `contamination_rate`,
   `eval_violations`, `grounding_coverage` without a separate call.
2. **Durable sink (TD-01)** — behind `MEM20_METRICS_SINK`:
   `none` (default) | `prometheus` (text exposition on `/metrics`) |
   `otlp` (push). Avoids blocking stdio.
3. **Event log ring buffer** — keep last N events in memory for `/debug/events`
   (dev only, off by default).
4. **Feedback loop** — weekly export of `tool_errors`, `contamination_rate`, and
   `recall_precision` into the Step 11 dashboard; regressions gate release.

## Implementation notes (already done)
- `server.py`: `__init__` seeds `_tool_calls`/`_tool_errors`/`_event_taxonomy`;
  `_handle_call_tool` increments per-tool counters on call/error;
  `metrics()` returns the extended block.
- `health.py` `/metrics` handler already serializes the extended block to JSON.

## Experimentation guidelines
- Feature flags via env (`MEM20_FLAG_<name>`) read by tool registration, so a
  beta tool can ship behind a flag (see Step 17) without a code branch in dispatch.
- Never A/B test safety gates (contamination firewall, eval safety) — they are
  hard invariants, not tunables.
