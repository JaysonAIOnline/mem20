"""CLI for mem20kanbanz.

Commands
--------
health         is the door up
boards         list board names
show           one board: columns, cards, open work
jobs           open (un-done) cards, optionally only unclaimed ones
add            add a card
move           move a card to a column by name
claim          assign a card to an agent and move it into a working column
done           move a card into a done column
inspect        read-only inventory of a foreign kanban SQLite file
migrate        import a foreign kanban SQLite file into the door

Exit codes: 0 success, 1 door/IO error, 2 usage error. Non-zero on findings so
it composes in CI and in the mem20 ops sweep.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

from . import __version__
from .door import DEFAULT_DOOR, Door, DoorError
from .migrate import inspect as inspect_file
from .migrate import migrate_file


def _door(args: argparse.Namespace) -> Door:
    return Door(args.door, timeout=args.timeout)


def _out(obj, as_json: bool) -> None:
    if as_json:
        print(json.dumps(obj, indent=2, default=str))
    else:
        if isinstance(obj, str):
            print(obj)
        else:
            print(json.dumps(obj, indent=2, default=str))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mem20kanbanz",
        description="One true kanban door for mem20 (client + migrator).",
    )
    p.add_argument("--version", action="store_true",
                   help="print version and exit")
    p.add_argument("--door", default=DEFAULT_DOOR,
                   help=f"kanban door base URL (default {DEFAULT_DOOR})")
    p.add_argument("--timeout", type=float, default=10.0,
                   help="per-request timeout in seconds (default 10)")
    p.add_argument("--json", action="store_true", dest="as_json",
                   help="machine-readable output")
    sub = p.add_subparsers(dest="command")

    sub.add_parser("health", help="is the door up")
    sub.add_parser("boards", help="list board names")

    s = sub.add_parser("show", help="one board in full")
    s.add_argument("board")

    s = sub.add_parser("jobs", help="open cards")
    s.add_argument("board")
    s.add_argument("--unclaimed", action="store_true",
                   help="only cards with no assignee")

    s = sub.add_parser("add", help="add a card")
    s.add_argument("board")
    s.add_argument("title")
    s.add_argument("--content", default="")
    s.add_argument("--assignee", default="")
    s.add_argument("--tags", default="", help="comma separated")
    s.add_argument("--column", default="")

    s = sub.add_parser("move", help="move a card to a column by name")
    s.add_argument("task_id")
    s.add_argument("column")
    s.add_argument("--reason", default="")

    s = sub.add_parser("claim", help="assign a card and move it into work")
    s.add_argument("board")
    s.add_argument("task_id")
    s.add_argument("agent")
    s.add_argument("--column", default="in_progress")
    s.add_argument("--force", action="store_true",
                   help="take the card even if another agent holds it")

    s = sub.add_parser("release", help="drop the assignee, return to the queue")
    s.add_argument("board")
    s.add_argument("task_id")
    s.add_argument("--column", default="todo")

    s = sub.add_parser("done", help="move a card into the board's done column")
    s.add_argument("board")
    s.add_argument("task_id")
    s.add_argument("--reason", default="completed")
    s.add_argument("--column", default="",
                   help="override the resolved done column")

    s = sub.add_parser("inspect", help="read-only inventory of a foreign file")
    s.add_argument("path", type=Path)

    s = sub.add_parser("migrate", help="import a foreign file into the door")
    s.add_argument("path", type=Path)
    s.add_argument("--as", dest="board_map", action="append", default=[],
                   metavar="SRC=DOOR",
                   help="rename a board on the way in (repeatable)")
    s.add_argument("--dry-run", action="store_true",
                   help="plan only; write nothing")
    s.add_argument("--done-column", default="",
                   help="force this source column to be the done column "
                        "(for stores with no done flag)")

    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.version:
        print(f"mem20kanbanz {__version__}")
        return 0
    if not args.command:
        build_parser().print_help()
        return 2

    board_map: dict[str, str] = {}
    for pair in getattr(args, "board_map", []) or []:
        if "=" not in pair:
            print(f"error: --as needs SRC=DOOR, got {pair!r}", file=sys.stderr)
            return 2
        src, dest = pair.split("=", 1)
        board_map[src.strip()] = dest.strip()

    try:
        if args.command == "health":
            door = _door(args)
            ok = door.healthy()
            _out({"door": door.base, "healthy": ok}, args.as_json)
            return 0 if ok else 1

        if args.command == "boards":
            _out(list(_door(args).board_names()), args.as_json)
            return 0

        if args.command == "show":
            b = _door(args).board(args.board)
            _out({
                "name": b.name, "goal": b.goal,
                "columns": [{"name": c.name, "wip_limit": c.wip_limit,
                             "is_done": c.is_done,
                             "is_landing": c.is_landing} for c in b.columns],
                "cards": [{"id": c.id, "title": c.title, "status": c.status,
                           "assignee": c.assignee, "tags": list(c.tags),
                           "open": c.open_work} for c in b.cards],
            }, args.as_json)
            return 0

        if args.command == "jobs":
            door = _door(args)
            cards = door.unclaimed(args.board) if args.unclaimed \
                else door.open_jobs(args.board)
            _out([{"id": c.id, "title": c.title, "status": c.status,
                   "assignee": c.assignee} for c in cards], args.as_json)
            return 0

        if args.command == "add":
            tags = tuple(t for t in args.tags.split(",") if t.strip())
            c = _door(args).add_card(args.board, args.title, args.content,
                                     assignee=args.assignee, tags=tags,
                                     column=args.column)
            _out({"id": c.id, "title": c.title, "status": c.status,
                  "assignee": c.assignee}, args.as_json)
            return 0

        if args.command == "move":
            c = _door(args).move_card(args.task_id, args.column,
                                      reason=args.reason)
            _out({"id": c.id, "status": c.status}, args.as_json)
            return 0

        if args.command == "claim":
            # Assign first (so a re-read shows the owner), then move into
            # work. The door records the assignee in task metadata, which is
            # what the bots read back to keep the board accurate.
            c = _door(args).claim(args.task_id, args.agent, board=args.board,
                                  column=args.column, force=args.force)
            _out({"id": c.id, "status": c.status,
                  "assignee": args.agent}, args.as_json)
            return 0

        if args.command == "release":
            c = _door(args).release(args.task_id, board=args.board)
            _out({"id": c.id, "status": c.status}, args.as_json)
            return 0

        if args.command == "done":
            c = _door(args).complete(args.task_id, board=args.board,
                                     reason=args.reason, column=args.column)
            _out({"id": c.id, "status": c.status}, args.as_json)
            return 0

        if args.command == "inspect":
            rep = inspect_file(args.path)
            _out(rep.as_dict(), True)
            return 0 if not rep.errors else 1

        if args.command == "migrate":
            rep = migrate_file(args.path, door=_door(args),
                               board_names=board_map or None,
                               done_column=args.done_column,
                               dry_run=args.dry_run)
            _out(rep.as_dict(), True)
            if rep.errors:
                return 1
            if not rep.source_unchanged:
                print("error: source file changed during migration",
                      file=sys.stderr)
                return 1
            return 0

    except DoorError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    build_parser().print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
