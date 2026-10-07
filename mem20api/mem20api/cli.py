"""CLI for mem20api: health checks and one-off queries without writing code."""
from __future__ import annotations

import argparse
import json
import sys

from .api import EngineNotFound, StoreError, open_store


def _cmd_health(args) -> int:
    try:
        with open_store(args.store) as s:
            h = s.health()
    except (EngineNotFound, StoreError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    print(f"store: {h['store']}")
    print(f"ledger records: {h['ledger_records']}")
    print()
    for key, idx in h["indexes"].items():
        if not idx.get("present"):
            print(f"  {key:8} ABSENT   (run rebuild)")
            continue
        state = "ok" if idx.get("healthy") else "DRIFTED"
        bits = []
        if "resolvable" in idx:
            bits.append(f"{idx['resolvable']}/{idx['indexed']} resolvable")
        if idx.get("missing_from_ledger"):
            bits.append(f"{idx['missing_from_ledger']} stale pointers")
        if "entities" in idx:
            bits.append(f"{idx['entities']} entities, {idx.get('edges', 0)} edges")
        if idx.get("meta_matches_index") is False:
            bits.append("metadata/index count mismatch")
        print(f"  {key:8} {state:8} {', '.join(bits)}")

    print()
    print("overall:", "healthy" if h["healthy"] else "NEEDS REBUILD")
    if not h["healthy"]:
        print("stale pointers mean search matches records that no longer exist")
        print("fix with: mem20-api-health rebuild")
    return 0 if h["healthy"] else 1


def _cmd_rebuild(args) -> int:
    try:
        with open_store(args.store) as s:
            for which, msg in s.rebuild(args.which).items():
                print(f"{which}: {msg}")
            h = s.health()
    except (EngineNotFound, StoreError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0 if h["healthy"] else 1


def _cmd_contamination(args) -> int:
    try:
        with open_store(args.store) as s:
            c = s.contamination()
    except (EngineNotFound, StoreError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(json.dumps(c, indent=2, default=str))
    return 0 if c.get("contamination_rate") == 0.0 else 1


def _cmd_query(args) -> int:
    try:
        with open_store(args.store) as s:
            if args.mode == "semantic":
                r = s.semantic(args.query, k=args.k)
                diag, hits = r["diagnostic"], r["hits"]
            elif args.mode == "hybrid":
                r = s.hybrid(args.query, k=args.k)
                diag, hits = {"degraded_to": r["degraded_to"]}, r["hits"]
            else:
                r = s.graph(args.query, hops=args.k)
                if not r.get("found"):
                    print(f"miss: {r.get('error')}")
                    return 1
                print(f"start: {r['start']} "
                      f"({r['entity_count']} entities, {r['fact_count']} facts)")
                for e in r["entities"]:
                    print(f"  hop {e['hop']}: {e['entity']} "
                          f"({e['fact_count']} facts)")
                for f in r["facts"]:
                    print(f"  [{f['topic']}] {f['content'][:160]}")
                return 0
    except (EngineNotFound, StoreError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if diag:
        print(f"diagnostic: {json.dumps(diag, default=str)}", file=sys.stderr)
    if not hits:
        print("no hits")
        return 1
    for h in hits:
        print(f"[{h.get('score', 0):.4f}] [{h['topic']}] {h['content'][:200]}")
    return 0


def _cmd_stats(args) -> int:
    try:
        with open_store(args.store) as s:
            st = s.stats()
    except (EngineNotFound, StoreError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    st.pop("health", None)
    print(json.dumps(st, indent=2, default=str))
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="mem20-api-health",
        description="mem20 store health, contamination audit, and queries.")
    p.add_argument("--store", default=None,
                   help="store path (default: $MEM20_STORE_PATH, else ~/.mem20/store)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("health", help="index/ledger agreement; exits 1 if drifted")
    r = sub.add_parser("rebuild", help="rebuild derived indexes from the ledger")
    r.add_argument("which", nargs="?", default="all",
                   choices=["all", "vector", "bm25", "graph"])
    sub.add_parser("contamination", help="grounded/simulated separation audit")
    st = sub.add_parser("stats", help="record and topic counts")
    q = sub.add_parser("query", help="run one retrieval query")
    q.add_argument("query")
    q.add_argument("--mode", default="hybrid",
                   choices=["semantic", "hybrid", "graph"])
    q.add_argument("-k", type=int, default=5,
                   help="results, or hops when --mode graph")

    args = p.parse_args(argv)
    return {
        "health": _cmd_health,
        "rebuild": _cmd_rebuild,
        "contamination": _cmd_contamination,
        "query": _cmd_query,
        "stats": _cmd_stats,
    }[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())