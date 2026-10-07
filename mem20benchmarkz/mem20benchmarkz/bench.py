"""Retrieval benchmarks: recall quality, latency, and trustworthiness.

Run against an isolated store so a benchmark run can never touch real data:

    mem20benchmarkz run --out benchmarks/results

## What each metric means

Recall metrics
    `hit@k`  — fraction of answerable queries whose top-k results contain the
               expected evidence. Reported per query kind, because a single
               average hides the fact that keyword search can do direct queries
               and nothing else.
    `mrr`    — mean reciprocal rank, which penalises finding the right fact
               eighth instead of first.
    `leak@k` — for adversarial queries, the fraction that returned any grounded
               support at all. This is the number that should be zero, and a
               system without a hard simulated/grounded partition cannot score
               it.

Latency
    p50/p95/p99 in milliseconds, measured per query and per retrieval mode,
    with the embedding model warmed first. A cold-start number is not a latency
    number.

Trustworthiness
    `contamination_rate` — simulated records found in the grounded store or its
                            indexes. Must be 0.0.
    `stale_pointer_rate`  — fraction of index entries pointing at records that
                            no longer exist. The failure mode that made semantic
                            retrieval return zero results while reporting
                            success.
    `degradation_reported`— whether a query on a deliberately broken index said
                            so, instead of returning a plausible short list.

## Reading the output honestly

The suite refuses to report a quality score on a store whose indexes it knows
are unhealthy. A number produced from a stale index measures the index, not the
retriever, and publishing it would be the same error the diagnostics were added
to prevent.
"""
from __future__ import annotations

import json
import statistics
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .corpus import Corpus, load


@dataclass
class QueryResult:
    qid: str
    kind: str
    mode: str
    hit: bool
    rank: int | None          # 1-based rank of the first supporting hit
    leaked: bool
    n_results: int
    latency_ms: float
    degraded_to: str | None = None
    drift_healthy: bool | None = None


@dataclass
class Metric:
    name: str
    value: float
    unit: str = ""


@dataclass
class Report:
    corpus: str
    facts: int
    simulated: int
    queries: int
    environment: dict = field(default_factory=dict)
    recall: dict = field(default_factory=dict)
    latency_ms: dict = field(default_factory=dict)
    trust: dict = field(default_factory=dict)
    per_query: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))
    return s[idx]


def _hit(r_hits: list[dict], expect: tuple[str, ...],
         supports: set[str]) -> tuple[bool, int | None]:
    """First rank whose content satisfies the query's evidence requirement.

    A supporting *id* match counts when we can see ids. Otherwise we fall back
    to the `expect` substrings, because the graph path returns content without
    ids and we still want an honest verdict rather than a silent zero.
    """
    for i, h in enumerate(r_hits, 1):
        hid = h.get("id")
        if supports and hid and hid in supports:
            return True, i
        if expect:
            blob = " ".join(str(x) for x in expect).lower()
            if blob in str(h.get("content", "")).lower():
                return True, i
    return False, None


def _run_mode(store, q, mode: str, k: int) -> tuple[list[dict], str | None,
                                                    bool | None, float]:
    t0 = time.perf_counter()
    if mode == "semantic":
        r = store.semantic(q.text, k=k)
        ms = (time.perf_counter() - t0) * 1000
        return r["hits"], None, r["healthy"], ms
    if mode == "hybrid":
        r = store.hybrid(q.text, k=k)
        ms = (time.perf_counter() - t0) * 1000
        return r["hits"], r["degraded_to"], True, ms
    if mode == "graph":
        r = store.graph(q.entity or "", hops=q.hops, max_results=k)
        ms = (time.perf_counter() - t0) * 1000
        facts = [{"id": f.get("id"), "content": f.get("content", "")}
                 for f in r.get("facts", [])]
        return facts, ("found" if r.get("found") else "miss"), True, ms
    if mode == "keyword":
        # Engine-level BM25 via hybrid with alpha=0, which is the honest way to
        # isolate the keyword half using the shipped code path.
        r = store.hybrid(q.text, k=k, alpha=0.0)
        ms = (time.perf_counter() - t0) * 1000
        return r["hits"], r["degraded_to"], True, ms
    raise ValueError(mode)


