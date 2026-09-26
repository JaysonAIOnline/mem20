"""Query CLI for the mem20 tool inventory.

Commands:

- ``refresh``   regenerate inventory.json from real on-box discovery
- ``list``      list inventory entries (filter by category/kind/subcategory)
- ``search``    search names + descriptions for a term
- ``show``      show one entry in detail (by name or id)
- ``stats``     summary counts
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from toolchest import __version__
from toolchest.catalog import (
    REQUIRED_FIELDS, build_inventory, load_inventory, write_inventory,
)

def _locate_inventory() -> Path:
    """Find the project-root inventory.json without hardcoding a parent depth.

    The package lives at <root>/src/<pkg>/, but walking a fixed number of parents
    breaks the moment the layout changes, so probe the nearby parents in order.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "inventory.json"
        if candidate.is_file():
            return candidate
    return here.parent.parent / "inventory.json"


DEFAULT_INVENTORY = _locate_inventory()


def _entry_matches(e: Dict[str, Any], category: str, kind: str,
                   subcategory: str) -> bool:
    if category:
        target = category.lower()
        if e["category"].lower() != target and e.get("subcategory", "").lower() != target:
            return False
    if kind and e["kind"].lower() != kind.lower():
        return False
    if subcategory and e.get("subcategory", "").lower() != subcategory.lower():
        return False
    return True


def _print_table(entries: List[Dict[str, Any]]) -> None:
    if not entries:
        print("(no matching entries)")
        return
    nlen = max(len(e["name"]) for e in entries)
    for e in entries:
        extra = e.get("subcategory", "")
        print(f"{e['kind']:<10} {e['name']:<{nlen}}  [{e['category']}"
              f"{f'/{extra}' if extra else ''}]  {e['description'][:80]}")


def _sort_key(e: Dict[str, Any]) -> tuple:
    return (e["kind"], e["name"])


def cmd_refresh(args: argparse.Namespace) -> int:
    out = Path(args.output)
    inv = build_inventory(help_sampling=not args.no_help_samples)
    write_inventory(inv, out)
    c = inv["counts"]
    print(f"refreshed {out}")
    print(f"  mcp={c['mcp']} cli={c['cli']} subsystem={c['subsystem']} "
          f"total={c['total']}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    inv = load_inventory(args.inventory)
    entries = sorted(
        (e for e in inv["entries"]
         if _entry_matches(e, args.category, args.kind, args.subcategory)),
        key=_sort_key,
    )
    if args.limit:
        entries = entries[: args.limit]
    if args.json:
        print(json.dumps(entries, indent=2))
    else:
        _print_table(entries)
        if not args.limit or len(entries) < len(
                inv["entries"]):
            print(f"\n{len(entries)} of {inv['counts']['total']} entries")
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    inv = load_inventory(args.inventory)
    term = args.term.lower()
    hits = []
    for e in inv["entries"]:
        if args.kind and e["kind"].lower() != args.kind.lower():
            continue
        hay = " ".join([
            e["name"], e["description"], e["category"],
            e.get("subcategory", ""), json.dumps(e.get("meta", {})),
        ]).lower()
        if term in hay:
            hits.append(e)
    hits = sorted(hits, key=_sort_key)
    if args.limit:
        hits = hits[: args.limit]
    if args.json:
        print(json.dumps(hits, indent=2))
    else:
        _print_table(hits)
        print(f"\n{len(hits)} hits")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    inv = load_inventory(args.inventory)
    target = args.name.lower()
    matches = [e for e in inv["entries"]
               if e["name"].lower() == target or e["id"].lower() == target]
    if not matches:
        print(f"no entry named '{args.name}'", file=sys.stderr)
        return 1
    e = matches[0]
    print(json.dumps(e, indent=2))
    src = e.get("source")
    if src and args.check_path:
        p = Path(src)
        candidates = [p]
        # source may be repo-relative ("opt/mem20/mcp/server.py")
        if not p.is_absolute():
            candidates.append(Path("/opt/mem20") / p)
            rel = str(p)
            if rel.startswith("opt/mem20/"):
                candidates.append(Path("/") / rel)
        resolved = next((c for c in candidates if c.exists()), p)
        print(f"\npath exists on disk: {resolved.exists()} ({resolved})")
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    inv = load_inventory(args.inventory)
    print(f"format      : {inv['format']} v{inv['format_version']}")
    print(f"generated_at: {inv['generated_at']}")
    print(f"host        : {inv['host']}")
    print(f"toolchest   : {inv['toolchest_version']}")
    c = inv["counts"]
    print(f"counts      : mcp={c['mcp']} cli={c['cli']} "
          f"subsystem={c['subsystem']} total={c['total']}")
    for cat, info in inv.get("categories", {}).items():
        subs = ", ".join(info["subcategories"])
        print(f"  - {cat:<14} {info['count']:>4}  ({subs})")
    for note in inv.get("notes", []):
        print(f"note: {note}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="toolchest",
        description="mem20 tool inventory registry — query the real tool registry.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY,
                        help=f"inventory JSON (default: {DEFAULT_INVENTORY})")
    sub = parser.add_subparsers(dest="command", required=True)

    p_refresh = sub.add_parser("refresh", help="regenerate inventory.json")
    p_refresh.add_argument("--output", type=str, default=str(DEFAULT_INVENTORY))
    p_refresh.add_argument("--no-help-samples", action="store_true",
                           help="skip --help sampling for CLI binaries")
    p_refresh.set_defaults(func=cmd_refresh)

    p_list = sub.add_parser("list", help="list inventory entries")
    p_list.add_argument("--category", default="",
                        help="filter by category or subcategory")
    p_list.add_argument("--kind", default="",
                        help="filter by kind (mcp|cli|subsystem)")
    p_list.add_argument("--subcategory", default="")
    p_list.add_argument("--limit", type=int, default=0)
    p_list.add_argument("--json", action="store_true")
    p_list.set_defaults(func=cmd_list)

    p_search = sub.add_parser("search", help="search names + descriptions")
    p_search.add_argument("term")
    p_search.add_argument("--kind", default="")
    p_search.add_argument("--limit", type=int, default=0)
    p_search.add_argument("--json", action="store_true")
    p_search.set_defaults(func=cmd_search)

    p_show = sub.add_parser("show", help="show one entry")
    p_show.add_argument("name")
    p_show.add_argument("--check-path", action="store_true",
                        help="also verify the source path exists on disk")
    p_show.set_defaults(func=cmd_show)

    p_stats = sub.add_parser("stats", help="summary counts")
    p_stats.set_defaults(func=cmd_stats)

    args = parser.parse_args(argv)
    if args.command not in ("refresh",):
        if not Path(args.inventory).exists():
            print(f"inventory not found: {args.inventory} — run "
                  f"'python -m toolchest refresh' first", file=sys.stderr)
            return 2
    return int(args.func(args)) or 0


if __name__ == "__main__":
    sys.exit(main())