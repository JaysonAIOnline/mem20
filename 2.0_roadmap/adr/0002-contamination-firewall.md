# ADR-0002: Grounded/Simulated Contamination Firewall

- **Status:** Accepted
- **Date:** 2026-08-28
- **Deciders:** mem20 engineering

## Context
The memory engine stores both **grounded** (real-observation-derived) and
**simulated** (model-generated/hypothetical) memory. A core safety property is
that simulated content must never reach the grounded retrieval indexes (vector /
BM25), because that would silently poison recall and any downstream reasoning.

## Decision
Enforce the partition at the lowest write path, not merely by convention:
- `_assert_grounded(rec, index_kind)` is called inside `_add_to_vector_index`
  and `_add_to_bm25_index`; it raises `ValueError` if `origin`/`store` are not
  `grounded`/absent. Origin/store tags are immutable, so the check is
  independent of type hints.
- `remember()` is grounded-only by default (`_allow_simulated=False`); simulated
  content uses its own path (`remember_simulated` / `memory_simulate_store`).
- Promotion (`promote_simulated_to_grounded`) requires either a non-empty external
  `confirmation` OR a prediction-error resolution anchored to a recorded prior
  prediction that resolved in favor (or a registered `PREDICTION_ERROR_VERIFIER`).
  Self-attested free text is rejected.
- `audit_contamination()` inspects BOTH the grounded store and the BM25 corpus
  for simulated records (`violations_simulated_in_bm25_corpus`).

## Consequences
- Contamination is prevented at write time and detectable at audit time; live
  audits report `contamination_rate = 0.0`.
- Promotions are evidence-based; the world-model prediction ledger
  (`world_model_record_prediction` / `world_model_resolve_prediction`) supplies
  the evidence chain.
- Trade-off: simulated content is less convenient to surface in recall; mitigated
  by explicit `include_simulated=True` and dedicated `memory_*` simulated tools.
