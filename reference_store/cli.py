#!/usr/bin/env python3
"""00_reference_store CLI -- inspect and operate the fountain.

Usage:
    python -m reference_store.cli --root <path> stats
    python -m reference_store.cli --root <path> proof
    python -m reference_store.cli --root <path> push --category parse --kind failure --text "..."
    python -m reference_store.cli --root <path> search --q "<needle>" [--category x] [--kind x]
    python -m reference_store.cli --root <path> snapshot --ring ring_a
    python -m reference_store.cli --root <path> get --cid <cid>
"""

from __future__ import annotations

import argparse
import json
import sys

from .store import ReferenceStore

DEFAULT_ROOT = "/opt/mem20/reference_store/data"


def _store(args) -> ReferenceStore:
    return ReferenceStore(args.root)


def _json(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def cmd_stats(args) -> None:
    _json(_store(args).stats())


def cmd_proof(args) -> None:
    _json(_store(args).proof())


def cmd_push(args) -> None:
    store = _store(args)
    result = store.push(
        category=args.category,
        kind=args.kind,
        text=args.text,
        origin_ring=args.origin_ring,
        actor=args.actor,
        ring=args.ring,
        energy=args.energy,
        hops=args.hops,
        confidence=args.confidence,
    )
    _json(result)


def cmd_search(args) -> None:
    store = _store(args)
    lessons = store.search(
        needle=args.q or "",
        category=args.category or "",
        kind=args.kind or "",
        origin_ring=args.origin_ring or "",
        min_confidence=args.min_confidence,
        limit=args.limit,
    )
    _json([l.to_dict() for l in lessons])


def cmd_get(args) -> None:
    lesson = _store(args).get(args.cid)
    if lesson is None:
        print(f"not found: {args.cid}")
        sys.exit(1)
    _json(lesson.to_dict())


def cmd_snapshot(args) -> None:
    snap = _store(args).snapshot(args.ring)
    _json(snap.to_dict())


def cmd_sweep(args) -> None:
    store = _store(args)
    jsonl = os.path.join(args.root, "index.jsonl")
    from .index import JsonlIndex

    idx = JsonlIndex(jsonl)
    idx.build(store.all())
    _json({"indexed": len(store.all()), "index_path": jsonl})


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="00_reference_store", description="MALIC braid fountain")
    parser.add_argument("--root", default=DEFAULT_ROOT, help="store root directory")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("stats")
    p.set_defaults(fn=cmd_stats)

    p = sub.add_parser("proof")
    p.set_defaults(fn=cmd_proof)

    p = sub.add_parser("push")
    p.add_argument("--category", required=True)
    p.add_argument("--kind", required=True, choices=["failure", "success"])
    p.add_argument("--text", required=True)
    p.add_argument("--origin-ring", default="ring_unknown")
    p.add_argument("--actor", default="cli")
    p.add_argument("--ring", default="")
    p.add_argument("--energy", type=float, default=1.0)
    p.add_argument("--hops", type=int, default=1)
    p.add_argument("--confidence", type=float, default=0.7)
    p.set_defaults(fn=cmd_push)

    p = sub.add_parser("search")
    p.add_argument("--q", default="")
    p.add_argument("--category", default="")
    p.add_argument("--kind", default="")
    p.add_argument("--origin-ring", default="")
    p.add_argument("--min-confidence", type=float, default=0.0)
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(fn=cmd_search)

    p = sub.add_parser("get")
    p.add_argument("--cid", required=True)
    p.set_defaults(fn=cmd_get)

    p = sub.add_parser("snapshot")
    p.add_argument("--ring", required=True)
    p.set_defaults(fn=cmd_snapshot)

    p = sub.add_parser("sweep")
    p.set_defaults(fn=cmd_sweep)

    args = parser.parse_args(argv)
    args.fn(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
