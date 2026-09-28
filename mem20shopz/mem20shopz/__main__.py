"""``python -m mem20shopz`` — describe or serve the storefront."""

from __future__ import annotations

import argparse
import json
import sys


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        prog="mem20-shop", description="mem20 storefront (Stripe Checkout)"
    )
    parser.add_argument("serve", nargs="?", help="run the FastAPI app")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8891)
    parser.add_argument(
        "--readiness", action="store_true", help="print readiness and exit (exit 1 if not sellable)"
    )
    args = parser.parse_args(args)

    if args.readiness:
        from . import checkout, webhooks
        from .app import store

        report = {**checkout.readiness(), "events": webhooks.status(store())}
        print(json.dumps(report, indent=2))
        return 0 if checkout.readiness()["can_sell"] else 1

    import uvicorn

    uvicorn.run("mem20shopz.app:app", host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
