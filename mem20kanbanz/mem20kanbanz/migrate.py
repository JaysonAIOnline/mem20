"""Migrate a foreign kanban store into the one true mem20 kanban door.

Built during the four-way merge (mem20agentz kanban / kanban-mcp / mem20-kanban
/ kanban-server) when a real board turned up in an orphan SQLite file that no
other tool could see.

Two hard rules, both from the data-integrity standing rule:

* **Read-only on the source.** The source file is opened with SQLite's
  ``mode=ro`` URI. Detection must never rewrite what a human authored, and a
  migration is detection with teeth. The source bytes are untouched; we prove
  it in the test suite by hashing the file before and after.
* **Everything lands through the door REST API.** No INSERT is ever issued
  against the door's database. The door stays the single writer, so its
  invariants (WIP limits, landing column, positions) still hold.

Column names are mapped by position into the destination board rather than
copied, because the two schemas disagree on names but agree on ordering. A
column that is a done column in the source stays a done column in the target.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .door import DEFAULT_DOOR, Card, Door, DoorError


@dataclass
class MigrationReport:
    """What a migration actually did. Evidence, not narration."""

    source: str = ""
    source_sha_before: str = ""
    source_sha_after: str = ""
    boards: list[str] = field(default_factory=list)
    columns: int = 0
    cards: int = 0
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def source_unchanged(self) -> bool:
        return bool(self.source_sha_before) and \
            self.source_sha_before == self.source_sha_after

    def as_dict(self) -> dict:
        return {
            "source": self.source,
            "source_unchanged": self.source_unchanged,
            "boards": list(self.boards),
            "columns": self.columns,
            "cards": self.cards,
            "skipped": list(self.skipped),
            "errors": list(self.errors),
        }


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _open_readonly(path: Path) -> sqlite3.Connection:
    """Open a SQLite file read-only.

    ``file:...?mode=ro`` is refused by SQLite itself if the file is missing or
    unreadable, which is stronger than a permissions check we might forget.
    """
    uri = f"file:{path}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def read_foreign_boards(path: Path) -> list[dict]:
    """Read boards/columns/tasks out of a foreign kanban SQLite file.

    Tolerates the two schemas seen on the box: one carries ``goal``, the other
    ``project_goal``; one has an ``assignee`` column on tasks, the other keeps
    it in a JSON ``metadata`` blob.
    """
    conn = _open_readonly(path)
    try:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"boards", "columns", "tasks"} <= tables:
            raise DoorError(
                f"{path} is not a kanban store (needs boards/columns/tasks, "
                f"has {sorted(tables)})")
        out: list[dict] = []
        board_rows = conn.execute(
            "SELECT * FROM boards").fetchall()
        board_cols = [d[0] for d in conn.execute(
            "SELECT * FROM boards LIMIT 0").description]
        for row in board_rows:
            b = dict(zip(board_cols, row))
            bid = b.get("id")
            name = b.get("name") or f"board-{bid}"
            goal = b.get("goal") or b.get("project_goal") or ""
            cols = []
            col_rows = conn.execute(
                "SELECT * FROM columns WHERE board_id = ? ORDER BY position",
                (bid,)).fetchall()
            col_cols = [d[0] for d in conn.execute(
                "SELECT * FROM columns LIMIT 0").description]
            for crow in col_rows:
                c = dict(zip(col_cols, crow))
                cols.append({
                    "id": c.get("id"),
                    "name": c.get("name") or "col",
                    "position": c.get("position", 0),
                    "wip_limit": c.get("wip_limit", 0) or 0,
                    "is_done": bool(c.get("is_done_column", 0)),
                })
            tasks = []
            task_rows = conn.execute(
                "SELECT * FROM tasks WHERE column_id IN "
                "(SELECT id FROM columns WHERE board_id = ?)",
                (bid,)).fetchall()
            task_cols = [d[0] for d in conn.execute(
                "SELECT * FROM tasks LIMIT 0").description]
            for trow in task_rows:
                t = dict(zip(task_cols, trow))
                tasks.append({
                    "id": t.get("id"),
                    "title": t.get("title") or "",
                    "content": t.get("content") or "",
                    "column_id": t.get("column_id"),
                    "assignee": t.get("assignee") or "",
                    "priority": t.get("priority") or "",
                })
            out.append({"id": bid, "name": name, "goal": goal,
                        "columns": cols, "tasks": tasks})
        return out
    finally:
        conn.close()


def _dest_columns(source_cols: list[dict],
                  done_column: str = "") -> list[dict]:
    """Map source columns onto door column definitions, by position.

    ``done_column`` forces a column to be the done column by name. This exists
    for stores whose schema has no done flag at all: the orphan board on this
    box has a column literally named ``Done`` and no ``is_done_column`` field
    anywhere, so without an override its work could never be marked complete
    and the bots would have no way to report a finished job.
    """
    if not source_cols:
        return []
    out = []
    for c in sorted(source_cols, key=lambda c: c.get("position", 0)):
        is_done = bool(c.get("is_done"))
        if done_column and c.get("name") == done_column:
            is_done = True
        out.append({"name": c["name"],
                    "wipLimit": int(c.get("wip_limit") or 0),
                    "isDoneColumn": is_done})
    return out


def migrate_file(source: Path, door: Optional[Door] = None,
                 board_names: Optional[dict] = None,
                 done_column: str = "",
                 dry_run: bool = False) -> MigrationReport:
    """Import every board in ``source`` into the door.

    :param board_names: optional ``{source_board_name: door_board_name}``
        override, so a migration can land under a different name.
    :param done_column: column name to mark as the done column, for source
        schemas that carry no done flag.
    :param dry_run: read and plan, write nothing. The report still carries the
        real source hashes, so a dry run is itself evidence about the source.
    """
    source = Path(source)
    door = door or Door(DEFAULT_DOOR)
    rep = MigrationReport(source=str(source))
    rep.source_sha_before = sha256(source)

    boards = read_foreign_boards(source)
    rep.source_sha_after = sha256(source)

    for b in boards:
        dest_name = (board_names or {}).get(b["name"], b["name"])
        col_defs = _dest_columns(b["columns"], done_column)
        by_src_id = {c["id"]: c for c in b["columns"]}
        ordered = sorted(b["columns"], key=lambda c: c.get("position", 0))
        landing = 0
        for i, c in enumerate(ordered):
            if not c.get("is_done"):
                landing = i
                break
        if dry_run:
            rep.boards.append(dest_name)
            rep.columns += len(col_defs)
            rep.cards += len(b["tasks"])
            continue
        try:
            made = door.create_board(dest_name, goal=b["goal"],
                                     columns=col_defs or None,
                                     landing_column_position=landing)
            # create_board is idempotent and returns an existing board
            # untouched, so a re-run against a board imported before the
            # done flag existed still needs the flag applied.
            if done_column and done_column not in made.done_columns:
                try:
                    door.set_done_column(made.name, done_column)
                    made = door.board(made.name)
                except DoorError as exc:
                    rep.errors.append(
                        f"{dest_name}: could not set done column "
                        f"{done_column!r}: {exc}")
            rep.boards.append(made.name)
            rep.columns += len(made.columns)
            landed = {c.name: c.name for c in made.columns}
            # An already-imported board can be re-scanned (a retry, or a
            # second source file contributing to the same board). Skip a card
            # whose title already landed in the same column, otherwise a
            # retried migration silently duplicates every task. The source
            # column is used for the comparison because the door renames
            # nothing -- positions carry the meaning.
            existing = {(c.title, c.status) for c in made.cards}
            for t in b["tasks"]:
                src_col = by_src_id.get(t.get("column_id"))
                target = landed.get(src_col["name"] if src_col else "", "")
                if not target:
                    rep.errors.append(
                        f"{b['name']}: card {t['title']!r} has no target column")
                    continue
                if (t["title"], target) in existing:
                    rep.skipped.append(f"{dest_name}/{t['title']}")
                    continue
                tags = [t["priority"]] if t.get("priority") else []
                try:
                    door.add_card(made.name, t["title"], t["content"],
                                  assignee=t.get("assignee", ""), tags=tags,
                                  column=target,
                                  metadata={"migrated_from": str(source)})
                    rep.cards += 1
                except DoorError as exc:
                    rep.errors.append(f"{b['name']}/{t['title']}: {exc}")
        except DoorError as exc:
            rep.errors.append(f"{b['name']}: {exc}")
    return rep


def inspect(source: Path) -> MigrationReport:
    """Read-only inventory of a foreign store. Never writes, anywhere."""
    source = Path(source)
    rep = MigrationReport(source=str(source))
    rep.source_sha_before = sha256(source)
    for b in read_foreign_boards(source):
        rep.boards.append(b["name"])
        rep.columns += len(b["columns"])
        rep.cards += len(b["tasks"])
    rep.source_sha_after = sha256(source)
    return rep
