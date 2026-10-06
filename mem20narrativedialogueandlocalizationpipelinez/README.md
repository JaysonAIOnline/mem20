# RM-244 — Narrative, Dialogue and Localization Pipeline

**Outcome:** Drive story state, dialogue graphs, translation, timing, and engine reintegration from one runtime

**Breakthrough:** A game can speak many languages without breaking logic or character identity

This package is the machine-executable local implementation derived from the supplied Off Record Lab roadmap. It includes versioned typed state, SQLite WAL persistence, event history/snapshots, SDK CRUD/subscription, resumable idempotent jobs, cancellation, retries/timeouts/quotas/backpressure, deterministic replica reconciliation, local/hybrid/cloud placement/failover, roadmap-specific `graph` logic, decision confidence/explanations, feedback, CLI, HTTP console/API, safety guards, simulator, benchmark/metrics, and rollback-capable installer.

Named live product surfaces, real provider/device credentials, production traffic, and governed FreeStack deployment remain target-environment integration and are not claimed complete.
