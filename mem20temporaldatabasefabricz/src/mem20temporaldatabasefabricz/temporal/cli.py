"""Command line for the bi-temporal store.

    put       assert a belief
    correct   supersede the current belief, keeping the old one queryable
    retract   stop believing, without asserting a replacement
    expire    record that the claim itself stopped being true
    get       query one slice (as-of join)
    slices    all four slices at one instant
    history   every version of an attribute, oldest first
    explain   why the engine answers what it answers
    export    deterministic dump of the whole store
    verify    re-derive the event hash chain
    ingest    build intervals from mem20's memory ledger
    selftest  prove the engine's core claims on a throwaway store

Output is JSON so it composes; errors go to stderr and set a non-zero exit.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile

from .engine import BiTemporalEngine, InvariantError
from .ledger_adapter import build_engine, derive_intervals
from .store import ChainError, TemporalStore

DEFAULT_DB = os.environ.get(
    "MEM20_TEMPORAL_DB", os.path.expanduser("~/.mem20/temporal/temporal.db"))
LEDGER = os.environ.get(
    "MEM20_LEDGER_PATH", os.path.expanduser("~/.mem20/store/ledger.jsonl"))


def _emit(payload: dict, as_json: bool = True) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    else:
        for version in payload.get("versions", []):
            print(f"{version['value_ref']:>24}  valid[{version['valid_from']} .. "
                  f"{version['valid_to'] or 'open'})  known[{version['known_from']} .. "
                  f"{version['known_to'] or 'open'})")


def _load_ledger_rows(path: str) -> list[dict]:
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"ledger not found at {path}. Set MEM20_LEDGER_PATH, or run "
            f"`mem20temporaldatabasefabricz ingest --ledger <path>`.")
    rows = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def cmd_put(args, store):
    engine = BiTemporalEngine(store)
    interval = engine.assert_belief(
        args.subject, args.attribute, args.value, valid_from=args.valid_from,
        known_at=args.known_at)
    _emit({"recorded": interval.to_dict()})


def cmd_correct(args, store):
    engine = BiTemporalEngine(store)
    interval = engine.correct(
        args.subject, args.attribute, args.value, known_at=args.known_at,
        valid_from=args.valid_from)
    _emit({"corrected": interval.to_dict(),
           "full_chain": [v.to_dict() for v in engine.history(args.subject)]})


def cmd_retract(args, store):
    engine = BiTemporalEngine(store)
    closed = engine.retract(args.subject, args.attribute, known_at=args.known_at,
                            reason=args.reason)
    _emit({"retracted": len(closed), "closed": [v.to_dict() for v in closed]})


def cmd_expire(args, store):
    engine = BiTemporalEngine(store)
    interval = engine.expire(args.subject, args.attribute, args.valid_to,
                             reason=args.reason)
    _emit({"expired": interval.to_dict()})


def cmd_get(args, store):
    engine = BiTemporalEngine(store)
    result = engine.query(args.subject, valid_at=args.valid_at,
                          known_at=args.known_at, attribute=args.attribute)
    _emit(result.to_dict(), as_json=not args.text)


def cmd_slices(args, store):
    engine = BiTemporalEngine(store)
    _emit(engine.four_slices(args.subject, args.instant, args.attribute))


def cmd_history(args, store):
    engine = BiTemporalEngine(store)
    chain = engine.history(args.subject, args.attribute)
    _emit({"subject": args.subject, "count": len(chain),
           "versions": [v.to_dict() for v in chain]})


def cmd_explain(args, store):
    engine = BiTemporalEngine(store)
    _emit(engine.explain(args.subject, valid_at=args.valid_at,
                         known_at=args.known_at, attribute=args.attribute))


def cmd_export(args, store):
    engine = BiTemporalEngine(store)
    payload = engine.export(args.subject)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, default=str)
        _emit({"exported_to": args.out, "versions": payload["version_count"]})
    else:
        _emit(payload)


def cmd_verify(args, store):
    _emit(store.verify_chain())


def cmd_ingest(args, store):
    rows = _load_ledger_rows(args.ledger)
    engine = build_engine(store, rows)
    _emit({
        "ledger": args.ledger,
        "ledger_rows": len(rows),
        "intervals_derived": len(derive_intervals(rows)),
        "versions_in_store": engine.store.count(),
        "chain": engine.store.verify_chain(),
    })


def cmd_selftest(args, store):
    """Prove the core claims on a throwaway store. Touches nothing real."""
    from datetime import datetime, timezone, timedelta
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def at(hours: int) -> str:
        return (base + timedelta(hours=hours)).isoformat()

    checks: list[tuple[str, bool]] = []
    with tempfile.TemporaryDirectory() as tmp:
        probe = TemporalStore(os.path.join(tmp, "selftest.db"))
        engine = BiTemporalEngine(probe)

        engine.assert_belief("svc.port", "value", "8080", known_at=at(0))
        checks.append(("assertion records an open belief",
                       len(engine.query("svc.port")) == 1))

        engine.correct("svc.port", "value", "9090", known_at=at(6))
        checks.append(("correction preserves the pre-correction truth",
                       engine.query("svc.port", valid_at=at(1),
                                    known_at=at(1)).value_refs() == ["8080"]))
        checks.append(("current view shows the correction",
                       engine.query("svc.port").value_refs() == ["9090"]))
        checks.append(("believed-then view excludes the later correction",
                       engine.query("svc.port", known_at=at(1)).value_refs() == ["8080"]))
        checks.append(("half-open: the correction instant belongs to the correction",
                       engine.query("svc.port", valid_at=at(6),
                                    known_at=at(6)).value_refs() == ["9090"]))
        checks.append(("nothing is deleted",
                       [v.value_ref for v in engine.history("svc.port")] ==
                       ["8080", "9090"]))

        engine.assert_belief("late", "value", "learned-late",
                             valid_from=at(0), known_at=at(9))
        checks.append(("as-of join finds the late-arriving fact",
                       engine.query("late", valid_at=at(1)).value_refs() == ["learned-late"]))

        engine.retract("svc.port", "value", known_at=at(12), reason="selftest")
        latest = engine.history("svc.port")[-1]
        checks.append(("retract closes belief but not truth",
                       latest.known_to == at(12) and latest.valid_to is None))

        # Probe the double-assertion guard on a subject that still holds an
        # open belief. svc.port was retracted above, so asserting there is
        # legal - that is the point of retract.
        try:
            engine.assert_belief("late", "value", "x", known_at=at(13))
            checks.append(("double assertion refused", False))
        except InvariantError:
            checks.append(("double assertion refused", True))

        engine.assert_belief("svc.port", "value", "reasserted", known_at=at(13))
        checks.append(("re-asserting after a retract is legal",
                       engine.query("svc.port").value_refs() == ["reasserted"]))

        probe._conn.execute("UPDATE events SET payload='{}' WHERE seq=1")
        probe._conn.commit()
        try:
            probe.verify_chain()
            checks.append(("tampering detected", False))
        except ChainError:
            checks.append(("tampering detected", True))
        probe.close()

    failed = [name for name, ok in checks if not ok]
    _emit({"checks": len(checks), "passed": len(checks) - len(failed),
           "failed": failed, "ok": not failed,
           "results": [{"check": name, "ok": ok} for name, ok in checks]})
    return 1 if failed else 0


def cmd_serve(args, store):
    from .http import serve
    if store is not None:
        store.close()
        store = None
    serve(host=args.host, port=args.port)
    return 0


HANDLERS = {
    "put": cmd_put, "correct": cmd_correct, "retract": cmd_retract,
    "expire": cmd_expire, "get": cmd_get, "slices": cmd_slices,
    "history": cmd_history, "explain": cmd_explain, "export": cmd_export,
    "verify": cmd_verify, "ingest": cmd_ingest, "selftest": cmd_selftest,
    "serve": cmd_serve,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mem20temporaldatabasefabricz",
        description="Bi-temporal memory: what was true, and what we believed, when.")
    parser.add_argument("--db", default=DEFAULT_DB,
                        help=f"SQLite store path (default: {DEFAULT_DB})")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("put", help="assert a belief")
    p.add_argument("subject")
    p.add_argument("attribute")
    p.add_argument("value")
    p.add_argument("--valid-from", dest="valid_from")
    p.add_argument("--known-at", dest="known_at")

    p = sub.add_parser("correct", help="supersede, keeping the old belief queryable")
    p.add_argument("subject")
    p.add_argument("attribute")
    p.add_argument("value")
    p.add_argument("--known-at", dest="known_at")
    p.add_argument("--valid-from", dest="valid_from")

    p = sub.add_parser("retract", help="stop believing, assert no replacement")
    p.add_argument("subject")
    p.add_argument("attribute")
    p.add_argument("--known-at", dest="known_at")
    p.add_argument("--reason", default="retracted")

    p = sub.add_parser("expire", help="record that the claim stopped being true")
    p.add_argument("subject")
    p.add_argument("attribute")
    p.add_argument("valid_to", metavar="VALID_TO")
    p.add_argument("--reason", default="no_longer_true")

    p = sub.add_parser("get", help="query one bi-temporal slice")
    p.add_argument("subject")
    p.add_argument("--valid-at", dest="valid_at")
    p.add_argument("--known-at", dest="known_at")
    p.add_argument("--attribute")
    p.add_argument("--text", action="store_true", help="human-readable lines")

    p = sub.add_parser("slices", help="all four slices at one instant")
    p.add_argument("subject")
    p.add_argument("instant")
    p.add_argument("--attribute")

    p = sub.add_parser("history", help="every version, oldest first")
    p.add_argument("subject")
    p.add_argument("--attribute")

    p = sub.add_parser("explain", help="why the engine answers what it answers")
    p.add_argument("subject")
    p.add_argument("--valid-at", dest="valid_at")
    p.add_argument("--known-at", dest="known_at")
    p.add_argument("--attribute")

    p = sub.add_parser("export", help="deterministic dump")
    p.add_argument("subject", nargs="?")
    p.add_argument("--out")

    sub.add_parser("verify", help="re-derive the event hash chain")

    p = sub.add_parser("ingest", help="build intervals from mem20's memory ledger")
    p.add_argument("--ledger", default=LEDGER)

    sub.add_parser("selftest", help="prove the core claims on a throwaway store")

    p = sub.add_parser("serve", help="run the HTTP query surface")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8791)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = None
    try:
        # selftest must never touch the real store, not even to read it.
        if args.command == "selftest":
            return cmd_selftest(args, None)
        store = TemporalStore(args.db)
        return HANDLERS[args.command](args, store) or 0
    except (InvariantError, ChainError, ValueError, FileNotFoundError) as exc:
        print(json.dumps({"error": type(exc).__name__, "detail": str(exc)}),
              file=sys.stderr)
        return 2
    finally:
        if store is not None:
            store.close()


if __name__ == "__main__":
    raise SystemExit(main())