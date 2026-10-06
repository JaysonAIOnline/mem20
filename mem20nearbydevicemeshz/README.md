# RM-153 — Nearby Device Mesh

**Owner:** Andi  
**Lane:** Device, mobile, enrollment, build, and edge delivery

## Outcome
Discover and combine trusted local devices over short-range and local networks

## Breakthrough
A room of hardware behaves like one cooperative computer

This package implements the locally executable/non-human portion of this Off Record Lab roadmap on a shared, zero-dependency runtime substrate. It includes typed/versioned roadmap validation, SQLite WAL state + event history, resumable/idempotent jobs, cancellation/timeouts/quotas, deterministic recovery, adaptive mode decisions with confidence/alternatives/bottlenecks/explanations, feedback tuning, CLI + typed client + HTTP API + browser command surface + event stream, local/hybrid/cloud peer execution, conflict-safe LWW synchronization, caching, backpressure/failover, metrics, simulator scenarios, benchmark tooling, safety gating, and a rollback manifest.

The domain engine for this package is keyed specifically to RM-153 and produces deterministic executable results for the roadmap's core operation using only local standard-library code. External hardware, proprietary models, production credentials, live third-party services, and deployment authorization are intentionally not fabricated; those remain environment-bound integration points.

## Run
```bash
python run.py inspect
python run.py run '{"text":"demo","cache":false}'
python run.py simulate
python run.py benchmark --runs 5
python run.py serve --port 8765
```

Open `http://127.0.0.1:8765/` for the live command surface.
