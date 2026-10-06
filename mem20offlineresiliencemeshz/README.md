# RM-045 — Offline Resilience Mesh

Outcome: Keep useful services operating during internet or provider outages

Breakthrough: The platform degrades gracefully instead of going dark

Machine-executable local runtime includes versioned state, SQLite WAL persistence, events, SDK CRUD, resumable/idempotent jobs, retries/timeouts/quotas, recovery, `sync` operation logic, decision explanations, feedback, CLI, HTTP console/API, mesh selection/failover, simulator, benchmark, metrics, and opt-in signature mode.
