# ADR-0001: Modular MCP Server Decomposition

- **Status:** Accepted
- **Date:** 2026-08-28
- **Deciders:** mem20 engineering

## Context
`mcp/mcp_server.py` had grown to ~4,848 lines containing 97 tools across 13
domains. The static review (8.2/10) flagged this as a maintainability risk
(regression risk, onboarding difficulty, hidden coupling). A single large file
also makes conflict resolution and review harder for a small team.

## Decision
Decompose the monolith into `server.py` (the `Mem20MCPServer` aggregator +
dispatch `_execute_tool` + `run`/`main`) and per-domain mixin modules:
`memory_tools.py`, `cognitive_tools.py`, `roadmap_tools.py`,
`tools/world_tools.py` (world-model/affective/procedural),
`tools/integration_tools.py` (fs/blender/unity). `mcp_server.py` becomes a
thin entry-point shim preserving the systemd `ExecStart` path. `mcp/health.py`
holds the operational HTTP endpoint. `tools/`, `resources/`, `prompts/` are
package markers.

Tool schemas and handlers are sliced verbatim — behavior is unchanged.
`Mem20MCPServer` inherits the five mixins; `_setup_tools()` delegates to
`register_<domain>_tools()`.

## Consequences
- No single file exceeds ~1,800 lines (largest is `memory_tools.py` at 1,750).
- Adding a tool means editing one domain module, not a 4.8k-line file.
- 97 tools / 97 handlers preserved; verified by `verification/verify_refactor.py`
  and a live import (0 dispatch tools missing a handler).
- Trade-off: cross-domain call graphs now span modules; mitigated by the shared
  `Mem20MCPServer` base and `self.*` dispatch.
