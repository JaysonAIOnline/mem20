# Scope & Epic Breakdown (Step 14)

Epics map to the prioritization themes (Step 12) and the existing codebase
workstreams. Each epic lists stories with codebase anchors.

## E1 — Safety & Grounding Hardening (T1)
- S1.1 `safe_eval_condition` AST evaluator + tests — DONE (`memory_engine/memory.py`).
- S1.2 `audit_contamination()` dual-index check — DONE (CLEAN 0.0).
- S1.3 Evidence-based simulated→grounded promotion — DONE.
- S1.4 Regression tests for S1.1–S1.3 — IN PROGRESS (pytest suite).

## E2 — Operability & Observability (T2)
- S2.1 Modular MCP decomposition — DONE (`server.py` + mixins).
- S2.2 Health/metrics endpoint — DONE (`mcp/health.py`, ADR-0003).
- S2.3 Durable metrics sink — TODO (TD-01, Step 16 §2).
- S2.4 pytest suite + CI — IN PROGRESS (TD-04).
- S2.5 systemd readiness gating — TODO (TD-08).

## E3 — Cognitive Depth (T3)
- S3.1 World-model `do()`/`counterfactual()` — PROTOTYPED in engine (`WorldModel`).
- S3.2 Self-model continuity (`SelfModel`) — PROTOTYPED in engine.
- S3.3 Wire S3.1/S3.2 into MCP tools? — **deferred**: user rejected adding new
  MCP tools for 8.1; expose via engine API + dedicated 2.0 tool module only if
  product research (Step 08) validates demand.

## E4 — Integrations (T4)
- S4.1 Blender/Unity handlers — EXISTING (`integration_tools.py`).
- S4.2 Sandbox wrapper — TODO (TD-06).
- S4.3 Figma — TODO pending Step 09 spec.

## E5 — Experience & Docs (T5)
- S5.1 `README.md` architecture/deploy — DONE.
- S5.2 Audit response doc — DONE (`proof/audit_response.md`).
- S5.3 Tool-discovery docs — TODO (high RICE).

## Dependency matrix
E1 → E2 (tests run in CI). E3 independent; E4/E5 can parallelize. E2.3 blocks
Step 16 dashboards. E3.1/3.2 are the only net-new engine behavior for 2.0.

## DoR / DoD
- **Definition of Ready:** metric + test named; owner; no hard-safety regression.
- **Definition of Done:** code + test green in CI; metrics emitted; doc updated.
