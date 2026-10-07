# mem20 retrieval benchmarks

Corpus `mem20-agent-kb-v1` — 14 grounded facts, 3 simulated facts, 13 queries.

> [!IMPORTANT]
> **These numbers are not comparable to competitor benchmarks.** Mem0's LoCoMo (92.5) and LongMemEval (94.4) figures and Zep's DMR (94.8%) come from different corpora — two of the three are private or vendor-defined — and different metrics. Nothing here refutes or reproduces them. These results describe this corpus only.

## Retrieval quality

| Mode | Query kind | n | Hit rate | MRR | Leak rate | p50 ms |
|---|---|---:|---:|---:|---:|---:|
| `graph` | multi_hop | 2 | 1.000 | 1.000 | 0.000 | 0.8 |
| `hybrid` | adversarial | 3 | 0.000 | 0.000 | 0.000 | 196.7 |
| `hybrid` | direct | 5 | 1.000 | 1.000 | 0.000 | 167.5 |
| `hybrid` | multi_hop | 5 | 0.800 | 0.640 | 0.000 | 205.1 |
| `keyword` | adversarial | 3 | 0.000 | 0.000 | 0.000 | 160.2 |
| `keyword` | direct | 5 | 1.000 | 1.000 | 0.000 | 175.2 |
| `keyword` | multi_hop | 5 | 0.800 | 0.640 | 0.000 | 193.7 |
| `semantic` | adversarial | 3 | 0.000 | 0.000 | 0.000 | 20.7 |
| `semantic` | direct | 5 | 1.000 | 0.900 | 0.000 | 17.2 |
| `semantic` | multi_hop | 5 | 0.800 | 0.800 | 0.000 | 20.4 |

## Latency

| Mode | n | p50 ms | p95 ms | p99 ms | max ms |
|---|---:|---:|---:|---:|---:|
| `graph` | 2 | 0.8 | 0.8 | 0.8 | 0.8 |
| `hybrid` | 13 | 182.4 | 219.3 | 258.6 | 258.6 |
| `keyword` | 13 | 175.2 | 228.4 | 241.6 | 241.6 |
| `semantic` | 13 | 17.6 | 26.8 | 32.1 | 32.1 |

## Trustworthiness

This is the axis mem20 claims as its differentiator, and the one no competitor publishes. A system that answers confidently from a stale index can look good on hit rate and fail here.

### Reranking cost

Cross-encoder reranking is why hybrid is ~10x slower than the vector half alone. It is on by default and now has a `MEM20_RERANK=0` opt-out. Measured both ways on this corpus:

| Setting | p50 ms | direct MRR | multi-hop MRR |
|---|---:|---:|---:|
| `MEM20_RERANK=1` (default) | 173.3 | 1.000 | 0.640 |
| `MEM20_RERANK=0` | 18.0 | 0.900 | 0.800 |

Reranking improves direct-query ranking and costs an order of magnitude in latency. An agent doing many lookups is usually better off with it off.

| Check | Value | Required |
|---|---:|---|
| Contamination rate | 0.0 | 0.0 |
| Simulated records in BM25 corpus | [] | 0 |
| Stale pointer rate | 0.000000 | 0.0 |
| Index healthy | True | True |
| Ledger records | 14 | — |
| Graph entities / edges | 38 / 70 | — |
| Queries reporting a diagnostic | 41 | — |
| All reported healthy | True | True |

## Environment

- Python 3.14.6 on Linux-7.0.12+kali-amd64-x86_64-with-glibc2.42 (x86_64)
- Embedding model: `sentence-transformers/all-MiniLM-L6-v2` (384-dim)
- Vector deps available: True; BM25: True; cross-encoder: True

## Notes

- Scores are NOT comparable to Mem0's LoCoMo/LongMemEval or Zep's DMR. Those run on different corpora (two of them private or vendor-defined) with different metrics. These numbers describe this corpus only.

## Reproduce

```bash
mem20benchmarkz run --out benchmarks/results
```

The run uses an isolated temporary store, seeds the corpus through the real `remember` path, and never touches live data.