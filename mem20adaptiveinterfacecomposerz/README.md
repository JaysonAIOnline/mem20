# RM-003 — Adaptive Interface Composer

Self-contained implementation of the non-human/executable portions of Off Record Lab RM-003.

It generates task-specific interfaces from typed capability metadata and user intent, and rebuilds the interface as the job state changes. It includes persistent SQLite state/event history, CRUD APIs, Python SDK, resumable jobs, idempotency, retries/timeouts/quotas, simulator, semantic + constraint composition, telemetry/cost-aware scheduling, feedback tuning with immutable hard safety boundaries, confidence/alternatives/bottlenecks/explanations, adaptive web desktop + command palette + event inspector, CLI, SSE progress events, local/hybrid/cloud execution, peer discovery, deterministic conflict reconciliation, cache/backpressure/failover, benchmark tooling, metrics and rollback-safe release artifacts.

## Run
```bash
python -m pip install .
freestack-interface --db demo.db register examples/search_capability.json
freestack-interface --db demo.db compose "search deployment notes"
freestack-interface --db demo.db serve --port 8783
```

Production environment endpoints/auth, production capability catalog, trust policy, deployment targets and human approval policy are deliberately not invented.
