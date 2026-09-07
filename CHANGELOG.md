# Changelog

All notable changes to mem20 are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/).

## [2.2.0-dev] — 2026-09-04 (cognitive substrate + A2A tools)

2.2 is the "cognitive substrate + A2A inter-bot communication" increment.

### Added
- **28-layer cognitive substrate** — 5-category reasoning framework with JSON schema + Pydantic models
  (`mcp/resources/cognitive_substrate.py`, `mcp/resources/cognitive_substrate_schema.json`).
- **Thought process tools** (`mcp/tools/thought_process.py`) — ToT, Reflexion, Least-to-Most, ReAct,
  Beam Search, plus `cognitive_substrate` paradigm invoker and `get_cognitive_tree_state` telemetry query.
- **A2A tools** (`mcp/tools/a2a_tools.py`) — `a2a_list`, `a2a_call`, `a2a_discover`, `a2a_history`,
  `a2a_orchestrate` for agent-to-agent communication.
- **Cross-session Tree-of-Thought learning** — persistent ToT state via SQLite (`tot_state.db`),
  evolutionary historical lesson retrieval, 5-key compressed telemetry schema.
- **Server routing** updated to include `A2AToolsMixin` and `ThoughtProcessMixin`.
- **Fleetwide Mem20 + A2A Setup roadmap** (`roadmaps/Fleetwide Mem20 + A2A Setup.json`).
- **Test suite** (`test/`) — comprehensive + extreme test coverage for all cognitive tools.

### Changed
- Tool domain count: 13 → 16 (added `a2a_*`, `tot_*`, `cognitive_substrate`).
- Total tools: ~80 → ~95.
- README.md fully updated with new tool domains, A2A tools table, thought process tools table,
  and cognitive substrate documentation.

## [2.1.0-rc2] — 2026-08-28 (frozen; QA audit → GitHub release)

2.1 is the "pluggable integrations + standalone packaging" increment. Code is
frozen here until the GitHub release is cut.

### Added
- **Pluggable integrations:** Blender and Unity ship as separate optional modules
  (`mcp/tools/blender_tools.py`, `mcp/tools/unity_tools.py`). Each degrades
  gracefully (informative message) when the external application is absent
  (`MEM20_BLENDER_EXECUTABLE` / `MEM20_UNITY_EXECUTABLE`, or on PATH).
- Blank integration template: `IntegrationToolsMixin.register_integration_template()`
  documents how to add a new optional integration (e.g., Figma).
- **Standalone packaging:** `requirements.txt` (pinned core deps),
  `requirements-optional.txt` (external-app integrations), `pyproject.toml`,
  `systemd/mem20.service.template`, and `install.sh` (venv + deps + unit generation).
- `LICENSE` (MIT), `.gitignore`, `CHANGELOG.md`.
- Step 16 instrumentation: `/metrics` exposes an event taxonomy and per-tool
  counters, plus cached `contamination_rate` / `grounding_coverage`.
- pytest suite (`tests/`) covering contamination firewall, eval safety, dispatch, metrics.
- 2.0 roadmap deliverables (`2.0_roadmap/`) and a human execution package.

### Changed
- Hard-coded `/home/jayson/...` and `/root/.hermes/...` defaults replaced with
  env-driven / `~`-relative defaults (`MEM20_STORE_PATH`, `MEM20_COG_PATH`,
  `MEM20_ROADMAPS_DIR`, `MEM20_BLENDER_WORKDIR`, `MEM20_ENGINE_SRC`).
- Engine brought into the repo as `memory_engine/` (code only; no user data).

### Fixed
- `eval()` replaced with `safe_eval_condition` (AST-restricted) for world-model rules.
- Contamination firewall: simulated records cannot reach grounded/BM25 indexes;
  `audit_contamination()` reports `contamination_rate == 0.0`.

## [2.0.0] — hardening baseline
- Phase 7 hardening, modular MCP decomposition (97 tools across 13 domains),
  health endpoint, audit response.

## [1.0.0] — initial release
