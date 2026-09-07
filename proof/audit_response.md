# Audit Response — Static Code Review (8.2 / 10)

This document maps each finding from the static code review to its resolution in this build.

## High-Priority Findings

### Finding 1 — Dynamic `eval()` in the memory engine (Medium)

**Location (before):** `memory.py`, `WorldModel.simulate_step` — `eval(rule["condition"], ...)`

**Resolution:** Replaced with a safe, AST-restricted evaluator.

- Added `_SafeConditionEval` (a node visitor) and `safe_eval_condition(expr, namespace)` in `memory.py`.
- Only a boolean/arithmetic subset is permitted: `Name`, `Constant`, `BoolOp`
  (`and`/`or`), `UnaryOp` (`not`/`-`/`+`), `BinOp` (`+ - * / % // **`),
  `Compare` (`== != < <= > >= in not in`). Any `Call`, `Attribute`, `Subscript`,
  or other node is rejected and the condition evaluates to `False`.
- This removes the only dynamic-code-execution path in the codebase.

**Verification:**
- Valid rule `temperature > 15` with effect `{'temperature': 5.0}` fires each
  step (20 → 35 over 3 steps).
- Arithmetic/boolean rule `a + b * 2 >= 8 and a < 10` fires correctly.
- Malicious rule `__import__("os").system("echo pwned")` is rejected; the
  variable is **not** mutated (no code execution).
- `grep -nE 'eval\(' memory.py` returns only docstring/comment mentions.

### Finding 2 — Large MCP server monolith (Medium)

**Location (before):** `mcp/mcp_server.py` (~4,848 lines, 97 tools, 13 domains)

**Resolution:** Decomposed into per-domain modules with identical behavior
(method and registration blocks sliced verbatim; only location changed).

| File                              | Lines | Contents                                  |
|-----------------------------------|-------|-------------------------------------------|
| `mcp/server.py`                   | 722   | `Mem20MCPServer` (aggregates mixins) + dispatch `_execute_tool` + `run`/`main` |
| `mcp/memory_tools.py`             | 1,750 | `memory_*` + `self_model_*` (39 tools)    |
| `mcp/cognitive_tools.py`          | 825   | `cog_*` + `imagination_*` + `theory_of_mind_*` + `corrigibility_*` (19) |
| `mcp/roadmap_tools.py`            | 144   | `roadmap_*` (4)                            |
| `mcp/tools/world_tools.py`        | 645   | `world_model_*` + `affective_*` + `procedural_*` (20) |
| `mcp/tools/integration_tools.py`  | 707   | `fs_*` + `blender_*` + `unity_*` (15)      |
| `mcp/mcp_server.py`               | 10    | thin entry-point shim (systemd `ExecStart`) |
| `mcp/tools/`, `mcp/resources/`, `mcp/prompts/` | — | package markers |

- `Mem20MCPServer` now inherits `MemoryToolsMixin, CognitiveToolsMixin,
  RoadmapToolsMixin, WorldToolsMixin, IntegrationToolsMixin`.
- `_setup_tools()` delegates to `register_<domain>_tools()` on each mixin.
- Dispatch stays in `server.py` and calls `self._<tool>(...)`.

**Verification:** `verification/verify_refactor.py` (static, no runtime deps)
and a live import both confirm: **97 registrations, 97 handlers, 0 dispatch
tools missing a handler**. No logic was altered.

### Finding 3 — External process execution (Low)

**Resolution:** No change required. Confirmed all `subprocess` calls use
argument lists (no `shell=True`, no `os.system()`), and external operations
(Blender/Unity build/test) carry timeouts. This already eliminates the common
command-injection class.

## Lower-Priority Recommendations

| Recommendation            | Status                                                     |
|---------------------------|------------------------------------------------------------|
| Documentation debt        | **Done** — `README.md` now covers architecture, deployment, dependencies, roadmap registry, memory model, governance. |
| Automated test suite      | Partial — `verification/` scripts present (static refactor check + memory contamination proof). A `pytest` suite is recommended next. |
| Structured logging        | Not yet implemented — recommend `logging.getLogger(...)` with JSON logs + request IDs. |
| Metrics / health endpoint | **Done** — `mcp/health.py` exposes `/health`, `/ready`, `/metrics` (stdlib `http.server`, daemon thread, non-blocking, bind-failure-safe). `server.py` now tracks request/error counters and configures `logging`. |

## Overall

The two Medium findings (dynamic `eval`, monolith) are fully resolved. The
codebase is in a stronger maintainability posture (no single file exceeds ~1,800
lines) while preserving verified runtime behavior.