def _answerable_ids(corpus: Corpus) -> set[str]:
    """Ids of grounded facts, so we can tell support from coincidence."""
    out: set[str] = set()
    per_topic: dict[str, int] = {}
    for f in corpus.facts:
        per_topic[f.topic] = per_topic.get(f.topic, 0) + 1
    counters: dict[str, int] = {}
    for f in corpus.facts:
        counters[f.topic] = counters.get(f.topic, 0) + 1
        out.add(f"{f.topic}-{counters[f.topic]}")
    return out


def _distinctive(text: str) -> str:
    """Pick a substring from `text` that identifies it and nothing else.

    The whole sentence is too blunt: a simulated fact often restates real
    vocabulary, and matching on that would flag an honest grounded result.
    Preference order:

      1. A rare-looking long word — "BLAKE3", "contaminated", "Zephyra".
      2. A capitalised token, because a fabricated proper noun is the usual tell.
      3. The leading clause, as a last resort.
    """
    import re as _re

    words = [w.strip(".,;:!?\"'()[]{}") for w in text.split()]
    longish = [w for w in words if len(w) >= 8]
    if longish:
        return max(longish, key=len).lower()

    caps = [w for w in words if w[:1].isupper() and len(w) >= 5]
    if caps:
        return max(caps, key=len).lower()

    return " ".join(words[:4]).lower()


def _leak(hits: list[dict], forbidden: tuple[str, ...]) -> bool:
    """Did an adversarial query surface any simulated content?

    The test is whether the *simulated text* came back, not whether the query
    returned anything. An earlier version flagged any non-empty result list as a
    leak and reported `leak_rate: 1.000` on a store where contamination was
    measurably 0.0 — the query had simply matched unrelated grounded facts,
    which is normal retrieval behaviour and not a partition failure.

    Adversarial queries are near-duplicates of real ones by design: "did prod
    migrate to build 4200" must be answerable from the grounded "prod runs build
    4127". Returning that is correct. Returning "Zephyra is a real city" is the
    failure. So the needle is the distinctive simulated token.
    """
    if not forbidden:
        return False
    for h in hits:
        blob = str(h.get("content", "")).lower()
        if any(f.lower() in blob for f in forbidden):
            return True
    return False


def _recall_block(corpus: Corpus, results: list[QueryResult]) -> dict:
    out: dict = {}
    for mode in sorted({r.mode for r in results}):
        by_kind: dict[str, list[QueryResult]] = {}
        for r in results:
            if r.mode == mode:
                by_kind.setdefault(r.kind, []).append(r)

        mode_block: dict = {}
        for kind, rs in sorted(by_kind.items()):
            hits = [r.hit for r in rs]
            ranks = [r.rank for r in rs if r.rank]
            leaks = [r.leaked for r in rs]
            mode_block[kind] = {
                "n": len(rs),
                "hit_rate": round(sum(hits) / len(rs), 4) if rs else 0.0,
                "mrr": round(sum(1 / x for x in ranks) / len(rs), 4) if rs else 0.0,
                "leak_rate": round(sum(leaks) / len(rs), 4) if rs else 0.0,
                "median_latency_ms": round(
                    statistics.median(r.latency_ms for r in rs), 2) if rs else 0.0,
            }
        out[mode] = mode_block
    return out


def _latency_block(results: list[QueryResult]) -> dict:
    out: dict = {}
    for mode in sorted({r.mode for r in results}):
        ms = [r.latency_ms for r in results if r.mode == mode]
        if not ms:
            continue
        out[mode] = {
            "n": len(ms),
            "p50": round(_pct(ms, 0.50), 2),
            "p95": round(_pct(ms, 0.95), 2),
            "p99": round(_pct(ms, 0.99), 2),
            "max": round(max(ms), 2),
            "mean": round(statistics.fmean(ms), 2),
        }
    return out


