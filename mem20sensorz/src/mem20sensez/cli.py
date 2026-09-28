"""fs-sense CLI — mem30 Phase 1 sense-organs commands.

  fs-sense gap --goal '...'
  fs-sense replan --goal '...' [--phases a,b,c] [--journal]
  fs-sense twin
  fs-sense exec [--steps 'json'] [--initial 'json'] [--journal]
  fs-sense accelerate --human 'id' --goal '...' [--action declare|attest|admit|growth|progress|summary|revoke|simulate]
  fs-sense enroll --device 'id' [--action declare|attest|enroll|provision|validate|revoke|list|simulate]
  fs-sense descriptors
  fs-sense serve [--port N]
  fs-sense health
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import braid_hook
from .descriptor import all_descriptors
from .service import SenseService

import functools

try:
    from mem20cliz import json_main
except ImportError as _exc:  # never fail silently: a hidden fallback looks like success
    import sys as _sys

    def json_main(func):
        @functools.wraps(func)
        def _warn(*a, **k):
            _sys.stderr.write(
                "warning: mem20cliz unavailable, --json disabled for this CLI (%s)\n" % _exc
            )
            return func(*a, **k)

        return _warn


def _cmd_gap(args: argparse.Namespace) -> int:
    svc = SenseService()
    print(json.dumps(svc.gap(args.goal), indent=2))
    return 0


def _cmd_replan(args: argparse.Namespace) -> int:
    phases = [p for p in (args.phases or "").split(",") if p] if args.phases else None
    svc = SenseService()
    plan = svc.replan(args.goal, phases, journal=args.journal)
    print(json.dumps(plan, indent=2))
    return 0


def _cmd_twin(args: argparse.Namespace) -> int:
    svc = SenseService()
    print(json.dumps(svc.twin(), indent=2))
    return 0


def _cmd_exec(args: argparse.Namespace) -> int:
    steps = json.loads(args.steps) if args.steps else None
    initial = json.loads(args.initial) if args.initial else None
    svc = SenseService()
    plan = svc.exec(steps, initial, journal=args.journal)
    print(json.dumps(plan, indent=2))
    return 0


def _cmd_descriptors(args: argparse.Namespace) -> int:
    print(json.dumps(all_descriptors(), indent=2))
    return 0


def _cmd_accelerate(args: argparse.Namespace) -> int:
    svc = SenseService()
    print(json.dumps(svc.accelerate(
        args.action, args.human, public_key=args.pubkey, goal=args.goal,
        signature=args.signature, metric=args.metric, delta=args.delta,
        max_devices=args.max), indent=2))
    return 0


def _cmd_enroll(args: argparse.Namespace) -> int:
    svc = SenseService()
    print(json.dumps(svc.enroll(
        args.action, args.device, public_key=args.pubkey, signature=args.signature,
        nonce=args.nonce, hostname=args.hostname, platform=args.platform,
        max_devices=args.max), indent=2))
    return 0


def _cmd_health(args: argparse.Namespace) -> int:
    svc = SenseService()
    print(json.dumps(svc.health(), indent=2))
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    from .api import main as api_main
    return api_main(["--port", str(args.port)])


@json_main
def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    p = argparse.ArgumentParser(prog="fs-sense", description="mem30 Phase 1 sense-organs")
    sub = p.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gap"); g.add_argument("--goal", required=True); g.set_defaults(fn=_cmd_gap)
    r = sub.add_parser("replan"); r.add_argument("--goal", required=True)
    r.add_argument("--phases", default=""); r.add_argument("--journal", action="store_true")
    r.set_defaults(fn=_cmd_replan)
    sub.add_parser("twin").set_defaults(fn=_cmd_twin)
    e = sub.add_parser("exec"); e.add_argument("--steps", default=""); e.add_argument("--initial", default="")
    e.add_argument("--journal", action="store_true"); e.set_defaults(fn=_cmd_exec)
    sub.add_parser("descriptors").set_defaults(fn=_cmd_descriptors)
    a = sub.add_parser("accelerate")
    a.add_argument("--action", choices=["declare", "attest", "admit", "growth",
                                        "progress", "summary", "revoke", "simulate"], default="simulate")
    a.add_argument("--human", default="human-1"); a.add_argument("--goal", default="")
    a.add_argument("--pubkey", default=""); a.add_argument("--signature", default="")
    a.add_argument("--metric", default=""); a.add_argument("--delta", type=float, default=0.0)
    a.add_argument("--max", type=int, default=3); a.set_defaults(fn=_cmd_accelerate)
    e = sub.add_parser("enroll")
    e.add_argument("--action", choices=["declare", "attest", "enroll", "provision",
                                        "validate", "revoke", "list", "simulate"], default="simulate")
    e.add_argument("--device", default="device-1"); e.add_argument("--pubkey", default="")
    e.add_argument("--signature", default=""); e.add_argument("--nonce", default="")
    e.add_argument("--hostname", default=""); e.add_argument("--platform", default="")
    e.add_argument("--max", type=int, default=3); e.set_defaults(fn=_cmd_enroll)
    h = sub.add_parser("health"); h.set_defaults(fn=_cmd_health)
    s = sub.add_parser("serve"); s.add_argument("--port", type=int, default=8784); s.set_defaults(fn=_cmd_serve)
    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
