# Changelog

All notable changes to mem20 are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/).

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
