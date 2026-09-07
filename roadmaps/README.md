# Roadmaps Registry

All roadmaps for mem20-managed projects. Each roadmap tracks phases from concept through completion.

## Status Key
- completed — phase done
- in_progress — actively working on it
- planned — not started yet
- blocked — blocked by dependency

---

## Roadmap Index

| Roadmap | File | Status | Phases | Docs |
|---------|------|--------|--------|------|
| **mem20_build** | `mem20_build.json` | ALL COMPLETE | 6/6 | `/opt/mem20/docs/` (6 files, 185KB) |
| **ags_os** | `ags_os.json` | Phase 1 done, NOT approved | 1/11 completed | `/opt/ags-os/docs/` (8 files, 56KB) |
| **altimator** | `altimator.json` | Phase 1-3 done | 3/9 completed | `/opt/altimator/docs/` (3 files, 64KB) |
| **oreo_language** | `oreo_language.json` | Phase 1-3 done | 3/8 completed | `/opt/oreo/docs/` (7 files, 87KB) |
| **unity_games** | `unity_games.json` | Phase 1-2 done | 2/9 completed | `/opt/unity/docs/` (1 file) |
| **unity_games_full** | `unity_games_full.json` | Phase 1-2 done | 4 submaps | Same as unity_games |
| **fleetwide_mem20** | `fleetwide_mem20.json` | Phase 1-2 done | 2/5 completed | N/A |
| **fleetwide_rules** | `fleetwide_rules.json` | Enforcement ongoing | 0/6 completed | N/A |
| **kanban_integration** | `kanban_integration.json` | Phase 1 done | 1/5 completed | N/A |
| **a2a_setup** | `a2a_setup.json` | Phase 1 in progress | 0/6 completed | N/A |

---

## Roadmap Details

### mem20_build — Build mem20 from scratch
**Status:** ALL PHASES COMPLETED (production since Aug 2026)

| Phase | Status | Notes |
|-------|--------|-------|
| mcp | completed | MCP server at `/home/jayson/mem20/mcp/server.py` with 111 tools |
| memory | completed | Memory engine at `/home/jayson/mem20/memory.py` |
| cognitive | completed | Cognitive engine at `/home/jayson/mem20/cog/cognitive_engine.py` |
| roadmap | completed | Roadmap system at `/home/jayson/mem20/mcp/roadmap_tools.py` |
| hermes_integration | completed | Integrated into Hermes Agent via MCP |
| production | completed | Running since August 2026, 57/81 tests passing |

---

### ags_os — Autonomous Game Studio OS
**Status:** Phase 1 COMPLETED — NOT YET APPROVED TO BUILD

| Phase | Status | Notes |
|-------|--------|-------|
| 1: Design review | completed | Architecture validated, documented in `/opt/ags-os/docs/` |
| 2: Schema fix | blocked | `05_hermes_router.py` queries table that `04_kernel` never creates |
| 3-11: Box A/B, SQLite ToT, Quest 3 | planned | Awaiting approval |

---

### altimator — Altimator Service Bay v2
**Status:** Phases 1-3 COMPLETED, Phase 4 in progress

Interactive 3D Nissan Altima service bay web app (React + TanStack Router + three.js).

| Phase | Status | Notes |
|-------|--------|-------|
| 1: App scaffold | completed | React + TanStack Router routing |
| 2: GLB loading | completed | 260+ parts loaded |
| 3: Asset path fix | completed | BASE path corrected |
| 4: Interactive removal | in_progress | Per-part explosion/removal |
| 5-9: UI, perf, multi-car, AR/VR | planned | Future features |

---

### oreo_language — OREO Visual-First NL-First Programming Language
**Status:** Phases 1-3 COMPLETED, Phases 4-8 in progress

| Phase | Status | Notes |
|-------|--------|-------|
| 1: Research | completed | Neo4j, Graph-Native Programming sources |
| 2: Spec | completed | `/home/jayson/OREO/IDE/spec/OREO_LANGUAGE_SPEC.md` |
| 3: Parser | completed | 20+ modules, GraphLang-based |
| 4: Runtime | in_progress | Compiler, interpreter, memory |
| 5: Visual editor | in_progress | Talk+draw web editor |
| 6: AI integration | in_progress | HybridParser with LLM fallback |
| 7: Test harness | in_progress | Property tests, fuzzing, model checking |
| 8: Docs | in_progress | Full language guides pending |

---

### unity_games_full — Unity Games (with submaps)
**Status:** Phases 1-2 COMPLETED, Phases 3-5 in progress

| Submap | Location | Status |
|--------|----------|--------|
| VRTestProject | `/home/jayson/VRTestProject` | Phase 1 done |
| VRTestProject2 | `/home/jayson/VRTestProject2` | Phase 1 done |
| TheUnreliableProphecy | `/home/jayson/Desktop/.../engine_project` | v0.5.0 vertical slice done |
| Blender Pipeline | `/home/jayson/glb/` | Phases 1-2 done |

---

### fleetwide_mem20 — Fleetwide Mem20 Rollout
**Status:** Phases 1-2 COMPLETED, Phase 3 in progress

| Phase | Status | Notes |
|-------|--------|-------|
| 1: Rename releasecoach→coach | completed | Directory + SOUL header updated |
| 2: Add mem20 MCP to all profiles | completed | 13 profiles updated |
| 3: Isolated namespaces | in_progress | Per-bot namespace creation |
| 4: Decision persistence enforcement | planned | Fleetwide rule |
| 5: Crash recovery test | planned | Verify resume without session search |

---

### fleetwide_rules — Fleetwide Rules Enforcement
**Status:** All phases in planning/enforcement stage

Rules defined in SOUL.md: decision persistence, fail log review, advice implementation, A2A, bot chain hierarchy.

---

### kanban_integration — Kanban Board Integration
**Status:** Phase 1 COMPLETED, Phase 2 in progress

| Phase | Status | Notes |
|-------|--------|-------|
| 1: Audit kanban-mcp code | completed | `/home/jayson/mem20/kanban-mcp/` audited |
| 2: Integrate with mem20 roadmaps | in_progress | Auto-sync phases to cards |
| 3-5: CLI, dashboard, monitoring | planned | Future features |

---

### a2a_setup — A2A Inter-Bot Communication
**Status:** ONGOING OPERATIONAL CONCERN (not a one-time project)

| Phase | Status | Notes |
|-------|--------|-------|
| 1: Audit A2A listeners | in_progress | Checking all profiles |
| 2: Standardize port config | planned | Fix port conflicts |
| 3: Agent auto-discovery | planned | Health checking |
| 4: Message persistence | planned | Replay capability |
| 5: Monitoring & alerting | planned | Reliability monitoring |
| 6: Troubleshooting runbook | planned | Documentation |

---

## Retroactive Audit Standard

Each roadmap has a `retroactive_audit` object added after phases are completed:

```json
{
  "retroactive_audit": {
    "completion_date": "2026-09-06",
    "completion_status": "phase_1_2_completed",
    "notes": "What was built, test results, current state"
  }
}
```

This ensures every completed phase is documented with what actually happened, not just what was planned.

---

Last updated: 2026-09-06
