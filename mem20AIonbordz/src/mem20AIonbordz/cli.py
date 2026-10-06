"""Command line interface.

    mem20aionbordz new "Agent Name"     generate a verified onboarding pack
    mem20aionbordz verify <dir>         re-check every claim, report drift
    mem20aionbordz pin <dir>            prepare pinned-memory-block delivery
    mem20aionbordz list                 show generated packs

Exit codes are meaningful: 0 clean, 1 findings (including drift), 2 usage error.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import discover, pack, pin, verify

DEFAULT_ROOT = Path.home() / "mem20-onboarding"


def _cmd_new(args: argparse.Namespace) -> int:
    profile = pack.AgentProfile(
        name=args.name,
        role=args.role,
        mission=args.mission,
        capabilities=list(args.capability or []),
        values=list(args.value or []),
    )
    if args.voice:
        profile.voice = args.voice

    facts, rows, subs = discover.survey()

    out_dir = Path(args.out) if args.out else DEFAULT_ROOT / profile.slug
    result = pack.build_pack(profile, rows, subs, facts, out_dir)

    print(f"Onboarding pack written to {result.directory}")
    print(f"  agent        {profile.name}")
    print(f"  identity     {profile.identity}")
    print(f"  facts        {len(facts)} verified claim(s)")
    print(f"  subsystems   {len(subs)} indexed")
    print(f"  paths found  {sum(1 for r in rows['paths'] if r['exists'])}/{len(rows['paths'])}")
    print(f"  commands     {sum(1 for r in rows['commands'] if r['path'])}/{len(rows['commands'])}")
    print(f"  ports        {len(rows['ports'])} listening, each attributed to a unit")
    print(f"  units        {len(rows['units'])}")
    for f in sorted(result.files()):
        print(f"    {f.name}")
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    pack_dir = Path(args.pack_dir)
    results = verify.verify_pack(pack_dir)
    print(verify.render(results, pack_dir))
    return 1 if any(r.drifted for r in results) else 0


def _cmd_pin(args: argparse.Namespace) -> int:
    pack_dir = Path(args.pack_dir)
    path, requests = pin.apply(pack_dir)
    print(pin.render(pack_dir, path, requests))
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    root = Path(args.root)
    if not root.is_dir():
        print(f"No onboarding packs found under {root}")
        return 0
    packs = sorted(p for p in root.iterdir() if (p / "onboarding.json").exists())
    if not packs:
        print(f"No onboarding packs found under {root}")
        return 0
    print(f"{len(packs)} onboarding pack(s) under {root}\n")
    for d in packs:
        try:
            manifest = pack.load_manifest(d)
        except (OSError, ValueError):
            print(f"  {d.name}  (unreadable manifest)")
            continue
        agent = manifest.get("agent", {})
        counts = manifest.get("counts", {})
        print(f"  {agent.get('name', d.name)}")
        print(f"    role       {agent.get('role', '?')}")
        print(f"    identity   {agent.get('identity', '?')}")
        print(f"    generated  {manifest.get('generated_at', '?')}")
        print(f"    facts      {counts.get('facts', '?')}  ports {counts.get('ports', '?')}")
        print()
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="mem20aionbordz",
        description="Generate verified onboarding packs for newly-hired mem20 agents.",
    )
    sub = ap.add_subparsers(dest="command")

    new = sub.add_parser("new", help="generate an onboarding pack")
    new.add_argument("name", help="agent name, e.g. 'Fledge Alpha'")
    new.add_argument("--role", default="mem20 agent")
    new.add_argument("--mission", default="Work the mem20 fleet with Jayson.")
    new.add_argument("--capability", action="append", help="repeatable")
    new.add_argument("--value", action="append", help="repeatable")
    new.add_argument("--voice", default=None)
    new.add_argument("--out", default=None, help="output directory")
    new.set_defaults(func=_cmd_new)

    ver = sub.add_parser("verify", help="re-check a pack and report drift")
    ver.add_argument("pack_dir")
    ver.set_defaults(func=_cmd_verify)

    pinp = sub.add_parser("pin", help="prepare pinned-block delivery for a pack")
    pinp.add_argument("pack_dir")
    pinp.set_defaults(func=_cmd_pin)

    lst = sub.add_parser("list", help="list generated onboarding packs")
    lst.add_argument("--root", default=str(DEFAULT_ROOT))
    lst.set_defaults(func=_cmd_list)

    return ap


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    if not getattr(args, "func", None):
        ap.print_help()
        return 2
    try:
        return args.func(args)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())