"""Client for the one true kanban door (mem20-kanban, REST on :8221).

Every kanban write in mem20 goes through here. There is exactly one store
(one SQLite file, owned by the mem20-kanban systemd unit); this module is a
thin, typed, fail-loud HTTP client for it.

Design rules that came out of the four-way kanban merge:

* **Fail loud.** A door that is unreachable raises :class:`DoorError`. It never
  returns a fabricated board or a silent empty list, because a caller that
  believes it wrote a task when it did not is exactly the drift this merge
  exists to kill.
* **No local writes.** This module never opens a SQLite file. A second writer
  is a second source of truth.
* **Board addressed by name.** The door is the authority on ids; callers hold
  names, which survive a rebuild. Ids are resolved per call.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field, replace
from typing import Any, Iterable, Optional

DEFAULT_DOOR = "http://localhost:8221"


class DoorError(RuntimeError):
    """The kanban door is unreachable or refused the request."""


class CapacityFull(DoorError):
    """A column has hit its WIP limit. Carries the door's message."""


class NotFound(DoorError):
    """The board, column or task does not exist on the door."""


@dataclass(frozen=True)
class Card:
    """A task as the door reports it, flattened for callers."""

    id: str
    title: str
    content: str = ""
    status: str = ""
    assignee: str = ""
    tags: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def open_work(self) -> bool:
        """True unless this card sits in a done column.

        The door marks a column ``is_done_column``; the door response nests
        that flag on the column, so :meth:`Door.card` propagates it into
        ``metadata['is_done_column']`` and this reads it back.
        """
        return not bool(self.metadata.get("is_done_column"))


@dataclass(frozen=True)
class Column:
    id: str
    name: str
    position: int = 0
    wip_limit: int = 0
    is_done: bool = False
    is_landing: bool = False


@dataclass(frozen=True)
class Board:
    id: str
    name: str
    goal: str = ""
    columns: tuple[Column, ...] = ()
    cards: tuple[Card, ...] = ()

    def column(self, name: str) -> Optional[Column]:
        for col in self.columns:
            if col.name == name:
                return col
        return None

    @property
    def done_columns(self) -> tuple[str, ...]:
        return tuple(c.name for c in self.columns if c.is_done)

    def open_cards(self) -> tuple[Card, ...]:
        """Cards not sitting in a done column, in column order."""
        return tuple(c for c in self.cards if c.open_work)

    def cards_in(self, column: str) -> tuple[Card, ...]:
        return tuple(c for c in self.cards if c.status == column)


