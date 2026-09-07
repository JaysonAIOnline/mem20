# Tech-Debt & Risk Register (Step 10)

Scope: technical architecture review & scalability audit for mem20 2.0. Severity
and effort are 1–5 (5 = highest). Source of truth for the audit is the current
codebase state after the Phase 7 hardening + MCP decomposition.

| ID | Area | Finding | Severity | Effort | Mitigation / Owner |
|----|------|---------|----------|--------|--------------------|
| TD-01 | mcp/health.py | Metrics are in-memory; lost on restart; no durable sink | 2 | 2 | Step 16: add push exporter (Prometheus/OTLP) behind `MEM20_METRICS_SINK` |
| TD-02 | memory_engine/memory.py | Vector index uses in-process FAISS; not shared across MCP processes | 3 | 4 | Document single-writer constraint; for 2.0 consider external vector store (ADR pending) |
| TD-03 | memory_engine/memory.py | `predict()` mutates live world-model state (simulate_step side effect) | 2 | 1 | Make `predict()` snapshot/restore like `counterfactual()` (cheap fix) |
| TD-04 | mcp/* | No automated test suite until Phase 7 close; only 2 verification scripts | 3 | 3 | Add `tests/` pytest suite (in progress) covering contamination, eval safety, dispatch |
| TD-05 | cog/cognitive_engine.py | `plan`/`aplan` enforce epistemic veto but no rate-limit/quota on LLM calls | 2 | 2 | Add token/cost guard + circuit breaker around `llm.py` |
| TD-06 | mcp/integration_tools.py | Blender/Unity handlers shell out; sandboxing is user's responsibility | 2 | 3 | Document sandbox; add optional `MEM20_SANDBOX` wrapper for 2.0 |
| TD-07 | memory_engine/memory.py | `safe_eval_condition` is AST-restricted but re-parses per step; fine for current scale | 1 | 1 | Cache compiled AST per rule if rule count grows |
| TD-08 | deploy | systemd unit has `Restart=always` but no health-based readiness gating | 2 | 1 | Wire `ExecStartPost`/watchdog to `/ready` once durable metrics exist |

## Scalability baseline (Step 10)
- Single MCP process, stdio transport; one client connection. Horizontal scale =
  run N processes behind an MCP proxy (out of scope for 1.0).
- Memory store is append-only JSONL ledger + FAISS index on local disk. Projected
  ceiling for 2.0: ~1M ledger entries before reindex strategy needed.
- World-model simulation is O(steps × rules) in-memory; fine to ~10k rules.

## Platform workstream (runs parallel to product work)
- TD-02 external/vector store evaluation (ADR).
- TD-04 pytest suite + CI.
- Durable metrics sink (TD-01) feeding Step 16 dashboards.