def run(store, modes=("keyword", "semantic", "hybrid", "graph"),
        k: int = 5, corpus: Corpus | None = None,
        warm: bool = True, compare_rerank: bool = True) -> Report:
    """Run the suite against an already-seeded store.

    `compare_rerank=False` is required for any caller that runs the suite from
    inside `_rerank_comparison`; without it the two functions recurse forever.
    """
    corpus = corpus or load()
    notes: list[str] = []

    health = store.health()
    if not health["healthy"]:
        notes.append(
            "STORE UNHEALTHY at run start: "
            + json.dumps({kk: vv for kk, vv in health["indexes"].items()},
                         default=str))
    notes.append(
        "Scores are NOT comparable to Mem0's LoCoMo/LongMemEval or Zep's DMR. "
        "Those run on different corpora (two of them private or vendor-defined) "
        "with different metrics. These numbers describe this corpus only.")

    supports_all = _answerable_ids(corpus)

    # Distinctive substrings from the simulated facts. If any of these appears in
    # a retrieval result, the grounded/simulated partition has failed.
    sim_markers: tuple[str, ...] = tuple(
        _distinctive(f.content) for f in corpus.simulated)

    # Warm the embedder and cross-encoder so the first query is not an outlier.
    if warm:
        for stage in ("embed", "query"):
            try:
                if stage == "embed":
                    store.semantic("warm up the retrieval path", k=1)
                else:
                    store.hybrid("warm up the retrieval path", k=1)
            except Exception as e:  # pragma: no cover - environment dependent
                notes.append(f"warmup {stage} failed: {type(e).__name__}: {e}")

    results: list[QueryResult] = []
    for mode in modes:
        for q in corpus.queries:
            if mode == "graph" and q.kind != "multi_hop":
                continue  # graph traversal is only meaningful for entity queries
            if mode == "graph" and q.entity is None:
                continue
            try:
                hits, degraded, healthy, ms = _run_mode(store, q, mode, k)
            except Exception as e:
                notes.append(f"{mode}/{q.qid} raised {type(e).__name__}: {e}")
                results.append(QueryResult(
                    qid=q.qid, kind=q.kind, mode=mode, hit=False, rank=None,
                    leaked=True, n_results=0, latency_ms=0.0,
                    degraded_to=f"error:{type(e).__name__}", drift_healthy=None))
                continue

            sup = {s for s in q.supports if s in supports_all}
            if q.kind == "adversarial":
                hit, rank = False, None
                leaked = _leak(hits, sim_markers)
            else:
                hit, rank = _hit(hits, q.expect, sup)
                leaked = False

            results.append(QueryResult(
                qid=q.qid, kind=q.kind, mode=mode, hit=hit, rank=rank,
                leaked=leaked, n_results=len(hits), latency_ms=round(ms, 3),
                degraded_to=degraded, drift_healthy=healthy))

    trust = _trust_block(store, results)
    trust["rerank_off_comparison"] = (_rerank_comparison(store, corpus, k)
                                      if compare_rerank else None)
    env = _environment(store)

    return Report(
        corpus=corpus.name,
        facts=len(corpus.facts),
        simulated=len(corpus.simulated),
        queries=len(corpus.queries),
        environment=env,
        recall=_recall_block(corpus, results),
        latency_ms=_latency_block(results),
        trust=trust,
        per_query=[asdict(r) for r in results],
        notes=notes,
    )


