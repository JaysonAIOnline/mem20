"""Command-line interface for mem20-orchestration."""

from __future__ import annotations

import argparse
import json
import sys

from .catalog import CatalogError, load as load_catalog
from .planner import load_plan, save_plan, validate

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_ERROR = 2


def _out(payload: dict, as_json: bool, human: str) -> None:
    print(json.dumps(payload, indent=2) if as_json else human)


def cmd_ops(args) -> int:
    try:
        cat = load_catalog()
    except CatalogError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    if args.search:
        names = cat.search(args.search, limit=args.limit)
        lines = [f"  {n}" for n in names]
        _out({"query": args.search, "matches": names}, args.json,
             f"{len(names)} match(es) for {args.search!r}\n" + "\n".join(lines))
        return EXIT_OK

    if args.module:
        names = cat.in_module(args.module)
        if not names:
            print(f"error: no such module: {args.module}", file=sys.stderr)
            return EXIT_ERROR
        lines = [f"  {n}" for n in names]
        _out({"module": args.module, "ops": names}, args.json,
             f"{len(names)} op(s) in bpy.ops.{args.module}\n" + "\n".join(lines))
        return EXIT_OK

    if args.show:
        op = cat.get(args.show)
        if op is None:
            print(f"error: unknown op: {args.show}", file=sys.stderr)
            return EXIT_ERROR
        _out(op.as_dict(), args.json,
             f"{op.name}\n  module  : {op.module}\n  function: {op.function}")
        return EXIT_OK

    stats = cat.stats()
    _out(stats, args.json,
         f"Blender {stats['blender_version']}\n"
         f"  operators : {stats['operators']}\n"
         f"  modules    : {stats['modules']}")
    return EXIT_OK


def cmd_modules(args) -> int:
    try:
        cat = load_catalog()
    except CatalogError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    modules = cat.modules
    lines = [f"  {name:<24s} {count:>5d}" for name, count in modules.items()]
    _out({"count": len(modules), "modules": modules}, args.json,
         f"{len(modules)} modules, {sum(modules.values())} ops\n"
         + "\n".join(lines))
    return EXIT_OK


def cmd_validate(args) -> int:
    try:
        steps = load_plan(args.plan)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    try:
        report = validate(steps)
    except CatalogError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    lines = [
        f"plan: {args.plan}",
        f"  steps        : {report.total_steps}",
        f"  valid        : {report.valid_steps}",
        f"  modules used : {len(report.modules_used)}",
        f"  blender      : {report.blender_version}",
    ]
    for finding in report.findings:
        lines.append(f"  {finding.severity.upper():7s} step {finding.index}: "
                     f"{finding.message}")
    verdict = "VALID" if report.ok else "INVALID"
    lines.append(f"  verdict      : {verdict}")

    _out(report.as_dict(), args.json, "\n".join(lines))
    return EXIT_OK if report.ok else EXIT_INVALID


def cmd_newplan(args) -> int:
    try:
        cat = load_catalog()
    except CatalogError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    steps = list(args.op)
    report = validate(steps, catalog=cat)
    save_plan(args.out, steps, cat.blender_version)
    _out({"written": args.out, "steps": len(steps), "valid": report.valid_steps},
         args.json,
         f"wrote {args.out} with {len(steps)} step(s) "
         f"({report.valid_steps} valid against Blender {cat.blender_version})")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mem20-orchestration",
        description=("Blender op orchestration: query the real bpy.ops catalog "
                     "and validate op sequences before they reach Blender."))
    parser.add_argument("--json", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("ops", help="catalog stats, search, module, or show one op")
    p.add_argument("--search")
    p.add_argument("--module")
    p.add_argument("--show")
    p.add_argument("--limit", type=int, default=50)
    p.set_defaults(func=cmd_ops)

    p = sub.add_parser("modules", help="list modules with op counts")
    p.set_defaults(func=cmd_modules)

    p = sub.add_parser("validate", help="validate a plan JSON against the catalog")
    p.add_argument("plan")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("new-plan", help="write a plan JSON from op names")
    p.add_argument("op", nargs="+")
    p.add_argument("--out", default="plan.json")
    p.set_defaults(func=cmd_newplan)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return EXIT_ERROR
    except Exception as exc:  # noqa: BLE001
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
