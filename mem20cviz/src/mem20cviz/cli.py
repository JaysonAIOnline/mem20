"""fs-cv CLI — cv.infer capability commands.

  fs-cv infer --image img.png | --frame-blob b64 [--mode real|sim] [--embed-dim N] [--no-journal]
  fs-cv sim [--payload '{...}'] [--json]
  fs-cv descriptor
  fs-cv serve [--port N]
  fs-cv health
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.request
from typing import Any

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


def _fetch(path: str, body: dict | None = None,
           base: str = "http://127.0.0.1:8783") -> Any:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{base}{path}", data=data,
        headers={"Content-Type": "application/json"},
        method="POST" if body is not None else "GET",
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def _cmd_infer(args: argparse.Namespace) -> int:
    payload: dict[str, Any] = {"mode": args.mode}
    if args.image:
        if not os.path.isfile(args.image):
            print(f"error: image not found: {args.image}", file=sys.stderr)
            return 2
        payload["image_path"] = args.image
    elif args.frame_blob:
        payload["frame_blob_b64"] = args.frame_blob
    else:
        print("error: --image or --frame-blob required", file=sys.stderr)
        return 2
    payload["options"] = {"embed_dim": args.embed_dim}
    from .service import run_inference
    result = run_inference(payload, journal=not args.no_journal)
    print(json.dumps(result, indent=2))
    rj = (result.get("metadata") or {}).get("_braid")
    if rj:
        print(f"\nbraid receipt: {rj.get('cid')} ok={rj.get('ok')}", file=sys.stderr)
    return 0


def _cmd_sim(args: argparse.Namespace) -> int:
    from .simulator import simulate
    payload = json.loads(args.payload) if args.payload else {}
    result = simulate(payload)
    print(json.dumps(result, indent=2))
    return 0


def _cmd_descriptor(args: argparse.Namespace) -> int:
    from .descriptor import descriptor
    print(json.dumps(descriptor(), indent=2))
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    from .api import main as api_main
    return api_main(["--port", str(args.port)] if args.port else [])


def _cmd_health(args: argparse.Namespace) -> int:
    h = _fetch("/health")
    print(json.dumps(h, indent=2))
    return 0 if h.get("ok") else 1


@json_main
def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="fs-cv", description="mem20cviz cv.infer")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("infer", help="run cv.infer (real or sim)")
    pi.add_argument("--image")
    pi.add_argument("--frame-blob")
    pi.add_argument("--mode", choices=["real", "sim"], default="real")
    pi.add_argument("--embed-dim", type=int, default=128)
    pi.add_argument("--no-journal", action="store_true")
    pi.set_defaults(fn=_cmd_infer)

    ps = sub.add_parser("sim", help="contract simulator (simulated:true)")
    ps.add_argument("--payload", default="")
    ps.set_defaults(fn=_cmd_sim)

    pd = sub.add_parser("descriptor", help="print UCG descriptor")
    pd.set_defaults(fn=_cmd_descriptor)

    psrv = sub.add_parser("serve", help="run HTTP server")
    psrv.add_argument("--port", type=int, default=8783)
    psrv.set_defaults(fn=_cmd_serve)

    ph = sub.add_parser("health", help="server health")
    ph.set_defaults(fn=_cmd_health)

    args = p.parse_args(argv)
    return int(args.fn(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
