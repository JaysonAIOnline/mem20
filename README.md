<p align="center">
  <img src="https://img.shields.io/badge/mem20-v2.1--rc2-6366f1?style=for-the-badge&logo=github" alt="mem20 v2.1-rc2">
</p>
<p align="center">
  <strong>A persistent memory + cognition substrate for AI agents.</strong>
</p>
<p align="center">
  <a href="https://mem20.jaysonai.online"><img src="https://img.shields.io/badge/Website-mem20.jaysonai.online-FFD700?style=for-the-badge" alt="Website"></a>
  <a href="https://github.com/JaysonAIOnline/mem20/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License: MIT"></a>
  <a href="https://github.com/JaysonAIOnline/mem20/actions"><img src="https://img.shields.io/github/actions/workflow/status/JaysonAIOnline/mem20/ci.yml?style=for-the-badge" alt="CI"></a>
  <a href="https://github.com/JaysonAIOnline/mem20/releases"><img src="https://img.shields.io/github/v/release/JaysonAIOnline/mem20?style=for-the-badge" alt="Release"></a>
</p>

<p align="center">
  <a href="README.md">English</a> | <a href="#documentation">Docs</a> | <a href="#quick-start">Quick Start</a>
</p>

[![mem20 Dashboard](https://via.placeholder.com/1200x400/1e1b4b/ffffff?text=mem20+Memory+%2B+Cognition+Substrate)](https://mem20.jaysonai.online)

---

**mem20** separates *grounded* memory (real observations, user statements, events) from *simulated* memory (hypotheticals, counterfactuals, model output) and couples forecasting ("world-model") predictions to observed outcomes. Promotions out of the simulated partition are evidence-based rather than honor-system.

Exposed to clients over the [Model Context Protocol](https://modelcontextprotocol.io) as a JSON-RPC 2.0 service on stdio. Connect Hermes Agent, Claude Code, or any MCP host.

> **v2.1 (frozen):** Pluggable integrations — Blender and Unity ship as optional, separately-installable modules. Code is frozen until the GitHub release is cut.

---

## What you can do with mem20

- **Give your AI agent a persistent memory** that survives across sessions, with hybrid retrieval (vector + BM25 + cross-encoder reranking) and automatic fact extraction.
- **Keep grounded facts strictly separate from imagined ones** — contamination guards at the storage layer make it impossible for hypotheticals to pollute your real memory.
- **Run cognitive operations** — reasoning (deductive, inductive, abductive, analogical, causal), planning with hierarchical decomposition, reflection, and working memory.
- **Simulate the future** — imagination tools for counterfactuals and generative simulation, with an evidence-based promotion path back to grounded memory.
- **Model other agents' perspectives** — theory-of-mind tools that simulate what another agent believes, knows, or intends.
- **Track the world** — world-model tools with variables, rules, and a prediction ledger that measures how often simulations come true.
- **Give your agent a self-model** — affective values, emotional states, and goal tracking for richer agent introspection.
- **Build a procedural skill library** — reusable how-to knowledge with steps, preconditions, and effects.
- **Run standups, reviews, and retrospectives** — roadmap registry for multi-phase project plans with phase tracking.
- **Automate 3D workflows** — optional Blender and Unity integration for modeling, rendering, and game-engine automation.
- **Sandboxed filesystem access** — let your agent read/write files within a controlled scope.
- **Observe everything** — `/health`, `/ready`, and `/metrics` endpoints with tool counters, contamination rate, and event taxonomy.

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

### Transport / protocol

- **MCP server** (`mcp` package) speaking JSON-RPC 2.0 over stdio.
- `Mem20MCPServer` (in `server.py`) aggregates per-domain mixin classes and dispatches in `_execute_tool()`.
- Tool schemas + handlers live in per-domain modules: `memory_tools.py`, `cognitive_tools.py`, `roadmap_tools.py`, `tools/world_tools.py`, `tools/blender_tools.py` (OPTIONAL Blender), `tools/unity_tools.py` (OPTIONAL Unity), and `tools/integration_tools.py` (filesystem + blank template for new optional integrations).
- `mcp_server.py` is a thin entry-point shim preserving the systemd unit path.

### Cognitive layer (`cog/`)

- `cognitive_engine.py` wraps an OpenAI-compatible LLM (`llm.py`) to provide thought processing, chains, reasoning, planning (`plan`/`aplan`), reflection, and working memory.
- Planning enforces the epistemic veto (see Governance).

### Memory layer (`mem/` + store engine `memory.py`)

- The durable memory engine lives on `MEM20_STORE_PATH` (default `~/.mem20/store`).
- It owns the ledger, the vector index (SentenceTransformer embeddings), and the BM25 corpus.

### Roadmap registry (`roadmaps/`)

- JSON files describing multi-phase project plans.

### Deployment (`systemd/`)

- A user service unit runs the MCP server under a virtualenv.

---

## Tool domains (13)

| Prefix | Domain | What it does |
|--------|--------|-------------|
| `memory_*` | Core memory | Store, recall, probe entities, reason across entities, contradiction detection, epistemic audit, namespaces, pins |
| `self_model_*` | Agent self-model | Track the agent's own beliefs, confidence, and identity over time |
| `cog_*` | Cognitive processing | Thought processing, reasoning chains, structured reasoning, planning, reflection, working memory |
| `imagination_*` | Counterfactual simulation | Generate hypotheticals, run "what-if" scenarios, simulate futures |
| `theory_of_mind_*` | Perspective simulation | Model what another agent believes, knows, or intends |
| `corrigibility_*` | Shutdown / capability tiers | Control the agent's capability levels and shutdown behavior |
| `roadmap_*` | Roadmap registry | Create, list, get, and update multi-phase project plans |
| `world_model_*` | World forecasting | Define variables and rules, record predictions, resolve against observed outcomes |
| `affective_*` | Values, emotions, goals | Track agent values, emotional states, and goal hierarchies |
| `procedural_*` | Skill library | Add, get, and search reusable procedural skills (how-to knowledge) |
| `fs_*` | Sandboxed filesystem | Read/write files within a controlled scope |
| `blender_*` | Blender automation | **OPTIONAL** — 3D modeling, rendering, scene manipulation (requires Blender app) |
| `unity_*` | Unity automation | **OPTIONAL** — Game-engine scripting, project builds, test runs (requires Unity Editor) |

---

## Memory model

mem20 keeps two logical partitions:

- **Grounded memory** — facts derived from real observations, user statements, or events.
- **Simulated memory** — hypotheticals, imagined scenarios, counterfactuals, or model output.

### Hard invariants enforced by the store engine

1. **Indexes are grounded-only.** `_add_to_vector_index()` and `_add_to_bm25_index()` call `_assert_grounded()`; a simulated record reaching either index raises immediately.
2. **`remember()` is grounded-only by default** (`_allow_simulated=False`). Simulated content uses its own path (`remember_simulated` / `memory_simulate_store`).
3. **Append-only ledger with validated tags.** Every ledger entry carries `origin` (e.g. `user`, `tool`, `simulated`) and `store` (`memory`/`imaginated`). `_validate_partition_tags()` rejects mismatches at the lowest append path.
4. **Promotion is evidence-based.** `promote_simulated_to_grounded()` accepts a simulated record only when it carries `prediction_error_evidence` — either a linked prior prediction resolved in its favor, or vouched for by a registered external verifier.
5. **Epistemic status is authoritative on the record.** `set_epistemic_status()` stamps the status directly onto the original grounded ledger line and the deep-store markdown header.

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

## Governance & Contamination Controls

- **Contamination guards** — `_assert_grounded()` at the vector/BM25 write paths.
- **Origin/store assertion** — `_validate_partition_tags()` at the ledger append path.
- **Epistemic veto / clearance** — `require_epistemic_clearance()` plus the plan-execution guard `run_plan_execution_guard()`. The cognitive engine enforces this on `plan`/`aplan`.
- **Audit** — `memory_audit_contamination()` inspects both the grounded store and the BM25 corpus for simulated records, returning `contamination_rate`, `violations`, and `violations_simulated_in_bm25_corpus`. A clean system reports rate `0.0`.
- **Prediction ledger** — `world_model_record_prediction` / `world_model_resolve_prediction` couple a forecast to its observed outcome, feeding the promotion gate and prediction-accuracy metrics.

---

## Quick Start

### Install from source

```bash
git clone https://github.com/JaysonAIOnline/mem20.git
cd mem20

# Create venv and install core deps
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Run the server (stdio)
MEM20_STORE_PATH=~/.mem20/store .venv/bin/python mcp/mcp_server.py
```

### Install on Penguin Linux (ChromeOS Crostini)

Penguin Linux is Debian-based — the standard systemd install works perfectly:

```bash
# Clone and install as a system service (recommended for always-on)
git clone https://github.com/JaysonAIOnline/mem20.git /opt/mem20
sudo /opt/mem20/install.sh --user $USER --dir /opt/mem20

# Verify it's running
curl http://localhost:8080/health
```

**What the installer does:**
- Creates a Python venv at `/opt/mem20/.venv`
- Installs core deps from `requirements.txt` (mcp, pydantic, numpy, faiss-cpu, sentence-transformers)
- Creates `/etc/systemd/system/mem20.service` and enables/starts it
- Default store path: `/opt/mem20/store`

**If you want to run without systemd (simpler for testing):**
```bash
sudo /opt/mem20/install.sh --no-systemd
# Then run manually:
MEM20_STORE_PATH=/opt/mem20/store /opt/mem20/.venv/bin/python /opt/mem20/mcp/mcp_server.py
```

**Note:** Penguin Linux has systemd, so the default install (without `--no-systemd`) is recommended. The service runs on port 8080.

### Install with systemd (recommended for always-on)

```bash
sudo ./install.sh --user $USER --dir /opt/mem20
```

`install.sh` creates the venv, installs deps, generates the systemd unit from `systemd/mem20.service.template`, and enables + starts it.

After start, probe health:

```bash
curl http://localhost:8080/health   # → {"status":"ok", ...}
curl http://localhost:8080/metrics  # → tool counters + contamination_rate
```

Point an MCP host at the server (stdio).

### Connect from Hermes Agent

```bash
# In your Hermes config, add mem20 as an MCP server
hermes config set mcp.servers.mem20 '["python3", "/path/to/mem20/mcp/mcp_server.py"]'
```

### Connect from Claude Code / Cursor

```bash
claude mcp add mem20 -- python3 /path/to/mem20/mcp/mcp_server.py
```

---

## Optional integrations (v2.1)

Blender and Unity ship as *separate, pluggable modules*. They require the respective external application installed:

- **Blender** — install Blender; ensure `blender` is on PATH or set `MEM20_BLENDER_EXECUTABLE`.
- **Unity** — install the Unity Editor; set `MEM20_UNITY_EXECUTABLE`.

When absent, the tools return an informative message instead of failing. See `requirements-optional.txt`.

To add your own optional integration, see `IntegrationToolsMixin.register_integration_template()` in `mcp/tools/integration_tools.py`.

---

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `MEM20_STORE_PATH` | `~/.mem20/store` | Memory engine module + store location |
| `MEM20_COG_PATH` | (mem20 `cog/` dir) | Cognitive engine location |
| `MEM20_LLM_BASE_URL` | `https://integrate.api.nvidia.com/v1` | LLM chat-completions base URL |
| `MEM20_LLM_MODEL` | (project default) | Model name |
| `NVAPI_KEY` / `NVIDIA_API_KEY` / `MEM20_LLM_API_KEY` | — | LLM bearer token (required) |
| `MEM20_ENV_FILE` | — | Optional `.env` to load API keys from |
| `MEM20_FLAG_WORLDMODEL_20` | `1` (ON) | Kill-switch for world-model / self-model / affective / procedural tools |

---

## Roadmap registry

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

Tools: `roadmap_create`, `roadmap_list`, `roadmap_get`, `roadmap_update_phase`.

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

Core (Python, pip) — `requirements.txt`:

- `mcp` — MCP server framework
- `sentence-transformers` — `SentenceTransformer` (embeddings) and `CrossEncoder` (reranking)
- `numpy` — vector math
- `faiss-cpu` — vector index
- `pydantic`, `anyio` — MCP transport
- LLM access — `cog/` talks to an OpenAI-compatible chat-completions endpoint via `llm.py` (default NVIDIA `integrate.api.nvidia.com/v1`); requires an API key, no SDK beyond `httpx`

Optional / integration-only (external applications — degrade gracefully when absent):

- **Blender** — install Blender; ensure `blender` is on PATH or set `MEM20_BLENDER_EXECUTABLE`
- **Unity** — install the Unity Editor; set `MEM20_UNITY_EXECUTABLE`

Install core:

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
# or, with dev + integration extras:
#   .venv/bin/pip install -e ".[dev]"
```

---

## Development / Onboarding

- **Engine logic** lives in the store engine (`memory.py` on `MEM20_STORE_PATH`), not in the MCP server. MCP tools are thin handlers that call engine functions.
- **Adding a tool:** pick the domain module, add the `self.tools["name"] = mt.Tool(...)` block, and add a dispatch branch + handler. Run `verification/verify_refactor.py` after changes.
- **Adding an OPTIONAL integration:** create `mcp/tools/<name>_tools.py` with a `<Name>ToolsMixin`, guard any external executable with a graceful check, add the mixin to `Mem20MCPServer`'s bases, and call `self.register_<name>_tools()` in `_setup_tools()`.
- **Verify governance** after changes: call `memory_audit_contamination()` and confirm `contamination_rate == 0.0`.
- **Roadmaps** are plain JSON in `roadmaps/`; edit via the `roadmap_*` tools or directly.

---

## Documentation

Full docs live at **[mem20.jaysonai.online](https://mem20.jaysonai.online)**.

| Resource | What's covered |
|----------|----------------|
| [`README.md`](README.md) | This file — overview, quick start, architecture |
| [`CHANGELOG.md`](CHANGELOG.md) | Release notes, version history |
| [`2.0_roadmap/`](2.0_roadmap/) | 2.0 roadmap deliverables and human execution package |
| [`systemd/mem20.service.template`](systemd/mem20.service.template) | Systemd unit template for production deployment |
| [`verification/verify_refactor.py`](verification/verify_refactor.py) | Refactor verification script |
| [`tests/`](tests/) | pytest suite covering contamination firewall, eval safety, dispatch, metrics |
| [`roadmaps/`](roadmaps/) | Roadmap registry (JSON) |
| [`mcp/`](mcp/) | MCP server implementation and tool modules |
| [`cog/`](cog/) | Cognitive engine (LLM-backed reasoning, planning, reflection) |
| [`memory_engine/`](memory_engine/) | Core memory store engine |
| [`proof/`](proof/) | Audit responses and verification artifacts |

---

## Contributing

Contributions are welcome! Before submitting a PR:

1. Run `verification/verify_refactor.py` if you touched engine code.
2. Run `pytest tests/` to confirm all tests pass.
3. Confirm `contamination_rate == 0.0` after any memory-layer changes.
4. Update docs when behavior or architecture changes.

---

## License

MIT — see [LICENSE](LICENSE).

Built by [JaysonAIOnline](https://github.com/JaysonAIOnline).
