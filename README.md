<p align="center">
  <img src="https://img.shields.io/badge/mem20-v2.1--rc2-6366f1?style=for-the-badge&logo=github" alt="mem20 v2.1-rc2">
</p>
<p align="center">
  <strong>A memory substrate and agent runtime for AI systems that have to be trusted.</strong>
</p>
<p align="center">
  <a href="https://mem20.jaysonai.online"><img src="https://img.shields.io/badge/Website-mem20.jaysonai.online-FFD700?style=for-the-badge" alt="Website"></a>
  <a href="https://github.com/JaysonAIOnline/mem20/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License: MIT"></a>
  <a href="https://github.com/JaysonAIOnline/mem20/releases"><img src="https://img.shields.io/github/v/release/JaysonAIOnline/mem20?style=for-the-badge" alt="Release"></a>
</p>

<p align="center">
  <a href="#what-this-is">What this is</a> · <a href="#the-honest-claim">The honest claim</a> · <a href="#benchmarks">Benchmarks</a> · <a href="#the-estate">The estate</a> · <a href="#quick-start">Quick start</a> · <a href="docs/">Docs</a>
</p>

---

**mem20 started as a memory store for AI agents. It is now the runtime those agents live in.**

The original idea — separate *grounded* facts from *simulated* ones and refuse to promote a hypothesis without evidence — is still enforced at the lowest append path and is still the thing that distinguishes mem20 from every other memory product. But that is one subsystem. Around it there are **301 organs**, **17 services**, **28 live systemd units**, an append-only cryptographic ledger in Rust, a dream engine with an eight-model critique panel, an IRC channel where agents coordinate with each other, a 3D modeler with procedural node graphs, a visual programming language, and a chat front-end with its own model gateway.

