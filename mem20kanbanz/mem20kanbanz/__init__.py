"""mem20kanbanz — the one true kanban door for mem20.

After the four-way merge this package is the only Python entry to kanban in the
estate. It owns three jobs:

* **client** — a typed, fail-loud client for the mem20-kanban REST door
  (:mod:`mem20kanbanz.door`). Never opens the database.
* **migrate** — import a foreign kanban store into the door without touching
  the source (:mod:`mem20kanbanz.migrate`).
* **inspect** — report what a foreign store holds, read-only.

There is exactly one kanban store in mem20, and it belongs to the
``mem20-kanban.service`` unit. Everything here talks to that door.
"""

from __future__ import annotations

__version__ = "0.1.0"

from .door import DEFAULT_DOOR, Board, Card, CapacityFull, Column, Door, DoorError, NotFound
from .migrate import MigrationReport, inspect, migrate_file, read_foreign_boards, sha256

__all__ = [
    "__version__",
    "DEFAULT_DOOR",
    "Board",
    "Card",
    "CapacityFull",
    "Column",
    "Door",
    "DoorError",
    "NotFound",
    "MigrationReport",
    "inspect",
    "migrate_file",
    "read_foreign_boards",
    "sha256",
]
