# Step 16 — Instrumentation & Feedback Loop

**Type:** engineering. **Status:** PARTIAL (endpoint live; durable sink + engine
metrics pending). See `instrumentation_plan.md`.

## Deliverables
- **Event taxonomy** (`tool.call`, `tool.success`, `tool.error`) — IMPLEMENTED in
  `server.py` + exposed on `/metrics`.
- **Per-tool counters** (`tool_calls`, `tool_errors`) — IMPLEMENTED.
- **Extension plan** (Step 16 §1–4): merge engine audit metrics into `/metrics`,
  durable sink behind `MEM20_METRICS_SINK`, dev event ring buffer, weekly export
  feeding Step 11 dashboard.
- **Experimentation guidelines:** env feature flags (`MEM20_FLAG_*`), no A/B on
  safety gates.

## Code landed for this step
- `server.py`: `__init__` seeds counters/taxonomy; `_handle_call_tool` increments
  on call/error; `metrics()` returns the extended block (verified live).
- `health.py` `/metrics` serializes it.

## Remaining (tracked TD-01 / Step 16 §2)
Durable sink + engine audit metrics merge — schedule after E2.4 (pytest+CI).
