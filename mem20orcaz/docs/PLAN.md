# mem20orcaz — full-fidelity cleanroom (phase 19)

**Branding policy (Jayson, 2026-09-10):** every known capability of the absorbed
workflow-orchestrator platform is rebuilt directly INTO mem20
(`/opt/mem20/mem20orcaz`), under **mem20** branding. Zero occurrences of the
old product name in code, docs, paths, or packaging (a single `corporal`-style
reference to the upstream source remains only in this PLAN as provenance). The
upstream repo is the *reference* (cleanroom) — never imported, never vendored,
never pip-installed, never referenced by name.

The orchestrator is built directly into mem20: a pure-stdlib package at
`/opt/mem20/mem20orcaz` (importable `mem20orcaz`), shipping a CLI
(`mem20orcaz <workflow.yaml>`), a YAML-subset loader, runtime agent/node
registries, and an execution engine.

---

## 1. Scope — what was absorbed

Orchestrator composition + runtime execution for deterministic multi-agent
workflows, driven by YAML configuration. All behavior is native: **no**
redis / redis-om / openai / sentence-transformers / fastmcp / fastapi /
pydantic / jinja2 / PyYAML. LLM calls go through the mem20 substrate llm
gateway (fake deterministic gateway provided for offline/CI runs).

## 2. Modules (`mem20orcaz/`)

- `loader.py` — safe YAML-subset parser (block map/seq, flow `[..]`/`{..}`,
  quotes, comments, booleans/numbers/null) + `YAMLLoader` API
  (`load_yaml`, `parse`, `agent_config_map`, `initial_queue`,
  `orchestrator_id`, `validate`). Unsupported syntax raises `ConfigError`.
- `orchestrator.py` — `Orchestrator(id, config=None)` composition
  (workflow + YAML path resolution), `run()`/`arun()` execution loop,
  LLM gateway injection, metrics, trace, memory logger wiring.
- `execution.py` — `QueueProcessor.run(initial_queue, context,
  final_response_provider, metrics)`, `AgentRunner`, `ResponseNormalizer`,
  `ResponseExtractor`, `ContextManager`, `TraceBuilder`, `ParallelExecutor`.
- `agent_factory.py` — `AgentFactory(config_map, registry)` +
  `_instantiate` (injects config/registry/prompt behind `**kwargs`).
- `agents.py` / `nodes.py` — BaseAgent / BaseNode ABCs + registries
  (`AGENT_TYPES`, `NODE_TYPES`; type = class-name lowercased).
- `response_builder.py` — `ResponseBuilder.create_success/error_response`
  (`status` always set; `component_id`-keyed with `agent_id` alias) and
  `from_plain_response` (promotes node control-flow keys to top level).
- `fork_group_manager.py` — `ForkGroupManager` (create/add/track/done).
- `concurrency.py` — `ConcurrencyManager` (semaphore + timeout runner).
- `memory.py` — pure-stdlib in-memory `MemoryLogger` under the
  `memory_manager:{key}` namespace contract with coverage-based search,
  plus `_RedisCompatBase` stubs keeping the backend signature shape.
- `prompt_rendering.py` — `${var}`/`{{ var }}` rendering + `FILTERS`
  (`upper`, `lower`, `strip`, …) and literal-brace handling.
- `registry.py` — `ResourceRegistry` lazy DI (llm/embedding/memory/custom).
- `graph_api.py` — node/edge descriptors + `topological_queue`.
- `cli.py` — `mem20orcaz <workflow.yaml> [--input X] [--outputs]
  [--list-types] [--version]`; fake deterministic llm gateway for offline runs.

## 3. Type registry

- Agents: `binary`, `classification`, `constant`, `counter`, `echo`, `llm`,
  `local_llm`, `memory`, `openai-answer`, `openai-binary`,
  `router`/`routernode`, `validate_and_structure`,
  `validation_and_structuring_agent`.
- Nodes: `failing`(-node), `failover`(-node), `forknode`, `graph-scout`/
  `graph_scout`/`graphscout`, `join`(-node), `loop`(-node/validator),
  `memory_reader`(_node), `memory_writer`(_node), `rag`(-node),
  `router`/`routernode`.

## 4. Key behaviors

- **Fork ⇒ join**: sequential fork executes members, marks the fork-group
  member done in the manager; join proceeds once `is_group_done`.
- **Failover**: primary → fallbacks; runner resolved from
  `context["_runner"]` or the node's `runner`.
- **Memory**: write/read share the `memory_manager:{key}` prefix and
  query-term-coverage relevance (values include key-label tokens).
- **RAG**: reader enriches context from stored docs; response carries
  `hits`; LLM call count recorded in metrics.
- **Traces**: `n_entries` + per-entry `component_type`/`input`/`output`/
  `status`/timing; `metrics` summary has `total_executions`/`by_type`/
  `statuses`.

## 5. Validation (hermetic gate)

- `python -m unittest discover -s tests` — **40/40 OK** (loader incl.
  in-repo 84-file OrKa-example corpus — 84 load, 82 validate, 2 `*_inputs.yml`
  payload files skipped from validation; memory incl. prefix+coverage search;
  prompt rendering; response builder incl. status/extras; factory incl.
  `**kwargs` injection; fork-group tracking; 12 execution E2Es; YAML file
  workflow; CLI; import surface).
- CLI verified: `mem20orcaz --version` → `0.9.17+mem20`; YAML workflow run
  prints final response, execution counts, per-agent outputs.
- Entirely offline/deterministic: no network, no external services.

## 6. Packaging

- `pyproject.toml`: `setuptools>=68`, `requires-python>=3.10`, versions are
  PEP-440 (`0.9.17+mem20`), console script `mem20orcaz = mem20orcaz.cli:main`.
- Installed editable into the shared `/root/.venv`.

## 7. Handoff

Phase 19 complete. Next: `20_secretz` (fresh secrets pass) and
`21_systemz` (full systemd audit + write-up); phase `07_mem20langz` remains
paused pending its de-wiring pass.