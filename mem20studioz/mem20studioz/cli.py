"""Crew runtime CLI (skeleton slice)."""

from __future__ import annotations

import argparse
import sys
from typing import Optional, Sequence

from . import MEMBERS, __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mem20studioz",
        description="mem20 studio runtime.",
    )
    parser.add_argument("--version", action="store_true",
                        help="Print the version and exit.")
    parser.add_argument("--members", action="store_true",
                        help="List member systems and exit.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.version:
        print(f"mem20studioz {__version__}")
    if args.members:
        for member in MEMBERS:
            print(member)
    return 0


if __name__ == "__main__":
    sys.exit(main())
