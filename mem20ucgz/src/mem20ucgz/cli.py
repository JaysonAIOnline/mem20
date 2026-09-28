from __future__ import annotations

import argparse
import json
import sys

from .sdk import UCGClient
from .simulator import run_scenarios

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


@json_main
def main() -> None:
    p = argparse.ArgumentParser(prog="mem20ucgz")
    p.add_argument("--url", default="http://127.0.0.1:8781")
    sub = p.add_subparsers(dest="cmd", required=True)
    reg = sub.add_parser("register"); reg.add_argument("file")
    q = sub.add_parser("query"); q.add_argument("--text"); q.add_argument("--provides", action="append", default=[]); q.add_argument("--platform")
    c = sub.add_parser("compose"); c.add_argument("--output", action="append", required=True); c.add_argument("--input", action="append", default=[]); c.add_argument("--platform", default="local")
    sub.add_parser("graph")
    sub.add_parser("simulate")
    args = p.parse_args()
    if args.cmd == "simulate":
        print(json.dumps(run_scenarios(), indent=2, default=str)); return
    client = UCGClient(args.url)
    if args.cmd == "register":
        with open(args.file, "r", encoding="utf-8") as f: out = client.register(json.load(f))
    elif args.cmd == "query":
        out = client.query(text=args.text, provides=args.provides, requires_platform=args.platform)
    elif args.cmd == "compose":
        out = client.compose(required_outputs=args.output, available_inputs=args.input, platform=args.platform)
    elif args.cmd == "graph":
        out = client.graph()
    else:
        p.error("unknown command")
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
