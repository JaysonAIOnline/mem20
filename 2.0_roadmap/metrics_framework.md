# Outcome & Metrics Framework (Step 11)

Grounded in the live `/metrics` endpoint (`mcp/health.py`) and the engine's
verifiable safety properties. Every metric below is either already emitted or
has a defined collection path.

## North-star
**"Trusted memory that improves decisions without poisoning reasoning."**
Operationalized as recall trust × safe grounding rate.

## Metric dictionary

| Metric | Definition | Source | Target (2.0) |
|--------|------------|--------|--------------|
| `uptime_seconds` | Process liveness | `/metrics` | ≥ 99.5% |
| `request_count` / `request_errors` | MCP transport health | `/metrics` | error rate < 1% |
| `tool_calls_total` / `tool_errors_total` | Per-tool reliability | `/metrics` | per-tool error < 2% |
| `memory_system_available` | Engine bootstrap OK | `/metrics` | true |
| `contamination_rate` | simulated records in grounded/BM25 indexes | `audit_contamination()` | 0.0 (hard gate) |
| `eval_violations` | unsafe conditions blocked by `safe_eval_condition` | engine log | 0 accepted |
| `promotion_errors` | rejected simulated→grounded promotions | engine log | 0 silent |
| `recall_precision` | grounded hits / total recall | eval harness | ≥ 0.9 |
| `grounding_coverage` | grounded memories / total | `audit_grounding()` | ≥ 0.8 |

## Instrumentation status (Step 11 → Step 16)
- 6 of the above are live today (`uptime`, `request_*`, `tool_*`,
  `memory_system_available`) via the `/metrics` endpoint.
- 3 are emitted by the engine audit/log path (`contamination_rate`,
  `eval_violations`, `promotion_errors`) — wire into `/metrics` in Step 16.
- 2 (`recall_precision`, `grounding_coverage`) require an eval harness shipped
  with the 2.0 test suite.

## Outcome statements (SMART)
1. Reduce contamination incidents to **0** in production (already 0 in audit).
2. Cut mean time-to-add-a-tool from ~hours (4.8k-line edit) to < 30 min (domain
   module edit) — measured by onboarding task.
3. Achieve ≥ 99.5% MCP transport uptime with the health endpoint as the probe.
