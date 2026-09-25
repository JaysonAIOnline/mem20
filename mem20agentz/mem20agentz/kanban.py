"""Kanban — unified multi-board task tracking (sub-phase 2.4).

The mem20 agentz kanban is now a thin client of the mem20 kanban door (:8221),
the ONE kanban backend (single SQLite store). There is exactly one source of
truth for boards and cards; no local JSON is written in production.

Backends:
  - _DoorBackend   (default): real HTTP client to the door REST API.
  - _JsonBackend   (test fixture only, when ``root=`` is passed): deterministic
    on-disk JSON so unit tests run offline. Never the production default.

Watching a board fires a hook event (card_moved / card_added) through the
optional hook registry.
"""

from __future__ import annotations

import json
import pathlib
import urllib.error
import urllib.request
from typing import Optional
from uuid import uuid4

from .config import config_dir

KANBAN_DIR = "kanban"
BOARDS_FILE = "boards.json"
DEFAULT_COLUMNS = ["todo", "in_progress", "done"]
DEFAULT_DOOR = "http://localhost:8221"


class KanbanDoorError(RuntimeError):
    """The unified kanban door is unreachable — the single source of truth."""


class Board:
    def __init__(self, name: str, columns: list[str]) -> None:
        self.name = name
        self.columns = list(columns or DEFAULT_COLUMNS)
        self.cards: list[dict] = []

    def to_dict(self) -> dict:
        return {"columns": self.columns, "cards": self.cards}

    @classmethod
    def from_dict(cls, name: str, d: dict) -> "Board":
        b = cls(name, d.get("columns") or DEFAULT_COLUMNS)
        b.cards = [dict(c) for c in d.get("cards", [])]
        return b

    def card(self, card_id: str) -> Optional[dict]:
        for c in self.cards:
            if c["id"] == card_id:
                return c
        return None