If you came here for a memory library, read [What this is](#what-this-is) and stop. If you came to see what an agent platform looks like when one person builds the whole stack, keep going.

---

## What this is

### The original: a memory substrate that cannot lie to itself

The store keeps two partitions that never mix.

**Grounded** memory holds facts from real observations, user statements, or events. **Simulated** memory holds counterfactuals, hypotheses, and model output. The separation is enforced in code, not by convention:

- `remember()` refuses any record not tagged `origin="grounded"`. An explicit `_allow_simulated=True` is *rejected on purpose*, so no future refactor can quietly route simulation through the grounded path.
- The vector and BM25 indexes call `_assert_grounded()` on every write. A simulated record reaching an index raises immediately rather than being caught later by an audit.
- Promotion from simulated to grounded requires evidence: either a prior prediction that resolved in the fact's favor, or attestation from a registered external verifier. A boolean flag and a free-text note are refused.
- `audit_contamination()` returns a `contamination_rate`. A clean store reports `0.0`.

[Mem0](https://github.com/mem0ai/mem0) reports LoCoMo 92.5 and LongMemEval 94.4. [Zep](https://github.com/getzep/zep) reports DMR 94.8%. Those are recall-quality numbers on their own corpora. mem20 publishes its own numbers — see [Benchmarks](#benchmarks) — including the ones nobody else reports.

### The retrieval layer

Four retrieval modes over the same store:

| Mode | What it does | When to use it |
|---|---|---|
| `recall()` | Reverse-chronological filter by topic and tags | You know the topic |
| `recall_semantic()` | Vector search over MiniLM embeddings, optional cross-encoder rerank | You remember the meaning, not the words |
| `recall_hybrid()` | Reciprocal Rank Fusion of vector + BM25, then rerank | Default. Best recall |
| `recall_graph()` | Multi-hop traversal over an entity/edge graph built at write time | "What is connected to X?" |

Every retrieval result carries a diagnostic. This is the difference from a normal vector store:

```python
from mem20api import open_store

with open_store() as store:
    r = store.semantic("what build is prod on")
    r["hits"]           # the results
    r["healthy"]        # False if the index has drifted from the ledger
    r["diagnostic"]     # exactly how many stale pointers exist
```

That is not decoration. Semantic retrieval on this repository's own live store was returning **zero results while reporting success**: the FAISS index held 2,681 vectors, the ledger held 371 records, and 2,312 index entries pointed at records that no longer existed. Every one was found by the search and then silently dropped because its content could not be resolved. A caller could not distinguish "nothing matches" from "your index is stale." That defect is fixed, measured by [`index_health()`](mem20api/README.md), and covered by tests that truncate a ledger and assert the diagnostic fires.

### The cognitive layer

Reasoning in five modes (deductive, inductive, abductive, analogical, causal), hierarchical planning, reflection, working memory, a 28-paradigm substrate, and tree-of-thought search. Planning enforces an **epistemic veto**: a plan whose supporting facts are still marked `hypothesis` or `imagined` is refused unless clearance is granted.

This is exposed as tools, not as a library you call — an agent reasons through the same surface it uses for memory.

### Dreaming and imagination

**The dream engine** ([`mem20dreamz`](mem20dreamz/README.md)) iterates on artifacts with a panel of eight *distinct* models, each critiquing in its own domain. The design rule is that iteration must **improve**, never **condense**: a lineage keeps the full artifact, every intermediate version, an invention register, and its own evolving config. It runs as a systemd service (`mem20-dreamer.service`) with an idle timer.

Why eight models rather than one: a single-model panel makes its own blind spot *systematic*. Every member can be confidently wrong the same way, and agreement gets laundered into consensus. `assert_roster_valid()` **raises** on a duplicate model rather than deduplicating silently — which is what previously deleted a role and left the invention register permanently empty with nothing reporting why.

**Imagination** is a separate tool family: counterfactuals, generative simulation, concept recombination, mental models, and adversarial critique. Simulated output lands in the simulated partition and cannot contaminate grounded memory. It becomes real only through evidence-based promotion.

---

## The honest claim

> **mem20 does not win on recall quality. It wins on recall trustworthiness.**

The incumbents have more data, more benchmark iterations, and more engineers. Pretending otherwise would be marketing, and a competitor publishes one comparison and the claim is dead.

What is uncontested is the axis mem20 is built around: **a memory system that tells you when it does not know, and never silently degrades.** Concretely:

- A contaminated store reports `contamination_rate > 0`. It cannot look healthy while leaking.
- An index that has drifted from its ledger reports it, with exact counts, on every retrieval call.
- Hybrid search reports which halves actually ran, so a silent fallback to keyword-only is visible.
- Graph retrieval reports honestly when an entity is absent instead of returning an empty result.
- Promotion out of the simulated partition requires evidence, not a flag.

These are all measured in [Benchmarks](#benchmarks). A system that answers confidently from a stale index can post an excellent hit rate and score terribly here. That is the point of measuring it.

**Where mem20 is behind, stated plainly:** no bi-temporal (event-time + ingestion-time) model — Zep's is genuinely best-in-class and ours is deferred; no temporal graph at all; Python-only SDK, where Mem0 ships Python, TypeScript, and Go; and a small corpus, so the quality numbers above are from 14 facts and 13 queries, which is enough to catch a regression and not enough to claim parity with anything.

---

## Benchmarks

Published at [`benchmarks/results/latest.md`](benchmarks/results/latest.md), regenerated with:

```bash
mem20benchmarkz run --out benchmarks/results
```

Retrieval quality, per query kind (a single average hides that keyword search handles direct queries and nothing else):

| Mode | direct | multi-hop | adversarial leak |
|---|---:|---:|---:|
| `keyword` (BM25 only) | 1.000 | 0.800 | 0.000 |
| `semantic` (vector) | 1.000 | 0.800 | 0.000 |
| `hybrid` (RRF + rerank) | 1.000 | 0.800 | 0.000 |
| `graph` (multi-hop) | — | 1.000 | — |

Trustworthiness — the axis mem20 claims:

| Check | Value | Required |
|---|---:|---|
| Contamination rate | **0.0** | 0.0 |
| Simulated records in BM25 corpus | **0** | 0 |
| Stale pointer rate | **0.000000** | 0.0 |
| Index healthy | **True** | True |

Latency, and the finding that came out of measuring it:

| Mode | p50 | p95 | p99 |
|---|---:|---:|---:|
| `graph` | 0.8 ms | 0.8 ms | 0.8 ms |
| `semantic` | 17.6 ms | 26.8 ms | 32.1 ms |
| `hybrid` (rerank on) | 182.4 ms | 219.3 ms | 258.6 ms |
| `hybrid` (`MEM20_RERANK=0`) | **18.0 ms** | — | — |

Cross-encoder reranking costs an order of magnitude in latency and buys direct-query ranking, not multi-hop recall. It now has an opt-out (`MEM20_RERANK=0`) because the benchmark found the tax was invisible.

> **These numbers are not comparable to competitor benchmarks.** Mem0's LoCoMo (92.5) and LongMemEval (94.4) figures and Zep's DMR (94.8%) come from different corpora — two of the three are private or vendor-defined — and different metrics. Nothing here reproduces or refutes them. This corpus is `mem20-agent-kb-v1`, 14 facts and 13 queries. It is small on purpose: it is a regression gate, not a leaderboard.

---

## The estate

**327 indexed subsystems** — 301 organs, 17 services, 9 other. 8,969 source files, ~468k code lines.

Find code with the sitemap instead of grepping:

```bash
/sitemap search "graph node eval"     # ranked across names, entry points, keywords
/sitemap show mem20dreamz             # full detail for one subsystem
/sitemap build                        # rescan after adding a subsystem
```

| Layer | What lives there |
|---|---|
| `memory_engine/` | The store: append-only ledger, vector + BM25 + graph indexes, contamination firewall |
| `mem20api/` | Stable Python API over the engine — bind a store, get honest diagnostics |
| `mem20benchmarkz/` | The benchmark suite in this README |
| `mcp/` | MCP server: **258 tools across 26 domains** |
| `cog/` | Cognitive engine (reasoning, planning, reflection) |
| `braid/` | **Append-only cryptographic ledger in Rust** — see below |
| `mem20dreamz/` | The dream engine |
| `mem20oreo/` | OREO — visual, natural-language-first language |
| `mem20kilnz/engine/` | kiln — Linux 3D modeler with procedural node graphs |
| `mem20agentz/` | Full agent platform: sessions, skills, projects, gateway, desktop |
| `mem20owebz/` | Chat front-end + LiteLLM model gateway |
| `mem20ircz/`, `mem20botz/` | The IRC channel where agents talk and take jobs |
| `mem20controlz/` | Unified control plane with per-subsystem panels |
| `toolchest/` | Registry of 879 capabilities (258 MCP tools, 318 CLIs, 303 subsystems) with runtime status |

### Braid: the ledger everything else could be built on

[`braid/`](braid/README.md) is a Cargo workspace of nine crates implementing an append-only Merkle-DAG ledger where **every write is signed**.

- `braid_core` — Ed25519 signing, BLAKE3 hashing, `br`-prefixed CIDs, a parent-CID spine, and `proof()` to genesis. `node_is_proven(node)` is the single fact gate every door shares: audit verification *and* re-derivation of the node's committed CID, because a signature alone covers the strand, not the payload.
- Capability grants are **one-directional** — only the granting side may wildcard — so a narrow rule cannot mint broad power.
- Escalation binds two triplets (base + human-gated) to one node. The base policy must *deny* the operation for escalation to be reachable at all.
- `braid_intent` treats a desire as an ordinary committed node. It stays OPEN until a *later proven* node references it. Resolution is ledger motion, never imagined execution: an injected unsigned resolver leaves the intent OPEN, and that is unit-tested.

### The MCP surface

258 tools in 26 domains. The largest:

| Prefix | Tools | Domain |
|---|---:|---|
| `memory_*` | 52 | Core memory, retrieval, epistemic audit |
| `cog_*`, `tot_*` + substrate | 18 | Reasoning, planning, tree-of-thought |
| `world_model_*` | 15 | Forecasting with a prediction ledger |
| `vcs_*` | 11 | Git and GitHub |
| `cloud_*`, `cloudstorage_*` | 18 | AWS, Azure, GCP, K8s, Docker, R2 |
| `db_*` | 10 | SQL across six engines |
| `fs_*` | 10 | Sandboxed filesystem |
| `braid_*` | 9 | The ledger |
| `comm_*` | 9 | Email, Slack, Discord, Telegram, SMS |
| `dev_*` | 9 | Tests, lint, search, sandboxed exec |
| `scrape_*` | 8 | Web scraping, forms, Playwright |
| `imagination_*` | 8 | Counterfactuals, recombination, mental models |

Plus `blender_*` and `unity_*` as **optional** integrations that require the external application and return an informative message when absent rather than failing.

---

## Quick start

```bash
git clone https://github.com/JaysonAIOnline/mem20.git
cd mem20

python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

MEM20_STORE_PATH=~/.mem20/store .venv/bin/python mcp/mcp_server.py
```

Or use the Python API directly:

```bash
pip install -e ./mem20api
```

```python
from mem20api import open_store

with open_store() as store:
    store.remember("deploys", "Prod runs build 4127", tags=["prod"])
    store.hybrid("what build is prod on", k=5)
    store.graph("prod", hops=2)
    store.health()      # index/ledger agreement
```

Check that your indexes still match your ledger — the check that would have caught the defect described above:

```bash
mem20-api-health health      # exits non-zero if anything drifted
mem20-api-health rebuild     # reindex from the ledger
```

---

## Documentation

| Resource | What's covered |
|---|---|
| [`benchmarks/results/latest.md`](benchmarks/results/latest.md) | Retrieval quality, latency, trustworthiness |
| [`SITEMAP.md`](SITEMAP.md) | Generated map of all 327 subsystems |
| [`mem20api/README.md`](mem20api/README.md) | The Python API |
| [`mem20benchmarkz/README.md`](mem20benchmarkz/README.md) | Benchmark methodology and scope |
| [`braid/README.md`](braid/README.md) | The ledger architecture |
| [`mem20dreamz/README.md`](mem20dreamz/README.md) | The dream engine |
| [`docs/`](docs/) | Extended tool and usage reference |
| [mem20.jaysonai.online](https://mem20.jaysonai.online) | Hosted documentation |

---

## Development

- **Engine logic** lives in the store engine, not in the MCP server. MCP tools are thin handlers.
- **Verify claims by execution.** [`mem20verify`](mem20verify/README.md) exists because claims were being trusted instead of verified.
- **Run the full suite.** A bare `pytest` from the repo root collects every package's tests (see `pytest.ini`); `pytest tests/` covers only the core suite.
- **Contamination must stay at 0.0** after any memory-layer change.

```bash
pytest                                   # whole estate
mem20verify tests                        # per-package, with timeouts
mem20benchmarkz run                      # retrieval benchmarks
```

---

## License

MIT — see [LICENSE](LICENSE).

Built by [JaysonAIOnline](https://github.com/JaysonAIOnline).