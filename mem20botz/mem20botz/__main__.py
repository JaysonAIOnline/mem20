"""Run mem20botz as a module: python -m mem20botz [--version]."""

from __future__ import annotations

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
