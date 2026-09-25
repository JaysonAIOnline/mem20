"""Migrate legacy mem20 agentz JSON kanban boards into the unified door store.

Consumes /root/.mem20agentz/kanban/boards.json (the old per-process JSON
"source of truth") and imports every board + card into the mem20 kanban door
(:8221 unified SQLite store) via its REST API. The JSON file is then backed up
and removed so there is exactly ONE kanban source of truth.

Usage:
    python scripts/migrate_kanban.py [--door http://localhost:8221]

Idempotent: boards already present in the door are skipped.
"""
import argparse
import json
import shutil
import sys
import urllib.request

KANBAN_JSON = "/root/.mem20agentz/kanban/boards.json"
DEFAULT_COLUMNS = ["todo", "in_progress", "done"]


def _req(door: str, method: str, path: str, payload: dict | None = None,
         timeout: int = 15) -> dict:
    body = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(
        door + path, data=body, method=method,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--door", default="http://localhost:8221",
                        help="mem20 kanban door base URL")
    parser.add_argument("--purge-test-boards", action="store_true",
                        help="delete the temporary unified/unified2 e2e boards")
    args = parser.parse_args()
    door = args.door.rstrip("/")

    try:
        existing = {b["name"]: b for b in _req(door, "GET", "/api/boards")}
    except Exception as exc:  # noqa: BLE001 - network/parse failure
        print(f"ERROR: cannot reach kanban door at {door}: {exc}")
        return 1

    if args.purge_test_boards:
        for name in ("unified", "unified2"):
            board = existing.get(name)
            if board:
                _req(door, "DELETE", f"/api/boards/{board['id']}")
                print(f"purged test board: {name}")

    with open(KANBAN_JSON, encoding="utf-8") as fh:
        data = json.load(fh)

    imported = 0
    skipped = 0
    for board_name, board_data in (data or {}).items():
        if board_name in existing:
            print(f"skip (exists): {board_name}")
            skipped += 1
            continue
        fresh = _req(door, "POST", "/api/boards", {
            "name": board_name,
            "projectGoal": "legacy mem20 agentz board (migrated)",
            "columns": [
                {"name": c, "position": i, "wipLimit": 0,
                 "isDoneColumn": c == "done"}
                for i, c in enumerate(board_data.get("columns") or DEFAULT_COLUMNS)
            ],
            "landingColumnPosition": 0,
        })
        board_id = fresh["boardId"]
        detail = _req(door, "GET", f"/api/boards/{board_id}")
        col_id = {c["name"]: c["id"] for c in detail["columns"]}

        for card in board_data.get("cards", []):
            status = card.get("status") or "todo"
            column_id = col_id.get(status, fresh["landingColumnId"])
            meta = {"assignee": card.get("assignee", ""),
                    "tags": card.get("tags", [])}
            _req(door, "POST", "/api/tasks", {
                "boardId": board_id,
                "title": card["title"],
                "content": card.get("content", ""),
                "columnId": column_id,
                "metadata": meta,
            })
            imported += 1
        print(f"imported board: {board_name} ({len(board_data.get('cards', []))} cards)")

    if imported:
        bak = KANBAN_JSON + ".migrated"
        shutil.copy2(KANBAN_JSON, bak)
        with open(KANBAN_JSON, "w", encoding="utf-8") as fh:
            json.dump({}, fh)
        print(f"legacy JSON emptied; backup at {bak}")
    print(f"summary: {imported} cards imported, {skipped} boards skipped")
    return 0


if __name__ == "__main__":
    sys.exit(main())