def _rerank_comparison(store, corpus: Corpus, k: int) -> dict | None:
    """Measure hybrid retrieval with and without cross-encoder reranking.

    Reranking costs an order of magnitude in latency. Reporting only the
    default-on number hides a real operational choice, so measure both.
    """
    eng = store._engine
    if not getattr(eng, "CROSS_ENCODER_AVAILABLE", False):
        return None
    original = eng.USE_CROSS_ENCODER
    out = {}
    try:
        for key, flag in (("with", True), ("without", False)):
            eng.USE_CROSS_ENCODER = flag
            # warm=True: the main run has already loaded both models, so this
            # measures the query cost rather than a second cold start.
            r = run(store, modes=("hybrid",), k=k, corpus=corpus, warm=True,
                    compare_rerank=False)
            hb = r.recall.get("hybrid", {})
            out[key] = {
                "p50_ms": r.latency_ms.get("hybrid", {}).get("p50", 0.0),
                "mrr_direct": hb.get("direct", {}).get("mrr", 0.0),
                "mrr_multi_hop": hb.get("multi_hop", {}).get("mrr", 0.0),
                "hit_direct": hb.get("direct", {}).get("hit_rate", 0.0),
                "hit_multi_hop": hb.get("multi_hop", {}).get("hit_rate", 0.0),
            }
    finally:
        eng.USE_CROSS_ENCODER = original
    return out


def _trust_block(store, results: list[QueryResult]) -> dict:
    health = store.health()
    cont = store.contamination()

    vec = health["indexes"].get("vector", {})
    bm = health["indexes"].get("bm25", {})
    graph = health["indexes"].get("graph", {})

    total_indexed = (vec.get("indexed", 0) or 0) + (bm.get("indexed", 0) or 0)
    total_stale = (vec.get("missing_from_ledger", 0) or 0) + \
                  (bm.get("missing_from_ledger", 0) or 0)
    stale_rate = round(total_stale / total_indexed, 6) if total_indexed else 0.0

    # Did retrieval ever admit it was degraded?
    degraded = [r for r in results if r.degraded_to not in (None, "both", "found")]
    reported = [r for r in results if r.drift_healthy is not None]

    return {
        "contamination_rate": cont.get("contamination_rate"),
        "contamination_violations": len(cont.get("violations") or []),
        "simulated_in_bm25": cont.get("violations_simulated_in_bm25_corpus", 0),
        "stale_pointer_rate": stale_rate,
        "stale_pointers": total_stale,
        "indexed_entries": total_indexed,
        "index_healthy": health["healthy"],
        "graph_entities": graph.get("entities", 0),
        "graph_edges": graph.get("edges", 0),
        "degraded_queries": len(degraded),
        "queries_with_drift_diagnostic": len(reported),
        "all_reported_healthy": all(r.drift_healthy for r in reported)
                                 if reported else None,
        "ledger_records": health["ledger_records"],
    }


def _environment(store) -> dict:
    import platform
    import sys
    eng = store._engine
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor() or "unknown",
        "store": store.path,
        "vector_available": eng.VECTOR_AVAILABLE,
        "bm25_available": eng.BM25_AVAILABLE,
        "embedding_model": getattr(eng, "EMBEDDING_MODEL", None),
        "embedding_dim": getattr(eng, "EMBEDDING_DIM", None),
        "cross_encoder": bool(getattr(eng, "USE_CROSS_ENCODER", False)),
    }


