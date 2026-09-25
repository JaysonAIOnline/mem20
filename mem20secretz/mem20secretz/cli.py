"""Command-line interface for mem20secretz."""

from __future__ import annotations

import argparse
import json
import sys

from .sweep import (
    DEFAULT_ROOT,
    DEFAULT_STORE,
    SECRET_CRIT,
    SECRET_HIGH,
    SECRET_INFO,
    sweep,
)

EXIT_CLEAN = 0
EXIT_FINDINGS = 1
EXIT_ERROR = 2


def _print_human(result) -> None:
    print(f"root  : {result.root}")
    print(f"store : {result.store}")
    print(f"hunted: {result.values_hunted} store values")
    print(f"scanned: {result.files_scanned} files")
    print()

    if not result.findings:
        print("CLEAN - no store value found outside the store")
        return

    groups = (
        ("CRITICAL (real credential material)", result.critical),
        ("HIGH (opaque, review)", result.high),
        ("INFO (config duplication, not a leak)", result.info),
    )
    for title, items in groups:
        if not items:
            continue
        print(f"{title}: {len(items)}")
        current = None
        for finding in items:
            if finding.variable != current:
                current = finding.variable
                print(f"  {current}  [{finding.kind}]")
            flags = []
            if finding.would_commit:
                flags.append("WOULD-COMMIT")
            if finding.ignored:
                flags.append("gitignored")
            elif finding.tracked:
                flags.append("tracked")
            if finding.staged:
                flags.append("staged")
            suffix = f"  ({', '.join(flags)})" if flags else ""
            print(f"      {finding.path}:{finding.line}{suffix}")
        print()

    exposed = result.exposed
    if exposed:
        print(f"RISK: {len(exposed)} finding(s) would be committed to git")
    else:
        print("RISK: nothing found is in a git-tracked path")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mem20secretz",
        description=(
            "Detect credentials that escaped the central mem20 secrets store. "
            "Read-only: never mutates stored data."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("sweep", help="scan the tree for floating store values")
    scan.add_argument("--root", default=DEFAULT_ROOT, help="tree to scan")
    scan.add_argument("--store", default=DEFAULT_STORE, help="central store directory")
    scan.add_argument("--json", action="store_true", help="machine-readable output")
    scan.add_argument("--critical-only", action="store_true",
                      help="hide config/info hits")
    scan.add_argument("--no-git", action="store_true",
                      help="skip git tracked/staged/ignored checks")

    show = sub.add_parser("show", help="describe a variable's classification")
    show.add_argument("variable")
    show.add_argument("--store", default=DEFAULT_STORE)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "show":
        from .sweep import classify, load_store
        values = load_store(args.store)
        value = values.get(args.variable)
        if value is None:
            print(f"{args.variable}: not present in store "
                  f"({len(values)} entries loaded)")
            return EXIT_ERROR
        severity, kind = classify(args.variable, value)
        print(f"variable : {args.variable}")
        print(f"severity : {severity}")
        print(f"kind     : {kind}")
        print(f"length   : {len(value)}")
        return EXIT_CLEAN

    if args.command == "sweep":
        try:
            result = sweep(
                root=args.root,
                store_dir=args.store,
                include_info=not args.critical_only,
                git_aware=not args.no_git,
            )
        except OSError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_ERROR

        if args.json:
            print(json.dumps(result.as_dict(), indent=2))
        else:
            _print_human(result)

        if result.critical or result.exposed:
            return EXIT_FINDINGS
        return EXIT_CLEAN

    return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