# --------------------------------------------------------------------------
# door (unified store) backend
# --------------------------------------------------------------------------
def _door_request(url: str, method: str = "GET", payload: Optional[dict] = None,
                  timeout: float = 10.0):
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
    elif method in ("POST", "PUT", "DELETE"):
        body = b""
    req = urllib.request.Request(
        url, data=body, method=method,
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.URLError as exc:
        raise KanbanDoorError(
            f"kanban door unreachable at {url}: {exc}") from exc
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def _card_from_task(task: dict, col_by_id: Optional[dict] = None,
                    status: str = "") -> dict:
    """Map a door task row onto the stable card shape (status=column name).

    Tasks in a board detail are already nested under their column, so the
    caller passes the column name explicitly; lone task responses carry a
    column_id that is resolved through col_by_id.
    """
    meta = {}
    raw = task.get("metadata")
    if isinstance(raw, str):
        try:
            meta = json.loads(raw) or {}
        except ValueError:
            meta = {}
    elif isinstance(raw, dict):
        meta = raw
    if not status and col_by_id:
        status = col_by_id.get(task.get("column_id", ""), "")
    return {
        "id": task["id"],
        "title": task["title"],
        "status": status,
        "assignee": meta.get("assignee", ""),
        "tags": sorted(set(meta.get("tags") or [])),
        "content": task.get("content", ""),
        "metadata": meta,
    }


class _DoorBackend:
    """HTTP client for the unified kanban door (single source of truth)."""

    def __init__(self, door: str = DEFAULT_DOOR) -> None:
        self.base = door.rstrip("/")

    # -- boards ------------------------------------------------------------
    def board_names(self) -> list[str]:
        boards = _door_request(f"{self.base}/api/boards") or []
        return sorted(b["name"] for b in boards)

    def board(self, name: str) -> Optional[Board]:
        boards = _door_request(f"{self.base}/api/boards") or []
        board = next((b for b in boards if b["name"] == name), None)
        if board is None:
            return None
        detail = _door_request(
            f"{self.base}/api/boards/{board['id']}") or {"columns": []}
        col_by_id = {c["id"]: c["name"] for c in detail["columns"]}
        out = Board(name, [c["name"] for c in detail["columns"]])
        for col in detail.get("columns", []):
            for task in col.get("tasks", []):
                out.cards.append(_card_from_task(task, status=col["name"]))
        return out

    def create_board(self, name: str, columns=None) -> Board:
        existing = self.board(name)
        if existing is not None:
            return existing
        cols = list(columns or DEFAULT_COLUMNS)
        _door_request(f"{self.base}/api/boards", method="POST", payload={
            "name": name,
            "projectGoal": "created via mem20 agentz",
            "columns": [
                {"name": c, "position": i, "wipLimit": 0,
                 "isDoneColumn": c == "done"}
                for i, c in enumerate(cols)
            ],
            "landingColumnPosition": 0,
        })
        return self.board(name) or Board(name, cols)

    def delete_board(self, name: str) -> bool:
        boards = _door_request(f"{self.base}/api/boards") or []
        board = next((b for b in boards if b["name"] == name), None)
        if board is None:
            return False
        result = _door_request(
            f"{self.base}/api/boards/{board['id']}", method="DELETE")
        return bool(result and result.get("success"))

    # -- cards -------------------------------------------------------------
    def _board_id(self, name: str) -> Optional[str]:
        boards = _door_request(f"{self.base}/api/boards") or []
        board = next((b for b in boards if b["name"] == name), None)
        return board["id"] if board else None

    def add_card(self, board: str, title: str, assignee: str = "",
                 tags: tuple = (), column: str = "") -> Optional[dict]:
        board_id = self._board_id(board)
        if board_id is None:
            return None
        detail = _door_request(f"{self.base}/api/boards/{board_id}")
        if detail is None:
            return None
        col_by_name = {c["name"]: c["id"] for c in detail["columns"]}
        if column:
            column_id = col_by_name.get(column)
        else:
            landing = next(
                (c for c in detail["columns"] if c.get("isLanding")), None)
            column_id = landing["id"] if landing else None
        if not column_id:
            return None
        result = _door_request(f"{self.base}/api/tasks", method="POST", payload={
            "boardId": board_id,
            "title": title,
            "content": "",
            "columnId": column_id,
            "metadata": {"assignee": assignee,
                         "tags": sorted(set(str(t) for t in tags))},
        })
        if result is None or not result.get("success"):
            return None
        task = result.get("task") or {}
        col_by_id = {c["id"]: c["name"] for c in detail["columns"]}
        return _card_from_task(task, col_by_id=col_by_id)

    def move_card(self, board: str, card_id: str,
                  column: str) -> Optional[dict]:
        detail = self._detail_by_card(board, card_id)
        if detail is None:
            return None
        col_by_id = {c["id"]: c["name"] for c in detail["columns"]}
        target = next((c for c in detail["columns"] if c["name"] == column), None)
        if target is None:
            return None
        result = _door_request(
            f"{self.base}/api/tasks/{card_id}/move", method="POST",
            payload={"targetColumnId": target["id"]})
        if result is None or not result.get("success"):
            return None
        task = _door_request(f"{self.base}/api/tasks/{card_id}")
        return _card_from_task(task or {}, col_by_id=col_by_id)

    def list_cards(self, board: str, status: str = "") -> list[dict]:
        b = self.board(board)
        if b is None:
            return []
        cards = b.cards
        if status:
            cards = [c for c in cards if c["status"] == status]
        return cards

    def _detail_by_card(self, board: str, card_id: str):
        board_id = self._board_id(board)
        if board_id is None:
            return None
        detail = _door_request(f"{self.base}/api/boards/{board_id}")
        found = any(
            c["id"] == card_id
            for col in (detail or {}).get("columns", [])
            for c in col.get("tasks", []))
        return detail if found else None


# --------------------------------------------------------------------------
# hermetic (test fixture / legacy) backend — offline, deterministic
# --------------------------------------------------------------------------
class _JsonBackend:
    """On-disk JSON board store. Test fixture only — never the default."""

    def __init__(self, root: pathlib.Path) -> None:
        self.root = root
        self.path = root / BOARDS_FILE

    def _load(self) -> dict:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, data: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def board_names(self) -> list[str]:
        return sorted(self._load().keys())

    def board(self, name: str) -> Optional[Board]:
        raw = self._load().get(name)
        return Board.from_dict(name, raw) if raw else None

    def create_board(self, name: str, columns=None) -> Board:
        data = self._load()
        if name in data:
            return Board.from_dict(name, data[name])
        board = Board(name, columns)
        data[name] = board.to_dict()
        self._save(data)
        return board

    def delete_board(self, name: str) -> bool:
        data = self._load()
        removed = data.pop(name, None) is not None
        if removed:
            self._save(data)
        return removed

    def add_card(self, board: str, title: str, assignee: str = "",
                 tags: tuple = (), column: str = "") -> Optional[dict]:
        b = self.board(board)
        if b is None:
            return None
        col = column or self._first_column(b)
        card = {"id": str(uuid4().hex[:12]), "title": title,
                "status": col, "assignee": assignee,
                "tags": sorted(set(str(t) for t in tags))}
        b.cards.append(card)
        self._put(b)
        return card

    def move_card(self, board: str, card_id: str,
                  column: str) -> Optional[dict]:
        b = self.board(board)
        if b is None or column not in b.columns:
            return None
        card = b.card(card_id)
        if card is None:
            return None
        card["status"] = column
        self._put(b)
        return card

    def list_cards(self, board: str, status: str = "") -> list[dict]:
        b = self.board(board)
        if b is None:
            return []
        cards = b.cards
        if status:
            cards = [c for c in cards if c["status"] == status]
        return cards

    def _first_column(self, b: Board) -> str:
        for col in DEFAULT_COLUMNS:
            if col in b.columns:
                return col
        return b.columns[0]

    def _put(self, board: Board) -> None:
        data = self._load()
        data[board.name] = board.to_dict()
        self._save(data)


# --------------------------------------------------------------------------
# unified facade
# --------------------------------------------------------------------------
class Kanban:
    """Kanban over one backend. Default: the unified mem20 kanban door.

    Passing ``root=`` selects the hermetic on-disk backend (tests only).
    ``door=`` overrides the door base URL.
    """

    def __init__(self, root: Optional[pathlib.Path] = None,
                 hook_registry=None, door: Optional[str] = None) -> None:
        if root is not None:
            self.backend = _JsonBackend(root)
        else:
            self.backend = _DoorBackend(door or DEFAULT_DOOR)
        self.hook_registry = hook_registry

    # ------------------------------------------------------------ boards
    def board_names(self) -> list[str]:
        return self.backend.board_names()

    def board(self, name: str) -> Optional[Board]:
        return self.backend.board(name)

    def create_board(self, name: str, columns=None) -> Board:
        return self.backend.create_board(name, columns)

    def delete_board(self, name: str) -> bool:
        return self.backend.delete_board(name)

    # ------------------------------------------------------------ cards
    def add_card(self, board: str, title: str, assignee: str = "",
                 tags: tuple = (), column: str = "") -> Optional[dict]:
        card = self.backend.add_card(board, title, assignee, tags, column)
        if card:
            self._fire("card_added", {"board": board, "card": card})
        return card

    def move_card(self, board: str, card_id: str,
                  column: str) -> Optional[dict]:
        card = self.backend.move_card(board, card_id, column)
        if card:
            self._fire("card_moved", {"board": board, "card": card})
        return card

    def list_cards(self, board: str, status: str = "") -> list[dict]:
        return self.backend.list_cards(board, status)

    # ----------------------------------------------------------- helpers
    def _fire(self, event: str, payload: dict) -> None:
        if self.hook_registry is None:
            return
        try:
            self.hook_registry.fire(event, payload)
        except Exception:  # noqa: BLE001
            pass