# mem20 MCP Server Documentation

> **Version:** 2.1-rc2
> **License:** MIT
> **Author:** JaysonAIOnline
> **Repository:** https://github.com/JaysonAIOnline/mem20

## Quick Links

| Document | Description |
|----------|-------------|
| [Architecture Overview](01-architecture.md) | System design, memory model, tool domains, deployment |
| [Tools Reference](02-tools-reference.md) | Complete reference for all 111 MCP tools |
| [Installation Guide](03-installation.md) | Install, configure, and connect MCP hosts |
| [Usage Examples](04-usage-examples.md) | Practical examples for every tool domain |

## What is mem20?

**mem20** is a **persistent memory + cognition substrate for AI agents**. It provides:

- **Persistent memory** with hybrid retrieval (vector + BM25 + cross-encoder)
- **Strict separation** of grounded facts from imagined/hypothetical ones
- **Cognitive operations** — reasoning, planning, reflection, working memory
- **World modeling** — define variables, record predictions, resolve outcomes
- **Self-modeling** — track beliefs, values, emotions, goals
- **Multi-agent coordination** — A2A communication, shared namespaces
- **3D workflow automation** — optional Blender and Unity integration

## Architecture at a Glance

```
MCP client --stdio--> Mem20MCPServer (mcp/mcp_server.py)
                         |
         +---------------+---------------+
         |               |               |
   cognitive_engine    memory.py      roadmaps/
   (LLM-backed)    (store engine)   (JSON files)
```

## 111 Tools Across 15 Domains

| Domain | Prefix | Count |
|--------|--------|-------|
| Core memory | `memory_*` | 36 |
| Cognitive processing | `cog_*` | 6 |
| Imagination/Simulation | `imagination_*` | 9 |
| Self-model | `self_model_*` | 3 |
| Theory of mind | `theory_of_mind_*` | 2 |
| Corrigibility/Shutdown | `corrigibility_*` | 2 |
| Roadmap registry | `roadmap_*` | 4 |
| World forecasting | `world_model_*` | 8 |
| Values/Emotions/Goals | `affective_*` | 6 |
| Skill library | `procedural_*` | 6 |
| Sandboxed filesystem | `fs_*` | 3 |
| Blender automation | `blender_*` | 7 |
| Unity automation | `unity_*` | 5 |
| Agent-to-agent | `a2a_*` | 5 |
| Thought process | `tot_*` / etc. | 9 |

## Quick Start

```bash
# Install
git clone https://github.com/JaysonAIOnline/mem20.git
cd mem20
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Configure
export NVAPI_KEY="your-nvidia-api-key"

# Run
python mcp/mcp_server.py

# Verify
curl http://localhost:8080/health
```

## Connecting MCP Hosts

```bash
# Hermes Agent
hermes config set mcp.servers.mem20 '["python3", "/path/to/mem20/mcp/mcp_server.py"]'

# Claude Code
claude mcp add mem20 -- python3 /path/to/mem20/mcp/mcp_server.py
```

## Key Concepts

### Memory Partitions

- **Grounded** — real observations, user statements, events (indexed)
- **Simulated** — hypotheticals, counterfactuals, model output (not indexed)

### Contamination Controls

- Indexes are grounded-only
- Simulated content can NEVER leak into grounded indexes
- Promotion requires evidence (prediction-error resolution or external verification)

### Health & Observability

- `/health` — status check
- `/ready` — readiness probe
- `/metrics` — tool counters, contamination rate, event taxonomy

## Optional Integrations

- **Blender** — 3D modeling, rendering, scene manipulation
- **Unity** — Game-engine scripting, builds, tests

Both degrade gracefully when the respective application is not installed.

## License

MIT — see [LICENSE](https://github.com/JaysonAIOnline/mem20/blob/main/LICENSE).

Built by [JaysonAIOnline](https://github.com/JaysonAIOnline).