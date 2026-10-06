"""Command-line interface for mem20ocaskz."""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys

from .engine import (
    THEMES,
    audit,
    connect,
    default_db_path,
    fingerprint,
    render_index,
    SCHEMA_USER_PROMPTS,
)

EXIT_CLEAN = 0
EXIT_FINDINGS = 1
EXIT_ERROR = 2

DEFAULT_INDEX = "/opt/mem20/roadmaps/opencode-feature-asks.md"


def _print_human(result, limit: int | None, show_quotes: bool) -> None:
    print(f"database : {result.db_path}")
    print(f"size     : {result.db_size_after:,} bytes")
    print(f"unchanged: {result.db_unchanged}")
    print(f"sessions : {result.session_count} scanned, "
          f"{result.sessions_with_asks} with asks")
    print(f"prompts  : {result.prompts_total:,} read, "
          f"{result.prompts_noise:,} excluded as agent-generated noise, "
          f"{len(result.asks):,} classified as asks")
    print()
    print("kinds:")
    for kind, n in sorted(result.kind_counts.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {kind:22} {n}")
    print()
    print("themes:")
    for theme, n in sorted(result.theme_counts.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {theme:22} {n}")
    print()
    shown = result.asks if limit is None else result.asks[:limit]
    if len(shown) != len(result.asks):
        print(f"showing first {len(shown)} of {len(result.asks)} asks")
        print()
    for a in shown:
        themes = ",".join(a.themes) or "-"
        kinds = ",".join(a.kinds) or "-"
        print(f"[{a.date}] {a.title}  ({themes} | {kinds})")
        print(f"  session {a.prompt.session_id}")
        if show_quotes:
            print(f"  > {a.quote}")


def cmd_scan(args) -> int:
    try:
        result = audit(db_path=args.db, limit=args.limit)
    except (OSError, sqlite3.Error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    if args.json:
        print(json.dumps(result.as_dict(), indent=2))
    else:
        _print_human(result, args.show, not args.brief)
    return EXIT_CLEAN


def cmd_search(args) -> int:
    try:
        result = audit(db_path=args.db, limit=args.limit)
    except (OSError, sqlite3.Error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    needle = re.compile(args.term, re.I)
    hits = [
        a for a in result.asks
        if needle.search(a.quote)
        or any(needle.search(t) for t in a.themes)
        or needle.search(a.title)
    ]
    if args.json:
        print(json.dumps([
            {
                "session_id": a.prompt.session_id,
                "date": a.date,
                "title": a.title,
                "themes": list(a.themes),
                "kinds": list(a.kinds),
                "quote": a.quote,
            }
            for a in hits
        ], indent=2))
    else:
        print(f"{len(hits)} match(es) for {args.term!r} "
              f"of {len(result.asks)} asks in {result.db_path}")
        for a in hits:
            print(f"[{a.date}] {a.title}  ({','.join(a.themes) or '-'})")
            print(f"  session {a.prompt.session_id}")
            print(f"  > {a.quote}")
    return EXIT_CLEAN if hits else EXIT_FINDINGS


def cmd_themes(args) -> int:
    print("theme taxonomy (patterns are auditable in mem20ocaskz/audit.py):")
    for name, pats in sorted(THEMES.items()):
        print(f"  {name}")
        for p in pats:
            print(f"      {p}")
    return EXIT_CLEAN


def cmd_index(args) -> int:
    out = os.path.abspath(args.out)
    db = os.path.abspath(args.db or default_db_path())
    if out == db or out.startswith(os.path.dirname(db) + os.sep):
        print(f"refusing to write inside the opencode data directory: {out}",
              file=sys.stderr)
        return EXIT_ERROR
    try:
        result = audit(db_path=args.db, limit=args.limit)
    except (OSError, sqlite3.Error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    text = render_index(result, max_quote=args.max_quote)
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, out)
    print(f"wrote  : {out}")
    print(f"asks   : {len(result.asks):,} from {result.prompts_total:,} prompts")
    print(f"sessions: {result.sessions_with_asks} of {result.session_count}")
    print(f"db unchanged: {result.db_unchanged}")
    return EXIT_CLEAN if result.db_unchanged else EXIT_FINDINGS


def cmd_verify(args) -> int:
    db = args.db or default_db_path()
    failures: list[str] = []
    try:
        before = fingerprint(db)
        counts = []
        for _ in range(args.repeat):
            con = connect(db)
            try:
                counts.append(con.execute(
                    "SELECT COUNT(*) FROM ("
                    + SCHEMA_USER_PROMPTS.rstrip().rstrip(";")
                    + ")"
                ).fetchone()[0])
            finally:
                con.close()
        result = audit(db_path=db, limit=args.limit)
        after = fingerprint(db)
    except (OSError, sqlite3.Error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    print(f"database        : {db}")
    print(f"size            : {before[0]:,} bytes")
    print(f"user prompts    : {result.prompts_total:,}")
    print(f"repeat counts   : {counts}")
    print(f"stable          : {len(set(counts)) == 1}")
    print(f"db unchanged    : {before == after}")
    print(f"read-only mode  : mode=ro (no write statement is ever issued)")

    if len(set(counts)) != 1:
        failures.append(f"prompt count unstable across runs: {counts}")
    if before != after:
        failures.append(f"database changed during audit: {before} -> {after}")
    if result.prompts_total != counts[-1]:
        failures.append(
            f"audit read {result.prompts_total} prompts but direct count "
            f"is {counts[-1]}"
        )
    if failures:
        print()
        print("FAIL:")
        for f in failures:
            print(f"  - {f}")
        return EXIT_FINDINGS
    print()
    print("PASS - count stable, database untouched")
    return EXIT_CLEAN


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mem20ocaskz",
        description=(
            "Mine opencode's session database for the feature requests Jayson "
            "actually made. Read-only: never mutates a session."
        ),
    )
    parser.add_argument("--db", default=None,
                        help=f"session database (default {default_db_path()})")
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="audit and report every feature ask")
    scan.add_argument("--json", action="store_true", help="machine-readable output")
    scan.add_argument("--limit", type=int, default=None,
                      help="only read the first N user prompts")
    scan.add_argument("--show", type=int, default=None,
                      help="print at most N asks after the summary")
    scan.add_argument("--brief", action="store_true",
                      help="summary only, no quotes")
    scan.set_defaults(func=cmd_scan)

    search = sub.add_parser("search", help="find asks matching a term or theme")
    search.add_argument("term")
    search.add_argument("--json", action="store_true")
    search.add_argument("--limit", type=int, default=None)
    search.set_defaults(func=cmd_search)

    themes = sub.add_parser("themes", help="print the theme taxonomy")
    themes.set_defaults(func=cmd_themes)

    index = sub.add_parser("index", help="write the curated markdown index")
    index.add_argument("--out", default=DEFAULT_INDEX)
    index.add_argument("--limit", type=int, default=None)
    index.add_argument("--max-quote", type=int, default=400)
    index.set_defaults(func=cmd_index)

    verify = sub.add_parser(
        "verify", help="prove the count is stable and the database untouched")
    verify.add_argument("--repeat", type=int, default=3)
    verify.add_argument("--limit", type=int, default=None)
    verify.set_defaults(func=cmd_verify)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())