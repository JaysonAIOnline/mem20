# Step 11 — Outcome Definition & Success Metrics

**Type:** engineering. **Status:** DONE (framework produced).

## Deliverables
- **North-star statement** + operationalization (trust × safe grounding).
- **Metric dictionary** (`metrics_framework.md`): 9 metrics, source, 2.0 targets.
- **Live metrics** wired via `/metrics` (6 of 9 already emitted).
- **3 SMART outcome statements** (contamination = 0; add-tool < 30 min;
  transport uptime ≥ 99.5%).

## Engineering tie-in
- `metrics()` in `server.py` already returns `uptime`, `request_*`, `tool_*`,
  `memory_system_available`.
- Remaining 3 metrics (`contamination_rate`, `eval_violations`, `grounding_coverage`)
  are emitted by engine audit paths; Step 16 merges them into `/metrics`.

## Not executable by agent
Defining *business* outcomes (revenue, retention) needs product owners; this file
supplies the measurable, code-backed translation.
