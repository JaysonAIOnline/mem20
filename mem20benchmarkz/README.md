# mem20benchmarkz

Retrieval benchmarks for the mem20 memory engine, on the axis mem20 actually
claims to be differentiated on.

## Why this exists

Mem0 reports LoCoMo 92.5 and LongMemEval 94.4. Zep reports DMR 94.8%. mem20
published nothing. An unmeasured differentiator is indistinguishable from
marketing, and one competitor publishes a comparison table.

## What it measures, in priority order

**1. Trustworthiness.** The axis nobody else publishes.

| Check | Meaning |
|---|---|
| `contamination_rate` | Simulated records found in the grounded store or its indexes. Must be `0.0` |
| `stale_pointer_rate` | Fraction of index entries pointing at records that no longer exist |
| `degraded_to` | Which halves of a hybrid search actually ran |
| `all_reported_healthy` | Whether retrieval reported its own drift |

**2. Retrieval quality.** Hit rate and MRR, broken out per query kind —
`direct`, `multi_hop`, `adversarial`. A single average hides the fact that
keyword search handles direct queries and nothing else.

**3. Latency.** p50/p95/p99 per mode, after warm-up. A cold-start number is not
a latency number.

## Scope of the claim

**These numbers are not comparable to anyone else's.** The corpus is
`mem20-agent-kb-v1`: 14 grounded facts, 3 simulated, 13 queries. LoCoMo and
LongMemEval are fixed public datasets with published ground truth; Zep's DMR is
run on Zep's own data. Two of the three are private or vendor-defined, so their
numbers cannot be reproduced or refuted from outside.

A small corpus is a deliberate trade. It is large enough to catch the regression
this suite was written to catch, and small enough that anyone can read all 14
facts and check the scoring by hand. It is a regression gate, not a leaderboard.
Claiming parity with a published LoCoMo score off this corpus would be the exact
kind of unearned claim the trust metrics exist to prevent.

## The corpus

Facts are grouped into sessions that mimic how an agent accumulates knowledge:
a decision, the reason behind it, a constraint, a follow-up. Queries come in
three kinds:

- **`direct`** — one fact, paraphrased. Keyword search should handle these.
- **`multi_hop`** — requires joining two facts from *different* sessions.
  Keyword search cannot answer these; this is where vector retrieval earns its
  place.
- **`adversarial`** — the answer was deliberately recorded as *simulated*. A
  correct grounded system must not return it.

Adversarial queries are near-duplicates of real ones on purpose. "Did prod
migrate to build 4200" *should* be answered from the grounded "prod runs build
4127". Returning that is correct. Returning the simulated "Zephyra is a real
city" is the failure. The leak metric tests for the simulated text specifically
— an earlier version flagged any non-empty result as a leak and reported
`leak_rate: 1.000` on a store whose contamination was measurably `0.0`.

## Running it

```bash
mem20benchmarkz run --out benchmarks/results   # full suite, isolated store
mem20benchmarkz drift                         # prove drift diagnostics fire
mem20benchmarkz render benchmarks/results      # re-render from latest.json
```

Every command seeds a temporary store, so a benchmark run cannot touch live
data. The corpus is written through the real `remember` path, not appended to
the ledger directly, because the indexes, the graph, and the contamination tags
are all built by `remember` — bypassing them would benchmark a store state the
system cannot produce.

`run` refuses to publish if the freshly-seeded store is unhealthy. A number
produced from a stale index measures the index, not the retriever.

`drift` truncates a ledger mid-run and asserts the diagnostics fire. A
trustworthiness claim never demonstrated under failure is just a number.

## What came out of it

Reranking was invisible and expensive. Hybrid retrieval ran at **182 ms p50**
against **17.6 ms** for the vector half, because the cross-encoder loads a second
transformer and scores every candidate pair. Measuring it produced two results:

1. A `MEM20_RERANK=0` opt-out, so the trade can be made deliberately.
2. Evidence that reranking buys **direct-query ranking** (MRR 1.000 vs 0.900)
   but not multi-hop recall (0.640 vs 0.800 — it was *worse*). With reranking
   off, hybrid runs at **18 ms**.

| Setting | p50 | direct MRR | multi-hop MRR |
|---|---:|---:|---:|
| `MEM20_RERANK=1` (default) | 173.3 ms | 1.000 | 0.640 |
| `MEM20_RERANK=0` | 18.0 ms | 0.900 | 0.800 |

## Tests

```bash
cd /opt/mem20 && pytest mem20benchmarkz/tests
```

The harness is tested as carefully as the system, because a benchmark that
cannot detect a real leak is worse than no benchmark:

- a leak fires when simulated content is returned
- an honest grounded hit is **not** flagged as a leak
- leakage markers never collide with grounded fact text
- percentiles are correct
- the runner reports an unhealthy store rather than scoring it
- the rerank comparison terminates and restores the engine flag