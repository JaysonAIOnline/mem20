# Prioritization & Themes (Step 12)

Scoring uses **RICE** (Reach × Impact × Confidence ÷ Effort), with Effort in
engineer-weeks. Reach/Impact/Confidence on 1–5.

## Themes (2.0)
- **T1 Trust & Safety** — contamination firewall, eval safety, promotion evidence.
- **T2 Operability** — health/metrics, test suite, deployment hardening.
- **T3 Cognitive Depth** — world-model causal layer, self-model continuity.
- **T4 Ecosystem** — Blender/Unity/Figma integrations, packaging.
- **T5 Experience** — MCP tool discovery, docs, onboarding.

## Scored backlog (representative)

| Epic | Theme | Reach | Impact | Conf | Effort | RICE |
|------|-------|-------|--------|------|--------|------|
| Eval-safety suite (TD-04) | T1/T2 | 5 | 4 | 5 | 2 | 50.0 |
| Durable metrics sink (TD-01) | T2 | 4 | 3 | 4 | 2 | 24.0 |
| pytest suite (TD-04) | T2 | 5 | 4 | 4 | 3 | 26.7 |
| World-model causal `do()`/`counterfactual()` | T3 | 3 | 5 | 3 | 3 | 15.0 |
| Self-model continuity | T3 | 3 | 4 | 3 | 2 | 18.0 |
| External vector store eval (TD-02) | T2 | 2 | 4 | 2 | 4 | 4.0 |
| Blender/Unity sandbox (TD-06) | T4 | 2 | 3 | 3 | 3 | 6.0 |
| Tool-discovery docs | T5 | 4 | 2 | 5 | 1 | 40.0 |

## Out of scope for 2.0 (deferred to 2.1+)
- Multi-process shared vector store (TD-02) — needs ADR + infra.
- LLM cost circuit breaker (TD-05) — depends on provider contracts.
- Figma integration — no spec yet (needs Step 09 benchmarking).

## Sequencing
1. T1/T2 hardening (highest RICE, lowest risk) — Phase 7 close + Steps 10–12.
2. T2 observability (Step 16) — pairs with the live `/metrics`.
3. T3 cognitive depth — `do()`/`counterfactual()` + self-model (already prototyped in engine).
4. T4/T5 — integrations + docs polish near launch.