def _request(base: str, path: str, method: str = "GET",
             payload: Optional[dict] = None, timeout: float = 10.0) -> Any:
    # No payload means no body and no Content-Type. Sending an empty body with a
    # declared content-type is what made DELETE fail twice over: Fastify answers
    # 400 for an empty JSON body, and urllib fills in
    # application/x-www-form-urlencoded for an empty one, which Fastify answers
    # 415. Every POST and PATCH in this client carries a payload, so a bodyless
    # request is genuinely bodyless.
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if body else {}
    req = urllib.request.Request(f"{base}{path}", data=body, method=method,
                                 headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            if not raw:
                return None
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = json.loads(exc.read()).get("message", "")
        except Exception:  # noqa: BLE001 - body may be empty or non-JSON
            pass
        if exc.code == 404:
            raise NotFound(f"404 {path}" + (f": {detail}" if detail else "")) from exc
        if exc.code == 422:
            raise CapacityFull(f"column at capacity {path}: {detail}") from exc
        raise DoorError(f"HTTP {exc.code} {method} {path}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise DoorError(
            f"kanban door unreachable at {base}: {exc.reason}") from exc


def _card_from(raw: dict, done_cols: Iterable[str] = ()) -> Card:
    done = set(done_cols)
    meta = raw.get("metadata")
    if isinstance(meta, str):
        try:
            meta = json.loads(meta) or {}
        except ValueError:
            meta = {}
    meta = dict(meta or {})
    tags = meta.get("tags") or []
    if isinstance(tags, str):
        tags = [t for t in tags.split(",") if t]
    if raw.get("status") in done:
        meta["is_done_column"] = True
    return Card(
        id=raw.get("id", ""),
        title=raw.get("title", ""),
        content=raw.get("content", "") or "",
        status=raw.get("status", "") or "",
        assignee=str(meta.get("assignee", "") or ""),
        tags=tuple(str(t) for t in tags),
        metadata=meta,
    )


class Door:
    """The unified kanban door.

    :param base: door base URL. Defaults to the systemd unit's port.
    :param timeout: per-request timeout in seconds. Bounded on purpose: an
        agent that blocks forever on a kanban call is worse than one that
        fails fast and can be retried.
    """

    def __init__(self, base: str = DEFAULT_DOOR, timeout: float = 10.0) -> None:
        self.base = base.rstrip("/")
        self.timeout = timeout

    # ------------------------------------------------------------------ raw
    def _get(self, path: str) -> Any:
        return _request(self.base, path, "GET", timeout=self.timeout)

    def _post(self, path: str, payload: dict) -> Any:
        return _request(self.base, path, "POST", payload, self.timeout)

    def _put(self, path: str, payload: dict) -> Any:
        return _request(self.base, path, "PUT", payload, self.timeout)

    def _patch(self, path: str, payload: dict) -> Any:
        return _request(self.base, path, "PATCH", payload, self.timeout)

    def _delete(self, path: str) -> Any:
        return _request(self.base, path, "DELETE", timeout=self.timeout)

    # --------------------------------------------------------------- health
    def healthy(self) -> bool:
        """True when the door answers. Never raises."""
        try:
            return isinstance(self._get("/api/boards"), list)
        except DoorError:
            return False

    # --------------------------------------------------------------- boards
    def board_names(self) -> tuple[str, ...]:
        boards = self._get("/api/boards") or []
        return tuple(sorted(b["name"] for b in boards))

    def board_id(self, name: str) -> str:
        for b in self._get("/api/boards") or []:
            if b["name"] == name:
                return b["id"]
        raise NotFound(f"no board named {name!r} on the door")

    def board(self, name: str) -> Board:
        bid = self.board_id(name)
        detail = self._get(f"/api/boards/{bid}")
        if not detail:
            raise NotFound(f"board {name!r} has no detail")
        done_cols = [c["name"] for c in detail.get("columns", [])
                     if c.get("isDoneColumn")]
        cols: list[Column] = []
        cards: list[Card] = []
        for raw in detail.get("columns", []):
            cols.append(Column(
                id=raw.get("id", ""),
                name=raw.get("name", ""),
                position=raw.get("position", 0),
                wip_limit=raw.get("wipLimit", 0) or 0,
                is_done=bool(raw.get("isDoneColumn")),
                is_landing=bool(raw.get("isLanding")),
            ))
            for t in raw.get("tasks", []):
                cards.append(_card_from(
                    {"id": t.get("id"), "title": t.get("title"),
                     "status": raw.get("name"), "metadata": t.get("metadata")},
                    done_cols))
        return Board(
            id=bid,
            name=detail.get("board", {}).get("name", name),
            goal=detail.get("board", {}).get("goal", ""),
            columns=tuple(sorted(cols, key=lambda c: c.position)),
            cards=tuple(cards),
        )

    def create_board(self, name: str, goal: str = "",
                     columns: Optional[list[dict]] = None,
                     landing_column_position: int = 0) -> Board:
        """Create a board. Idempotent: an existing name is returned as-is.

        Idempotence matters because the bots retry. A retry must not create a
        second board with the same name.
        """
        if name in self.board_names():
            return self.board(name)
        if not columns:
            columns = [{"name": "todo", "wipLimit": 0},
                       {"name": "in_progress", "wipLimit": 0},
                       {"name": "done", "wipLimit": 0, "isDoneColumn": True}]
        self._post("/api/boards", {
            "name": name, "projectGoal": goal or "created via mem20kanbanz",
            "columns": columns, "landingColumnPosition": landing_column_position,
        })
        return self.board(name)

    def delete_board(self, name: str) -> bool:
        result = self._delete(f"/api/boards/{self.board_id(name)}")
        return bool(result and result.get("success"))

    def set_done_column(self, board: str, column: str) -> bool:
        """Declare which column means "finished" on a board.

        Exactly one column carries the flag, so setting one clears the rest.
        A board whose source had no done flag at all would otherwise be
        impossible to complete a job on, which would leave an agent with no
        way to report finished work.

        :raises NotFound: when the board has no column of that name, so a
            typo in a bot's configuration surfaces instead of silently
            leaving the board without a done column.
        """
        result = self._post(f"/api/boards/{self.board_id(board)}/done-column",
                            {"column": column})
        if result is None or not result.get("success"):
            raise NotFound(
                f"board {board!r} has no column {column!r} to mark as done")
        return True

    # ---------------------------------------------------------------- cards
    def add_card(self, board: str, title: str, content: str = "",
                 assignee: str = "", tags: Iterable[str] = (),
                 column: str = "", metadata: Optional[dict] = None) -> Card:
        bid = self.board_id(board)
        meta = {"assignee": assignee,
                "tags": sorted({str(t) for t in tags})}
        if metadata:
            meta.update(metadata)
        payload: dict[str, Any] = {"boardId": bid, "title": title,
                                   "content": content, "metadata": meta}
        if column:
            col = self.board(board).column(column)
            if col is None:
                raise NotFound(f"board {board!r} has no column {column!r}")
            payload["columnId"] = col.id
        result = self._post("/api/tasks", payload)
        if not result or not result.get("success"):
            raise DoorError(f"door refused the card {title!r} on {board!r}")
        return _card_from(result.get("task") or {})

    def card(self, task_id: str) -> Card:
        """Fetch one card in full, including its ``content``.

        ``/api/tasks/{id}`` is the authoritative record and carries the body.
        The board listing deliberately does not — a board with hundreds of cards
        should not ship every body to anyone who asks for the board — so this
        method reads ``raw`` for the card itself and takes only the *context*
        (which board, which column, whether that column is done) from the board
        scan.

        It previously returned the board's stripped copy whenever the card was
        found on a board, which silently discarded ``content`` and made every
        caller that wanted the full card — the IRC bot DMing a worker its brief,
        for one — receive an empty specification.
        """
        raw = self._get(f"/api/tasks/{task_id}")
        if not raw:
            raise NotFound(f"no task {task_id!r}")
        # Context only. Deliberately does not use b.cards for the card body.
        for name in self.board_names():
            b = self.board(name)
            for c in b.cards:
                if c.id != task_id:
                    continue
                full = _card_from(raw, b.done_columns)
                return replace(
                    full,
                    status=c.status,
                    metadata={**full.metadata, "board": b.name,
                              "is_done_column": c.status in b.done_columns},
                )
        return _card_from(raw, ())

    def move_card(self, task_id: str, target_column: str,
                  board: str = "", reason: str = "") -> Card:
        """Move a card by *column name* (not id) so callers stay name-based."""
        board_name = board
        if not board_name:
            for name in self.board_names():
                b = self.board(name)
                if any(c.id == task_id for c in b.cards):
                    board_name = name
                    break
        if not board_name:
            raise NotFound(f"task {task_id!r} is on no board")
        col = self.board(board_name).column(target_column)
        if col is None:
            raise NotFound(
                f"board {board_name!r} has no column {target_column!r}")
        result = self._post(f"/api/tasks/{task_id}/move",
                            {"targetColumnId": col.id, "reason": reason})
        if not result or not result.get("success"):
            raise DoorError(f"door refused the move of {task_id!r}")
        return self.card(task_id)

    def set_content(self, task_id: str, content: str) -> Card:
        result = self._put(f"/api/tasks/{task_id}", {"content": content})
        if not result or not result.get("success"):
            raise DoorError(f"door refused the content update of {task_id!r}")
        return _card_from(result.get("task") or {})

    def patch_metadata(self, task_id: str, patch: dict) -> Card:
        """Merge ``patch`` into a task's metadata on the door.

        Merge, not replace, so recording an assignee never erases tags set at
        creation. A key mapped to ``None`` is removed, which is how a claim is
        released. The door rejects a non-object patch, so metadata stays a dict
        for every reader.
        """
        if not isinstance(patch, dict):
            raise DoorError("metadata patch must be a JSON object")
        result = self._patch(f"/api/tasks/{task_id}/metadata", {"patch": patch})
        if not result or not result.get("success"):
            raise DoorError(f"door refused the metadata patch of {task_id!r}")
        return _card_from(result.get("task") or {})

    # ------------------------------------------------------------- workflow
    def claim(self, task_id: str, agent: str, board: str = "",
              column: str = "in_progress", force: bool = False) -> Card:
        """Take a job: record the assignee, then move it into work.

        The assignee is written *before* the move so a card is never sitting
        in the working column owned by nobody. A claim on a card that already
        has a different assignee is refused unless ``force`` is set, because
        silently stealing work is how two agents end up duplicating a task.
        """
        board_name = board or self._board_of(task_id)
        current = self._current(task_id, board_name)
        owner = current.get("assignee") or ""
        if owner and owner.lower() != agent.lower() and not force:
            raise DoorError(
                f"task {task_id!r} is already claimed by {owner!r}; "
                f"pass force to take it over")
        self.patch_metadata(task_id, {"assignee": agent})
        if column:
            return self.move_card(task_id, column, board=board_name,
                                  reason=f"claimed by {agent}")
        return self.card(task_id)

    def release(self, task_id: str, board: str = "",
                column: str = "todo") -> Card:
        """Give a job back: drop the assignee and return it to the queue."""
        self.patch_metadata(task_id, {"assignee": None})
        if column:
            return self.move_card(task_id, column, board=board,
                                  reason="released back to the queue")
        return self.card(task_id)

    def complete(self, task_id: str, board: str = "", reason: str = "",
                 column: str = "") -> Card:
        """Report a job done: move it into the board's done column.

        The done column is resolved from the board's own ``isDoneColumn`` flag
        rather than a hardcoded name, because the boards on this box disagree
        on column naming (``done`` vs ``Done`` vs ``Review``).
        """
        board_name = board or self._board_of(task_id)
        target = column
        if not target:
            b = self.board(board_name)
            done = b.done_columns
            if not done:
                raise DoorError(
                    f"board {board_name!r} has no done column, so a card "
                    f"cannot be marked done without an explicit column")
            target = done[0]
        return self.move_card(task_id, target, board=board_name,
                              reason=reason or "completed")

    def _board_of(self, task_id: str) -> str:
        for name in self.board_names():
            if any(c.id == task_id for c in self.board(name).cards):
                return name
        raise NotFound(f"task {task_id!r} is on no board")

    def _current(self, task_id: str, board: str) -> dict:
        for c in self.board(board).cards:
            if c.id == task_id:
                return dict(c.metadata)
        raise NotFound(f"task {task_id!r} is not on board {board!r}")

    def delete_card(self, task_id: str) -> str:
        """Delete a card outright, returning the id the door confirmed.

        The door has always supported ``DELETE /api/tasks/:id``; this is the
        client-side door to it. It is destructive and not undoable, so two things
        are checked before this reads as success: that the door reported success
        at all, and that the id it confirmed is the id that was asked for. A
        door answering 200 for a *different* card must never read as a delete.

        Raises :class:`DoorError` rather than returning False, because a caller
        that ignores the result would otherwise believe a card was removed.

        Use :meth:`complete` to finish work. Use this only to remove a card that
        should never have existed.
        """
        result = self._delete(f"/api/tasks/{task_id}")
        if not result or not result.get("success"):
            raise DoorError(f"door refused the delete of {task_id!r}")
        confirmed = result.get("taskId")
        if confirmed and confirmed != task_id:
            raise DoorError(
                f"door confirmed deleting {confirmed!r} but {task_id!r} "
                f"was asked for")
        return str(confirmed or task_id)

    # ------------------------------------------------------------ reporting
    def open_jobs(self, board: str) -> tuple[Card, ...]:
        """Every un-done card on a board, oldest column first."""
        b = self.board(board)
        return b.open_cards()

    def unclaimed(self, board: str) -> tuple[Card, ...]:
        """Open cards with no assignee. These are the claimable jobs."""
        return tuple(c for c in self.open_jobs(board) if not c.assignee)

    def claimed_by(self, board: str, agent: str) -> tuple[Card, ...]:
        return tuple(c for c in self.open_jobs(board)
                     if c.assignee.lower() == agent.lower())