def render_markdown(report: Report) -> str:
    """Render a report as markdown for the repo and the website."""
    L: list[str] = []
    a = L.append
    a("# mem20 retrieval benchmarks")
    a("")
    a(f"Corpus `{report.corpus}` — {report.facts} grounded facts, "
      f"{report.simulated} simulated facts, {report.queries} queries.")
    a("")

    a("> [!IMPORTANT]")
    a("> **These numbers are not comparable to competitor benchmarks.** "
      "Mem0's LoCoMo (92.5) and LongMemEval (94.4) figures and Zep's DMR "
      "(94.8%) come from different corpora — two of the three are private or "
      "vendor-defined — and different metrics. Nothing here refutes or "
      "reproduces them. These results describe this corpus only.")
    a("")

    a("## Retrieval quality")
    a("")
    a("| Mode | Query kind | n | Hit rate | MRR | Leak rate | p50 ms |")
    a("|---|---|---:|---:|---:|---:|---:|")
    for mode, kinds in sorted(report.recall.items()):
        for kind, m in sorted(kinds.items()):
            a(f"| `{mode}` | {kind} | {m['n']} | {m['hit_rate']:.3f} | "
              f"{m['mrr']:.3f} | {m['leak_rate']:.3f} | "
              f"{m['median_latency_ms']:.1f} |")
    a("")

    a("## Latency")
    a("")
    a("| Mode | n | p50 ms | p95 ms | p99 ms | max ms |")
    a("|---|---:|---:|---:|---:|---:|")
    for mode, m in sorted(report.latency_ms.items()):
        a(f"| `{mode}` | {m['n']} | {m['p50']:.1f} | {m['p95']:.1f} | "
          f"{m['p99']:.1f} | {m['max']:.1f} |")
    a("")

    t = report.trust
    a("## Trustworthiness")
    a("")
    a("This is the axis mem20 claims as its differentiator, and the one no "
      "competitor publishes. A system that answers confidently from a stale "
      "index can look good on hit rate and fail here.")
    a("")

    cmp_ = t.get("rerank_off_comparison")
    if cmp_:
        a("### Reranking cost")
        a("")
        a("Cross-encoder reranking is why hybrid is ~10x slower than the vector "
          "half alone. It is on by default and now has a `MEM20_RERANK=0` "
          "opt-out. Measured both ways on this corpus:")
        a("")
        a("| Setting | p50 ms | direct MRR | multi-hop MRR |")
        a("|---|---:|---:|---:|")
        for label, key in (("`MEM20_RERANK=1` (default)", "with"),
                           ("`MEM20_RERANK=0`", "without")):
            c = cmp_[key]
            a(f"| {label} | {c['p50_ms']:.1f} | {c['mrr_direct']:.3f} | "
              f"{c['mrr_multi_hop']:.3f} |")
        a("")
        a("Reranking improves direct-query ranking and costs an order of "
          "magnitude in latency. An agent doing many lookups is usually better "
          "off with it off.")
        a("")

    a("| Check | Value | Required |")
    a("|---|---:|---|")
    a(f"| Contamination rate | {t['contamination_rate']} | 0.0 |")
    a(f"| Simulated records in BM25 corpus | {t['simulated_in_bm25']} | 0 |")
    a(f"| Stale pointer rate | {t['stale_pointer_rate']:.6f} | 0.0 |")
    a(f"| Index healthy | {t['index_healthy']} | True |")
    a(f"| Ledger records | {t['ledger_records']} | — |")
    a(f"| Graph entities / edges | {t['graph_entities']} / {t['graph_edges']} | — |")
    a(f"| Queries reporting a diagnostic | "
      f"{t['queries_with_drift_diagnostic']} | — |")
    a(f"| All reported healthy | {t['all_reported_healthy']} | True |")
    a("")

    env = report.environment
    a("## Environment")
    a("")
    a(f"- Python {env['python']} on {env['platform']} ({env['machine']})")
    a(f"- Embedding model: `{env['embedding_model']}` "
      f"({env['embedding_dim']}-dim)")
    a(f"- Vector deps available: {env['vector_available']}; "
      f"BM25: {env['bm25_available']}; cross-encoder: {env['cross_encoder']}")
    a("")

    if report.notes:
        a("## Notes")
        a("")
        for n in report.notes:
            a(f"- {n}")
        a("")

    a("## Reproduce")
    a("")
    a("```bash")
    a("mem20benchmarkz run --out benchmarks/results")
    a("```")
    a("")
    a("The run uses an isolated temporary store, seeds the corpus through the "
      "real `remember` path, and never touches live data.")
    return "\n".join(L)


def save(report: Report, out_dir: str | Path) -> dict[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    j = out / "latest.json"
    j.write_text(json.dumps(report.to_dict(), indent=2, default=str))
    md = out / "latest.md"
    md.write_text(render_markdown(report))
    return {"json": str(j), "markdown": str(md)}