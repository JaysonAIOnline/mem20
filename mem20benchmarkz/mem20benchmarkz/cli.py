"""CLI for mem20benchmarkz.

    mem20benchmarkz run --out benchmarks/results     # full suite
    mem20benchmarkz drift --out benchmarks/results   # trustworthiness only
    mem20benchmarkz render benchmarks/results        # re-render from latest.json

`run` seeds a throwaway store, so it cannot touch live data. That isolation is
the point: a benchmark that read the production ledger would be measuring a
moving target and could mutate it.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
for _p in (str(_REPO_ROOT / "mem20api"), str(_REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from .bench import Report, render_markdown, run, save  # noqa: E402
from .corpus import load  # noqa: E402


def _seed(store, corpus) -> None:
    """Write the corpus through the real write path.

    Deliberately not a direct ledger append: the indexes, the graph, and the
    contamination tags are all built by `remember`, and bypassing them would
    benchmark a store state the system cannot actually produce.
    """
    for f in corpus.facts:
        store.remember(f.topic, f.content, tags=list(f.tags),
                       priority=f.priority)
    for f in corpus.simulated:
        store.remember_simulated(f.topic, f.content,
                                 scenario="benchmark adversarial probe",
                                 sim_type="counterfactual")


def cmd_run(args) -> int:
    from mem20api import open_store

    corpus = load()
    tmp = tempfile.mkdtemp(prefix="mem20-bench-")
    print(f"isolated store: {tmp}", file=sys.stderr)

    with open_store(tmp) as store:
        _seed(store, corpus)
        h = store.health()
        if not h["healthy"]:
            print("ERROR: freshly seeded store is unhealthy; not publishing "
                  "numbers from a broken index", file=sys.stderr)
            print(json.dumps(h, indent=2, default=str), file=sys.stderr)
            return 2

        report = run(store, k=args.k, corpus=corpus,
                   compare_rerank=not args.no_rerank_compare)

    paths = save(report, args.out)
    print(render_markdown(report))
    print(f"\nwrote {paths['json']}", file=sys.stderr)
    print(f"wrote {paths['markdown']}", file=sys.stderr)

    t = report.trust
    bad = []
    if t["contamination_rate"] != 0.0:
        bad.append(f"contamination_rate={t['contamination_rate']}")
    if t["stale_pointer_rate"] != 0.0:
        bad.append(f"stale_pointer_rate={t['stale_pointer_rate']}")
    for mode, kinds in report.recall.items():
        for kind, m in kinds.items():
            if kind == "adversarial" and m["leak_rate"] != 0.0:
                bad.append(f"{mode} leaked {m['leak_rate']} of adversarial queries")
    if bad:
        print("\nFAILED TRUST CHECKS:", file=sys.stderr)
        for b in bad:
            print(f"  - {b}", file=sys.stderr)
        return 1
    print("\nall trust checks passed", file=sys.stderr)
    return 0


def cmd_drift(args) -> int:
    """Trustworthiness of a store, including a deliberate induced failure.

    Corrupts an index in a throwaway copy to prove the diagnostics fire. A
    trustworthiness claim that is never demonstrated under failure is just a
    number.
    """
    from mem20api import open_store

    corpus = load()
    tmp = tempfile.mkdtemp(prefix="mem20-drift-")
    with open_store(tmp) as store:
        _seed(store, corpus)
        before = store.health()
        print("baseline healthy:", before["healthy"])

        ledger = Path(tmp) / "ledger.jsonl"
        lines = ledger.read_text().splitlines()
        ledger.write_text("\n".join(lines[: len(lines) // 2]) + "\n")

        after = store.health()
        print("after truncation healthy:", after["healthy"])
        v = after["indexes"]["vector"]
        print(f"  stale pointers: {v['missing_from_ledger']} of {v['indexed']}")

        r = store.semantic("what build is prod on", k=3)
        print("  semantic healthy flag:", r["healthy"])
        print("  reported:", json.dumps(r["diagnostic"], default=str))

        ok = (after["healthy"] is False
              and v["missing_from_ledger"] > 0
              and r["healthy"] is False)
        print("\ndrift detection:", "PASS" if ok else "FAIL")
        return 0 if ok else 1


def cmd_render(args) -> int:
    src = Path(args.dir) / "latest.json"
    if not src.is_file():
        print(f"no results at {src}; run mem20benchmarkz run first",
              file=sys.stderr)
        return 2
    data = json.loads(src.read_text())
    r = Report(**{k: v for k, v in data.items()})
    md = render_markdown(r)
    out = Path(args.dir) / "latest.md"
    out.write_text(md)
    print(f"wrote {out}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="mem20benchmarkz",
        description="mem20 retrieval benchmarks: quality, latency, trustworthiness.")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run the full suite on an isolated store")
    r.add_argument("--out", default="benchmarks/results",
                   help="output directory for latest.json / latest.md")
    r.add_argument("-k", type=int, default=5, help="results per query")
    r.add_argument("--no-rerank-compare", action="store_true",
                   help="skip the with/without-rerank latency comparison")

    d = sub.add_parser("drift",
                       help="prove index-drift diagnostics fire under induced failure")
    d.add_argument("--out", default="benchmarks/results")

    n = sub.add_parser("render", help="re-render markdown from latest.json")
    n.add_argument("dir", nargs="?", default="benchmarks/results")

    args = p.parse_args(argv)
    return {"run": cmd_run, "drift": cmd_drift, "render": cmd_render}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())