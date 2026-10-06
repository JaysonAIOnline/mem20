"""Greenroom CLI: register, capture, baseline, verify, promote, drop."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional, Sequence

from . import __version__
from .baseline import write_baseline
from .mirror import mirror
from .repo import CloneError, clone_repo
from .store import Registry, RegistryError


def _home() -> Path:
    root = Path(os.environ.get("MEM20GREENZ_HOME",
                               Path.home() / ".mem20greenz"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _registry(home: Optional[Path] = None) -> Registry:
    return Registry((home or _home()) / "registry.sqlite")


def _workspace(home: Path, name: str) -> Path:
    path = home / "workspaces" / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mem20greenz",
        description="mem20 greenroom — stage clones, baseline cleanrooms.",
    )
    parser.add_argument("--version", action="store_true",
                        help="Print the version and exit.")
    sub = parser.add_subparsers(dest="command")

    add = sub.add_parser("add", help="Register a clone target.")
    add.add_argument("name")
    add.add_argument("--kind", required=True, choices=("software", "website"))
    add.add_argument("--source", required=True)

    sub.add_parser("list", help="List registered targets.")

    status = sub.add_parser("status", help="Show one target.")
    status.add_argument("name")

    capture = sub.add_parser(
        "capture", help="Mirror (website) or clone (software) into workspace.")
    capture.add_argument("name")

    baseline = sub.add_parser("baseline", help="Write the concept baseline.")
    baseline.add_argument("name")
    baseline.add_argument("--keeps", required=True)
    baseline.add_argument("--changes", required=True)
    baseline.add_argument("--run-steps", required=True)

    verify = sub.add_parser(
        "verify", help="Check workspace + baseline exist, mark verified.")
    verify.add_argument("name")

    promote = sub.add_parser("promote", help="Promote a verified target.")
    promote.add_argument("name")

    drop = sub.add_parser("drop", help="Drop a target (terminal).")
    drop.add_argument("name")
    return parser


def _cmd_add(reg: Registry, home: Path, args: argparse.Namespace) -> int:
    try:
        record = reg.add(args.name, args.kind, args.source)
    except RegistryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    _workspace(home, args.name)
    print(json.dumps(record, indent=1, default=str))
    return 0


def _cmd_capture(reg: Registry, home: Path, args: argparse.Namespace) -> int:
    record = reg.get(args.name)
    if record is None:
        print(f"error: unknown target {args.name!r}", file=sys.stderr)
        return 2
    if record["status"] != "staged":
        print(f"error: capture needs status staged, is {record['status']!r}",
              file=sys.stderr)
        return 2
    space = _workspace(home, args.name)
    try:
        if record["kind"] == "website":
            manifest = mirror(record["source"], space / "mirror")
            print(f"mirrored {manifest['pages']} pages"
                  f" ({manifest['bytes']} bytes)")
        else:
            report = clone_repo(record["source"], space / "clone")
            print(f"cloned {report['files']} files")
    except (CloneError, OSError) as exc:
        print(f"error: capture failed: {exc}", file=sys.stderr)
        return 1
    reg.advance(args.name, "captured")
    return 0


def _cmd_baseline(reg: Registry, home: Path, args: argparse.Namespace) -> int:
    record = reg.get(args.name)
    if record is None:
        print(f"error: unknown target {args.name!r}", file=sys.stderr)
        return 2
    if record["status"] != "captured":
        print(f"error: baseline needs status captured, is {record['status']!r}",
              file=sys.stderr)
        return 2
    try:
        path = write_baseline(_workspace(home, args.name), name=args.name,
                              source=record["source"], keeps=args.keeps,
                              changes=args.changes, run_steps=args.run_steps)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    reg.advance(args.name, "baselined")
    print(f"wrote {path}")
    return 0


def _cmd_verify(reg: Registry, home: Path, args: argparse.Namespace) -> int:
    record = reg.get(args.name)
    if record is None:
        print(f"error: unknown target {args.name!r}", file=sys.stderr)
        return 2
    if record["status"] != "baselined":
        print(f"error: verify needs status baselined, is {record['status']!r}",
              file=sys.stderr)
        return 2
    space = _workspace(home, args.name)
    if record["kind"] == "website" and not (space / "mirror").is_dir():
        print("error: no mirror workspace to verify", file=sys.stderr)
        return 1
    if record["kind"] == "software" and not (space / "clone").is_dir():
        print("error: no clone workspace to verify", file=sys.stderr)
        return 1
    if not (space / "BASELINE.md").is_file():
        print("error: no BASELINE.md to verify", file=sys.stderr)
        return 1
    reg.advance(args.name, "verified")
    print(f"{args.name} verified")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.version:
        print(f"mem20greenz {__version__}")
        return 0
    if not args.command:
        build_parser().print_help()
        return 0
    home = _home()
    reg = _registry(home)
    try:
        if args.command == "add":
            return _cmd_add(reg, home, args)
        if args.command == "list":
            for record in reg.list():
                print(f'{record["id"]:>3} {record["status"]:<9} '
                      f'{record["kind"]:<8} {record["name"]}  {record["source"]}')
            return 0
        if args.command == "status":
            record = reg.get(args.name)
            if record is None:
                print(f"error: unknown target {args.name!r}", file=sys.stderr)
                return 2
            print(json.dumps(record, indent=1, default=str))
            return 0
        if args.command == "capture":
            return _cmd_capture(reg, home, args)
        if args.command == "baseline":
            return _cmd_baseline(reg, home, args)
        if args.command == "verify":
            return _cmd_verify(reg, home, args)
        if args.command == "promote":
            try:
                reg.advance(args.name, "promoted")
            except RegistryError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
            print(f"{args.name} promoted")
            return 0
        if args.command == "drop":
            try:
                reg.drop(args.name)
            except RegistryError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
            print(f"{args.name} dropped")
            return 0
    except RegistryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
