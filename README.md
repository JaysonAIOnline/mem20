# mem20

A persistent **memory + cognition substrate** for AI agents, exposed to clients over the
[Model Context Protocol (MCP)](https://modelcontextprotocol.io) as a JSON-RPC 2.0 service on stdio.

mem20 separates **grounded** memory (derived from real observations/events) from **simulated**
memory (hypothetical or model-generated), enforces that separation at the storage layer, and
couples forecasting ("world-model") predictions to observed outcomes so that promotions out of the
simulated partition are evidence-based rather than honor-system.

---

## Architecture

```
                        ┌──────────────────────────────────────────┐
   MCP client  --stdio──▶│  mcp/mcp_server.py  (Mem20MCPServer)     │
   (Hermes, Claude,      │  JSON-RPC 2.0 · ~80 tools · 16 domains   │
    any MCP host)        └───────────────┬──────────────────────────┘
                                         │ calls
                 ┌────────────────────────┼─────────────────────────┐
                 ▼                        ▼                         ▼
        cog/cognitive_engine.py    mem20/mem (store)         roadmaps/*.json
        (plan/chain/reason/        memory.py engine:          (roadmap registry)
         reflect/working memory)   grounded vs simulated,
                                   vector + BM25 indexes,
                                   append-only ledger)
```

- **Transport / protocol:** MCP server (`mcp` package) speaking JSON-RPC 2.0 over stdio.
  `Mem20MCPServer` (in `server.py`) aggregates per-domain mixin classes and dispatches in `_execute_tool()`.
   Tool schemas + handlers live in per-domain modules: `memory_tools.py`, `cognitive_tools.py`, `roadmap_tools.py`,
   `tools/world_tools.py` (world-model/affective/procedural), `tools/blender_tools.py` (OPTIONAL Blender),
   `tools/unity_tools.py` (OPTIONAL Unity), `tools/integration_tools.py` (filesystem + blank template for new
   optional integrations), `tools/a2a_tools.py` (Agent-to-Agent communication), `tools/thought_process.py`
   (reasoning paradigms + cognitive substrate). `mcp_server.py` is a thin entry-point shim preserving the
   systemd unit path.

   **Optional integrations (2.1):** Blender and Unity ship as *separate, pluggable modules*. They require the
   respective external application installed (`blender` on PATH, or `MEM20_BLENDER_EXECUTABLE` / `MEM20_UNITY_EXECUTABLE`);
   when absent, the tools return an informative message instead of failing. See `requirements-optional.txt`.
- **Cognitive layer (`cog/`):** `cognitive_engine.py` wraps an OpenAI-compatible LLM
  (`llm.py`) to provide thought processing, chains, reasoning, planning (`plan`/`aplan`),
  reflection, and working memory. Planning enforces the epistemic veto (see Governance).
- **Memory layer (`mem/` + store engine `memory.py`):** the durable memory engine lives on
  `MEM20_STORE_PATH` (default `~/.mem20/store`). It owns the ledger, the
  vector index (SentenceTransformer embeddings), and the BM25 corpus.
- **Roadmap registry (`roadmaps/`):** JSON files describing multi-phase project plans.
- **Deployment (`systemd/`):** a user service unit runs the MCP server under a virtualenv.

### Tool domains (16)

| Prefix                | Domain                          |
|-----------------------|--------------------------------|
| `memory_*`            | core memory, epistemic, ingest, pins, namespaces, audit |
| `self_model_*`        | agent self-model                |
| `cog_*`               | cognitive processing            |
| `imagination_*`       | counterfactual / generative simulation |
| `theory_of_mind_*`    | perspective simulation          |
| `corrigibility_*`     | shutdown / capability tiers     |
| `roadmap_*`           | roadmap registry                |
| `world_model_*`       | variables, rules, prediction ledger |
| `affective_*`         | values, emotions, goals         |
| `procedural_*`        | skill library                   |
| `fs_*`                | sandboxed filesystem access     |
| `blender_*`           | Blender automation — **OPTIONAL** (needs Blender app; `tools/blender_tools.py`) |
| `unity_*`             | Unity automation — **OPTIONAL** (needs Unity app; `tools/unity_tools.py`) |
| `a2a_*`               | Agent-to-Agent communication    |
| `tot_*`               | Tree-of-Thoughts reasoning      |
| `cognitive_substrate` | 28-paradigm reasoning framework |

#### A2A tools (`mcp/tools/a2a_tools.py`)

Agent-to-Agent communication — lets bots discover peers, send tasks, and orchestrate fan-out.

| Tool | Description |
|------|-------------|
| `a2a_list` | List all configured A2A peer agents and their status |
| `a2a_call` | Send a natural-language task to a remote A2A agent |
| `a2a_discover` | Fetch and summarize a peer agent's Agent Card (capabilities, status) |
| `a2a_history` | Recall a persisted A2A conversation transcript by context ID |
| `a2a_orchestrate` | Fan-out a task to multiple peer agents by capability |

#### Thought process tools (`mcp/tools/thought_process.py`)

Reasoning paradigms — structured approaches to complex problems.

| Tool | Description |
|------|-------------|
| `tot_reason` | Tree-of-Thoughts: explore multiple reasoning paths, evaluate, select best |
| `tot_modeling` | Specialized ToT for 3D modeling decisions |
| `tot_diagnose` | Specialized ToT for diagnosing issues (root-cause exploration) |
| `reflexion` | Reflect on failures, extract lessons, store to memory |
| `least_to_most` | Decompose complex problems from simplest to hardest |
| `react_reason` | Interleave reasoning with tool calls (Think → Act → Observe) |
| `beam_search` | Maintain top-K reasoning paths at each step |
| `cognitive_substrate` | Invoke a specific paradigm from the 28-paradigm framework |
| `get_cognitive_tree_state` | Retrieve persistent ToT telemetry for a session |

---

## Memory Model

mem20 keeps two logical partitions:

- **Grounded memory** — facts derived from real observations, user statements, or events.
- **Simulated memory** — hypotheticals, imagined scenarios, counterfactuals, or model output.

Hard invariants enforced by the store engine:

1. **Indexes are grounded-only.** `_add_to_vector_index()` and `_add_to_bm25_index()` call
   `_assert_grounded()`; a simulated record reaching either index raises immediately. This is the
   lowest write path, so contamination is impossible regardless of which tool invoked it.
2. **`remember()` is grounded-only by default** (`_allow_simulated=False`). Simulated content uses
   its own path (`remember_simulated` / `memory_simulate_store`).
3. **Append-only ledger with validated tags.** Every ledger entry carries `origin`
   (e.g. `user`, `tool`, `simulated`) and `store` (`memory`/`imagined`). `_validate_partition_tags()`
   rejects mismatched `origin`/`store` pairs and `action`/partition mismatches at the lowest append
   path, so the partition boundary is asserted, not merely conventional.
4. **Promotion is evidence-based.** `promote_simulated_to_grounded()` accepts a simulated record
   only when it carries `prediction_error_evidence` that is **either**:
   - a linked prior prediction resolved in its favor
     (`world_model_resolve_prediction(prediction_id, observed_outcome, in_favor=True)` with a
     matching outcome), **or**
   - vouched for by a registered external verifier (`PREDICTION_ERROR_VERIFIER` hook).
   Free-text self-assertion is rejected.
5. **Epistemic status is authoritative on the record.** `set_epistemic_status()` stamps the status
   directly onto the original grounded ledger line and the deep-store markdown header, so readers
   see the canonical value without event-sourced reconstruction. `memory_epistemic_veto` quarantines
   records below a trust threshold.

### Store layout (`MEM20_STORE_PATH`)

```
store/
  memory.py                 # the engine
  ledger.jsonl              # append-only operation log (origin/store tagged)
  embeddings.npy / index    # vector index (grounded only)
  bm25_corpus.json          # BM25 corpus (grounded only)
  records/<id>.md           # deep-store markdown (header carries epistemic_status)
  simulated/                # simulated partition (never indexed)
```

---

## Cognitive Substrate (28 Paradigms)

The cognitive substrate is a 28-paradigm reasoning framework organized in 5 categories.
Each paradigm is a structured lens for evaluating decisions, code, or plans.

### Primary Cognitive Foundations
1. **Premise Validation** — List 3 unstated assumptions, evaluate veracity
2. **State Estimation** — Identify active goal, constraints, system state
3. **Adversarial Falsification** — Propose thesis, attack it, harden synthesis
4. **Depth-First Branching** — Generate pathways, score confidence, select best
5. **Epistemic Humility Map** — Separate facts, inferences, and speculation
6. **Opportunity Cost Calculation** — Heavy footprint vs. minimalist 80/20 path
7. **Inversion Principle** — Simulate catastrophic failure, add mitigations
8. **Semantic Compression** — Feynman analogy test, verify structural purity

### Metacognition & Processing
9. **Explanatory Depth Map** — Surface intent vs. underlying primitives
10. **Cognitive Dissonance Audit** — Find conflicting constraints, resolve
11. **Dialectical Inquiry** — Socratic self-critique, rebuttal, adaptation
12. **Premature Convergence Brake** — Discard first instinct, explore orthogonal paths
13. **Semantic Drift Sentinel** — Verify root goal alignment, track drift %

### Defensive Engineering
14. **Idempotency Audit** — Blast radius, safe-to-re-run proof
15. **Graceful Degradation** — Failure triggers, low-power fallback
16. **Boundary Stress Testing** — Null/zero/max input behavior
17. **Zero Trust Security** — Assumed exploit, mitigation shield
18. **State Invariant Enforcement** — Immutable rule, validation step

### Resource Management
19. **Complexity Cost Analysis** — Big O, scalability bottleneck
20. **Lazy Evaluation** — Deferred computations
21. **Dependency Minimization** — External requirements, vanilla fallback
22. **Bottleneck Prediction** — Highest latency line, optimization
23. **Context Window Budgeting** — Token weight, compression strategy

### Human Utility
24. **Cognitive Load Minimization** — 10-second review summary
25. **Progressive Disclosure** — Executive summary + hidden details
26. **Idiomatic Purity** — Style guide, anti-patterns evaded
27. **Premise Correction Loop** — User instruction flaws, proposed correction
28. **Intent Alignment Verification** — Final checklist of resolved goals

### Cross-Session Tree-of-Thought Learning

The ToT state is persisted to `tot_state.db` (SQLite) so reasoning survives crashes:
- **Persistent paths** — active reasoning branches stored across sessions
- **Pruned branch memory** — dead ends recorded to avoid re-exploration
- **Historical lessons** — `get_cognitive_tree_state` retrieves telemetry for evolutionary learning
- **5-key telemetry schema** — foundations / metacognition / defensive / resource / utility

---

## Roadmap Registry

Roadmaps are JSON files in `roadmaps/`. Schema:

```json
{
  "name": "mem20_build",
  "description": "Build mem20 from scratch",
  "phases": [
    { "name": "mcp",        "status": "planned", "notes": "" },
    { "name": "memory",     "status": "planned", "notes": "" },
    { "name": "cognitive",   "status": "planned", "notes": "" },
    { "name": "production",  "status": "planned", "notes": "" }
  ],
  "created": "1787804510.8459408"
}
```

Tools: `roadmap_create`, `roadmap_list`, `roadmap_get`, `roadmap_update_phase`
(update a phase `status` to `planned`/`in_progress`/`done`/`blocked`).

---

## Governance & Contamination Controls

These are the safeguards that make the grounded/simulated split real, not advisory:

- **Contamination guards** — `_assert_grounded()` at the vector/BM25 write paths.
- **Origin/store assertion** — `_validate_partition_tags()` at the ledger append path.
- **Epistemic veto / clearance** — `require_epistemic_clearance()` plus the plan-execution guard
  `run_plan_execution_guard()`. The cognitive engine enforces this on `plan`/`aplan`, so a plan
  built on simulated or low-trust premises cannot execute.
- **Audit** — `memory_audit_contamination()` (`audit_contamination()`) inspects **both** the grounded
  store and the BM25 corpus for simulated records, returning `contamination_rate`, `violations`, and
  `violations_simulated_in_bm25_corpus`. A clean system reports rate `0.0`.
- **Prediction ledger** — `world_model_record_prediction` / `world_model_resolve_prediction` couple a
  forecast to its observed outcome, feeding the promotion gate and prediction-accuracy metrics so the
  system can measure how often its simulations are later borne out.

---

## Deployment

The server runs as a systemd user service. A portable template ships at
`systemd/mem20.service.template`; the easiest path is the installer:

```bash
sudo ./install.sh --user <user> --dir /opt/mem20
# or, for this box only:
#   python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
#   MEM20_STORE_PATH=/path/to/store .venv/bin/python mcp/mcp_server.py
```

`install.sh` creates the venv, installs `requirements.txt`, generates the unit from the template
(filling `__MEM20_USER__` / `__MEM20_WORKDIR__` / `__MEM20_VENV_PYTHON__` / `__MEM20_STORE_PATH__`),
and enables + starts it. After start, probe health:

```bash
curl http://localhost:8080/health   # → {"status":"ok", ...}
curl http://localhost:8080/metrics  # → tool counters + contamination_rate
```

Point an MCP host at the server (stdio).

---

## Installation

mem20 is distributed through four channels. All of them run the **same**
server (`mcp/mcp_server.py`): an MCP stdio JSON-RPC server plus an HTTP health endpoint
on `:8080` (`/health`, `/ready`, `/metrics`). Pick whichever fits your environment.

### 1. pip (Python)

```bash
pip install .                 # builds the wheel, installs the `mem20-mcp` command
mem20-mcp                     # starts the MCP server + :8080 health endpoint
# or run the repo directly (always supported, never changes):
#   python mcp/mcp_server.py
```

`mem20-mcp` is a thin launcher (`launcher.py`) that locates the bundled `mcp/`
directory and runs it as a script — so `from mcp.server import Server` (the SDK)
is never shadowed. Override the port with `MEM20_HEALTH_PORT`.

### 2. Docker

```bash
docker build -t mem20 .
docker run -p 8080:8080 -e MEM20_HEALTH_PORT=8080 -v mem20-store:/data mem20
# or with compose (persists the store in a named volume):
docker compose up -d
curl http://localhost:8080/health
```

The image runs `python mcp/mcp_server.py` as the canonical entrypoint (health on `:8080`).

### 3. npm (web dashboard)

The `dashboard/` app (Vite + React) shows live server status and the memory
store. It talks to the **optional** HTTP bridge (`bridge/server.py`), which
proxies `/health`, `/ready`, `/metrics` and adds `/api/memory`, `/api/recall`.

```bash
# optional bridge (completely separate from the MCP server):
pip install fastapi uvicorn httpx
python bridge/server.py                 # :8000

# dashboard:
cd dashboard
npm install
npm run build                           # → dashboard/dist/ (static)
npx serve dashboard/dist                # or any static server
# dev mode with hot reload:
npm run dev                             # http://localhost:5173
```

### 4. apt (.deb)

```bash
make deb                                # → packaging/deb/mem20_*.deb
sudo dpkg -i packaging/deb/mem20_*.deb  # installs venv + systemd unit + health probe
sudo systemctl status mem20             # enabled + started by postinst
mem20-health                            # probe /health
```

See `packaging/README.md` for how each channel is built and why `mcp/` is kept
out of the Python import path (shadowing the `mcp` SDK would break the server).

---

## Dependencies

Install core deps from `requirements.txt` (pinned). `requirements-optional.txt` documents the
**optional external integrations** (Blender, Unity) which are applications, not pip packages.

Core (Python, pip) — `requirements.txt`:

- `mcp` — MCP server framework (also provides `mcp_types`).
- `sentence-transformers` — `SentenceTransformer` (embeddings) and `CrossEncoder` (reranking).
- `numpy` — vector math.
- `faiss-cpu` — vector index.
- `pydantic`, `anyio` — MCP transport.
- LLM access — `cog/` talks to an OpenAI-compatible chat-completions endpoint via `llm.py`
  (default NVIDIA `integrate.api.nvidia.com/v1`); requires an API key, no SDK beyond `requests`.

Optional / integration-only (external applications — degrade gracefully when absent):

- **Blender** — install Blender; ensure `blender` is on PATH or set `MEM20_BLENDER_EXECUTABLE`. (`blender_*` tools.)
- **Unity** — install the Unity Editor; set `MEM20_UNITY_EXECUTABLE`. (`unity_build_project`, `unity_run_test`.)

Install core:

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
# or, with dev + integration extras:
#   .venv/bin/pip install -e ".[dev]"
```

---

## Configuration

Environment variables:

| Variable                | Default                              | Purpose                                   |
|-------------------------|--------------------------------------|-------------------------------------------|
| `MEM20_STORE_PATH`      | `~/.mem20/store`                     | Memory engine module + store location     |
| `MEM20_COG_PATH`        | (mem20 `cog/` dir)                   | Cognitive engine location                 |
| `MEM20_LLM_BASE_URL`    | `https://integrate.api.nvidia.com/v1`| LLM chat-completions base URL             |
| `MEM20_LLM_MODEL`       | (project default)                    | Model name                                |
| `NVAPI_KEY` / `NVIDIA_API_KEY` / `MEM20_LLM_API_KEY` | —      | LLM bearer token (required)               |
| `MEM20_ENV_FILE`        | —                                    | Optional `.env` to load API keys from     |

---

## Development / Onboarding

- **Engine logic** lives in the store engine (`memory.py` on `MEM20_STORE_PATH`), not in the MCP
  server. MCP tools are thin handlers that call engine functions.
- **Adding a tool:** pick the domain module for your tool, add the
  `self.tools["name"] = mt.Tool(...)` block to that module's `register_<domain>_tools()` method, and add
  a dispatch branch + a `_name(self, args)` handler in the same mixin. Keep engine-side invariants
  (grounded/simulated, ledger tags) intact. Run `verification/verify_refactor.py` after changes.
- **Adding an OPTIONAL integration (2.1):** create `mcp/tools/<name>_tools.py` with a `<Name>ToolsMixin`
  (register + handlers), guard any external executable with a graceful check (see
  `UnityToolsMixin._resolve_optional_executable`), add the mixin to `Mem20MCPServer`'s bases in `server.py`,
  and call `self.register_<name>_tools()` in `_setup_tools()`. The blank scaffold is
  `IntegrationToolsMixin.register_integration_template()`.
- **Adding a reasoning paradigm:** add the tool to `tools/thought_process.py`, create the handler,
  and register the Pydantic model in `resources/cognitive_substrate.py` + the JSON schema in
  `resources/cognitive_substrate_schema.json`.
- **Verify governance** after changes: call `memory_audit_contamination()` and confirm
  `contamination_rate == 0.0`; ensure no simulated record reaches the vector/BM25 indexes.
- **Roadmaps** are plain JSON in `roadmaps/`; edit via the `roadmap_*` tools or directly.

> **2.1 freeze:** the modular integration refactor (Blender/Unity as separate optional modules) is the
> 2.1 increment. Code is frozen here until the GitHub release is complete; no further code changes until then.
