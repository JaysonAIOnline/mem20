"""``python -m mem20controlz`` — describe or serve the control plane."""

from __future__ import annotations

import argparse
import json
import sys


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        prog="mem20-control", description="mem20 fleet control plane"
    )
    parser.add_argument(
        "serve", nargs="?", help="run the FastAPI app (default when no command given)"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8890)
    parser.add_argument(
        "--describe", action="store_true", help="print the manifest and exit"
    )
    args = parser.parse_args(args)

    if args.describe:
        from . import websites

        print(json.dumps(websites.manifest(), indent=2))
        return 0

    import uvicorn

    uvicorn.run(
        "mem20controlz.app:app", host=args.host, port=args.port, log_level="info"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
