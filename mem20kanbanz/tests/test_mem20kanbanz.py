"""Tests for mem20kanbanz.

Everything here is hermetic. The door is exercised against a real HTTP server
bound to an ephemeral loopback port with a temporary SQLite file, because the
whole point of this package is the wire contract with mem20-kanban, and a
mocked door would only prove the mock agrees with itself.

No test in this suite can touch the live door at :8221 or the production
database at /opt/mem20/kanban.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mem20kanbanz import Door, DoorError, NotFound, __version__  # noqa: E402
from mem20kanbanz.door import DEFAULT_DOOR  # noqa: E402
from mem20kanbanz.migrate import inspect, migrate_file, read_foreign_boards, sha256  # noqa: E402


# --------------------------------------------------------------------------
# a faithful in-process stand-in for the mem20-kanban door
# --------------------------------------------------------------------------
class FakeDoorState:
    def __init__(self) -> None:
        self.boards: dict[str, dict] = {}
        self.tasks: dict[str, dict] = {}
        self.columns: dict[str, dict] = {}
        self._n = 0
        self.fail_next: str | None = None

    def nid(self, prefix: str) -> str:
        self._n += 1
        return f"{prefix}-{self._n}"


class FakeDoorHandler(BaseHTTPRequestHandler):
    state: FakeDoorState = FakeDoorState()

    def log_message(self, format, *args):  # silence the default stderr spam
        pass

    def _reject_empty_json_body(self):
        """Mirror Fastify: a JSON content-type with no body is a 400.

        The real door refuses DELETE that way, and this fake used to accept it,
        so the client shipped a delete that worked in tests and failed in
        production. Anything stricter than production here is a test that lies.
        """
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip()
        length = int(self.headers.get("Content-Length") or 0)
        if ctype == "application/json" and length == 0:
            self._send(400, {"message": "Body cannot be empty when "
                                        "content-type is set to "
                                        "'application/json'"})
            return True
        # And the follow-on failure: urllib labels an empty body as form data,
        # which the real door rejects as an unsupported media type.
        if ctype == "application/x-www-form-urlencoded":
            self._send(415, {"message": "Unsupported Media Type: "
                                        "application/x-www-form-urlencoded"})
            return True
        return False

    # -- helpers ---------------------------------------------------------
    def _send(self, code: int, payload=None):
        body = json.dumps(payload).encode() if payload is not None else b""
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n)) if n else {}

    def _path(self):
        return urlparse(self.path).path

    # -- routes ----------------------------------------------------------
    def do_GET(self):
        s = self.state
        if self._reject_empty_json_body():
            return
        p = self._path()
        if p == "/api/boards":
            return self._send(200, [
                {"id": b["id"], "name": b["name"], "goal": b["goal"],
                 "landing_column_id": b["landing_column_id"]}
                for b in s.boards.values()])
        if p.startswith("/api/boards/"):
            bid = p.rsplit("/", 1)[1]
            b = s.boards.get(bid)
            if not b:
                return self._send(404, {"error": "Board not found"})
            cols = []
            for c in sorted(
                (c for c in s.columns.values() if c["board_id"] == bid),
                key=lambda c: c["position"]):
                tasks = [t for t in s.tasks.values() if t["column_id"] == c["id"]]
                cols.append({**c, "tasks": tasks})
            return self._send(200, {"board": b, "columns": cols})
        if p.startswith("/api/tasks/"):
            tid = p.rsplit("/", 1)[1]
            t = s.tasks.get(tid)
            if not t:
                return self._send(404, {"error": "Task not found"})
            return self._send(200, t)
        return self._send(404, {"error": "nope"})

    def do_POST(self):
        s = self.state
        if self._reject_empty_json_body():
            return
        p = self._path()
        body = self._body()
        if s.fail_next == p:
            s.fail_next = None
            return self._send(500, {"error": "injected failure"})
        if p == "/api/boards":
            name = body["name"]
            for b in s.boards.values():
                if b["name"] == name:
                    return self._send(201, {"boardId": b["id"],
                                            "landingColumnId": b["landing_column_id"]})
            bid = s.nid("b")
            cols = body.get("columns") or [
                {"name": "todo", "wipLimit": 0},
                {"name": "done", "wipLimit": 0, "isDoneColumn": True}]
            landing = body.get("landingColumnPosition", 0)
            made = []
            for i, c in enumerate(cols):
                cid = s.nid("c")
                col = {"id": cid, "board_id": bid, "name": c["name"],
                       "position": i, "wipLimit": c.get("wipLimit", 0),
                       "isDoneColumn": bool(c.get("isDoneColumn")),
                       "isLanding": i == landing, "tasks": []}
                s.columns[cid] = col
                made.append(col)
            s.boards[bid] = {"id": bid, "name": name,
                             "goal": body.get("projectGoal", ""),
                             "landing_column_id": made[landing]["id"]}
            return self._send(201, {"boardId": bid,
                                    "landingColumnId": made[landing]["id"]})
        if p == "/api/tasks":
            bid = body["boardId"]
            b = s.boards.get(bid)
            if not b:
                return self._send(404, {"error": "Board not found"})
            cid = body.get("columnId") or b["landing_column_id"]
            col = s.columns.get(cid)
            if not col:
                return self._send(400, {"error": "Board has no landing column"})
            if col["wipLimit"] > 0:
                n = sum(1 for t in s.tasks.values() if t["column_id"] == cid)
                if n >= col["wipLimit"]:
                    return self._send(422, {"error": "Column capacity full",
                                            "message": f"{col['name']} full"})
            meta = body.get("metadata")
            tid = s.nid("t")
            t = {"id": tid, "column_id": cid, "title": body["title"],
                 "content": body.get("content", ""), "position": 0,
                 "metadata": json.dumps(meta) if isinstance(meta, dict) else meta}
            s.tasks[tid] = t
            return self._send(201, {"success": True, "task": t})
        if p.endswith("/done-column"):
            bid = p.split("/")[3]
            b = s.boards.get(bid)
            if not b:
                return self._send(404, {"error": "Board not found"})
            name = body.get("column") or ""
            cols = [c for c in s.columns.values() if c["board_id"] == bid]
            if not any(c["name"] == name for c in cols):
                return self._send(404, {"error": "Column not found"})
            for c in cols:
                c["isDoneColumn"] = c["name"] == name
            return self._send(200, {"success": True, "column": name})
        if p.endswith("/move"):
            tid = p.split("/")[3]
            t = s.tasks.get(tid)
            if not t:
                return self._send(404, {"error": "Task not found"})
            target_id = body.get("targetColumnId") or ""
            target = s.columns.get(target_id)
            if not target:
                return self._send(404, {"error": "Target column not found"})
            if target["wipLimit"] > 0:
                n = sum(1 for x in s.tasks.values()
                        if x["column_id"] == target["id"] and x["id"] != tid)
                if n >= target["wipLimit"]:
                    return self._send(422, {"error": "Column capacity full",
                                            "message": f"{target['name']} full"})
            t["column_id"] = target["id"]
            if body.get("reason"):
                t["update_reason"] = body["reason"]
            return self._send(200, {"success": True, "taskId": tid})
        return self._send(404, {"error": "nope"})

    def do_PUT(self):
        s = self.state
        p = self._path()
        body = self._body()
        tid = p.rsplit("/", 1)[1]
        t = s.tasks.get(tid)
        if not t:
            return self._send(404, {"error": "Task not found"})
        t["content"] = body.get("content", t["content"])
        return self._send(200, {"success": True, "task": t})

    def do_PATCH(self):
        s = self.state
        p = self._path()
        body = self._body()
        if not p.endswith("/metadata"):
            return self._send(404, {"error": "nope"})
        tid = p.split("/")[3]
        t = s.tasks.get(tid)
        if not t:
            return self._send(404, {"error": "Task not found"})
        patch = body.get("patch")
        if not isinstance(patch, dict):
            return self._send(400, {"error": "patch must be a JSON object"})
        cur = json.loads(t.get("metadata") or "{}")
        for k, v in patch.items():
            if v is None:
                cur.pop(k, None)
            else:
                cur[k] = v
        t["metadata"] = json.dumps(cur)
        return self._send(200, {"success": True, "task": t})

    def do_DELETE(self):
        s = self.state
        p = self._path()
        if p.startswith("/api/boards/"):
            bid = p.rsplit("/", 1)[1]
            if bid not in s.boards:
                return self._send(404, {"error": "Board not found"})
            for c in [c for c in s.columns.values() if c["board_id"] == bid]:
                for t in [t for t in s.tasks.values() if t["column_id"] == c["id"]]:
                    s.tasks.pop(t["id"], None)
                s.columns.pop(c["id"], None)
            s.boards.pop(bid)
            return self._send(200, {"success": True})
        if p.startswith("/api/tasks/"):
            tid = p.rsplit("/", 1)[1]
            if s.tasks.pop(tid, None) is None:
                return self._send(404, {"error": "Task not found"})
            return self._send(200, {"success": True, "taskId": tid})
        return self._send(404, {"error": "nope"})


class DoorServer:
    def __init__(self):
        self.state = FakeDoorState()
        handler = type("H", (FakeDoorHandler,), {"state": self.state})
        self.httpd = HTTPServer(("127.0.0.1", 0), handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_port}"
        self.thread = threading.Thread(target=self.httpd.serve_forever,
                                       daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *a):
        self.httpd.shutdown()
        self.httpd.server_close()


def make_foreign_db(path: Path) -> None:
    """Write a kanban store in the *other* on-box schema (the orphan one)."""
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE boards (id TEXT PRIMARY KEY, name TEXT NOT NULL,
                             goal TEXT, created_at TEXT DEFAULT (datetime('now')));
        CREATE TABLE columns (id TEXT PRIMARY KEY, board_id TEXT NOT NULL,
                              name TEXT NOT NULL, position INTEGER NOT NULL,
                              wip_limit INTEGER DEFAULT 0,
                              FOREIGN KEY (board_id) REFERENCES boards(id));
        CREATE TABLE tasks (id TEXT PRIMARY KEY, board_id TEXT NOT NULL,
                            column_id TEXT NOT NULL, title TEXT NOT NULL,
                            content TEXT DEFAULT '', assignee TEXT DEFAULT '',
                            priority TEXT DEFAULT 'medium',
                            created_at TEXT DEFAULT (datetime('now')),
                            updated_at TEXT DEFAULT (datetime('now')),
                            FOREIGN KEY (column_id) REFERENCES columns(id));
    """)
    conn.execute(
        "INSERT INTO boards (id,name,goal) VALUES ('B1','Fleet HQ','ship it')")
    # Mirrors the real orphan store: four columns, no done flag, WIP 3 on the
    # review column.
    for i, n in enumerate(["Backlog", "In Progress", "Review", "Done"]):
        conn.execute("INSERT INTO columns VALUES (?,?,?,?,?)",
                     (f"C{i}", "B1", n, i, 3 if i == 2 else 0))
    for i in range(5):
        conn.execute(
            "INSERT INTO tasks (id,board_id,column_id,title,content,assignee,priority)"
            " VALUES (?,?,?,?,?,?,?)",
            (f"T{i}", "B1", f"C{i % 3}", f"job {i}", f"do {i}",
             "" if i % 2 else "someone", "high" if i == 0 else "medium"))
    conn.commit()
    conn.close()


# --------------------------------------------------------------------------
class TestPackaging(unittest.TestCase):
    def test_version_is_a_string(self):
        self.assertIsInstance(__version__, str)
        self.assertTrue(__version__)

    def test_exports_importable(self):
        import mem20kanbanz as pkg
        for name in pkg.__all__:
            self.assertTrue(hasattr(pkg, name), name)

    def test_default_door_is_the_door_port(self):
        self.assertIn("8221", DEFAULT_DOOR)


class TestDoorClient(unittest.TestCase):
    def test_health_reports_up(self):
        with DoorServer() as s:
            self.assertTrue(Door(s.url, timeout=5).healthy())

    def test_health_is_false_when_nothing_listens(self):
        # Port 1 on loopback: nothing sane is bound there.
        self.assertFalse(Door("http://127.0.0.1:1", timeout=2).healthy())

    def test_unreachable_door_raises_not_silently_empty(self):
        with self.assertRaises(DoorError):
            Door("http://127.0.0.1:1", timeout=2).board_names()

    def test_create_board_is_idempotent(self):
        """A retry must not create a second board with the same name."""
        with DoorServer() as s:
            d = Door(s.url, timeout=5)
            d.create_board("ops", "goal")
            d.create_board("ops", "goal")
            self.assertEqual(d.board_names(), ("ops",))

    def test_add_card_records_assignee_and_tags(self):
        with DoorServer() as s:
            d = Door(s.url, timeout=5)
            d.create_board("ops")
            c = d.add_card("ops", "t", "body", assignee="crewbot", tags=["a", "b"])
            self.assertEqual(c.assignee, "crewbot")
            self.assertEqual(c.tags, ("a", "b"))

    def test_patch_metadata_preserves_existing_keys(self):
        with DoorServer() as s:
            d = Door(s.url, timeout=5)
            d.create_board("ops")
            c = d.add_card("ops", "t", tags=["keep"])
            d.patch_metadata(c.id, {"assignee": "crewbot"})
            again = d.card(c.id)
            self.assertEqual(again.assignee, "crewbot")
            self.assertEqual(again.tags, ("keep",))

    def test_patch_metadata_null_removes_key(self):
        with DoorServer() as s:
            d = Door(s.url, timeout=5)
            d.create_board("ops")
            c = d.add_card("ops", "t", assignee="crewbot")
            d.patch_metadata(c.id, {"assignee": None})
            self.assertEqual(d.card(c.id).assignee, "")

    def test_patch_metadata_rejects_non_object(self):
        with DoorServer() as s:
            d = Door(s.url, timeout=5)
            d.create_board("ops")
            c = d.add_card("ops", "t")
            with self.assertRaises(DoorError):
                d.patch_metadata(c.id, ["nope"])  # type: ignore[arg-type]

    def test_board_reports_done_columns(self):
        with DoorServer() as s:
            d = Door(s.url, timeout=5)
            d.create_board("ops")
            self.assertIn("done", d.board("ops").done_columns)

    def test_open_work_excludes_done_cards(self):
        with DoorServer() as s:
            d = Door(s.url, timeout=5)
            d.create_board("ops")
            a = d.add_card("ops", "open one")
            b = d.add_card("ops", "finished one")
            d.complete(b.id, board="ops")
            open_titles = {c.title for c in d.open_jobs("ops")}
            self.assertIn("open one", open_titles)
            self.assertNotIn("finished one", open_titles)
            self.assertTrue(a.open_work)

    def test_unclaimed_filters_by_assignee(self):
        with DoorServer() as s:
            d = Door(s.url, timeout=5)
            d.create_board("ops")
            d.add_card("ops", "free")
            d.add_card("ops", "taken", assignee="crewbot")
            self.assertEqual([c.title for c in d.unclaimed("ops")], ["free"])

    def test_claimed_by_matches_case_insensitively(self):
        with DoorServer() as s:
            d = Door(s.url, timeout=5)
            d.create_board("ops")
            d.add_card("ops", "mine", assignee="CrewBot")
            self.assertEqual(len(d.claimed_by("ops", "crewbot")), 1)

    def test_claim_sets_assignee_and_moves(self):
        with DoorServer() as s:
            d = Door(s.url, timeout=5)
            d.create_board("ops")
            c = d.add_card("ops", "job")
            got = d.claim(c.id, "crewbot", board="ops")
            self.assertEqual(got.status, "in_progress")
            self.assertEqual(got.assignee, "crewbot")

    def test_claim_refuses_to_steal_without_force(self):
        with DoorServer() as s:
            d = Door(s.url, timeout=5)
            d.create_board("ops")
            c = d.add_card("ops", "job")
            d.claim(c.id, "crewbot", board="ops")
            with self.assertRaises(DoorError) as ctx:
                d.claim(c.id, "agentz", board="ops")
            self.assertIn("already claimed", str(ctx.exception))

    def test_claim_by_same_agent_twice_is_fine(self):
        with DoorServer() as s:
            d = Door(s.url, timeout=5)
            d.create_board("ops")
            c = d.add_card("ops", "job")
            d.claim(c.id, "crewbot", board="ops")
            d.claim(c.id, "crewbot", board="ops")
            self.assertEqual(d.card(c.id).assignee, "crewbot")

    def test_claim_with_force_takes_over(self):
        with DoorServer() as s:
            d = Door(s.url, timeout=5)
            d.create_board("ops")
            c = d.add_card("ops", "job")
            d.claim(c.id, "crewbot", board="ops")
            d.claim(c.id, "agentz", board="ops", force=True)
            self.assertEqual(d.card(c.id).assignee, "agentz")

    def test_release_returns_card_to_queue(self):
        with DoorServer() as s:
            d = Door(s.url, timeout=5)
            d.create_board("ops")
            c = d.add_card("ops", "job")
            d.claim(c.id, "crewbot", board="ops")
            back = d.release(c.id, board="ops")
            self.assertEqual(back.status, "todo")
            self.assertEqual(back.assignee, "")

    def test_complete_uses_the_boards_done_column(self):
        with DoorServer() as s:
            d = Door(s.url, timeout=5)
            d.create_board("ops")
            c = d.add_card("ops", "job")
            self.assertEqual(d.complete(c.id, board="ops").status, "done")

    def test_complete_resolves_a_custom_done_name(self):
        """Boards on this box disagree: done vs Done vs Review."""
        with DoorServer() as s:
            d = Door(s.url, timeout=5)
            d.create_board("ops", columns=[
                {"name": "Backlog", "wipLimit": 0},
                {"name": "In Progress", "wipLimit": 0},
                {"name": "Review", "wipLimit": 0, "isDoneColumn": True}])
            c = d.add_card("ops", "job")
            self.assertEqual(d.complete(c.id, board="ops").status, "Review")

    def test_complete_refuses_when_board_has_no_done_column(self):
        with DoorServer() as s:
            d = Door(s.url, timeout=5)
            d.create_board("ops", columns=[{"name": "only", "wipLimit": 0}])
            c = d.add_card("ops", "job", column="only")
            with self.assertRaises(DoorError) as ctx:
                d.complete(c.id, board="ops")
            self.assertIn("no done column", str(ctx.exception))

    def test_wip_limit_is_enforced_by_the_door(self):
        with DoorServer() as s:
            d = Door(s.url, timeout=5)
            d.create_board("ops", columns=[
                {"name": "todo", "wipLimit": 0},
                {"name": "doing", "wipLimit": 1}])
            d.add_card("ops", "one", column="doing")
            from mem20kanbanz import CapacityFull
            with self.assertRaises(CapacityFull):
                d.add_card("ops", "two", column="doing")

    def test_unknown_board_raises_not_found(self):
        with DoorServer() as s:
            d = Door(s.url, timeout=5)
            with self.assertRaises(NotFound):
                d.board("nope")

    def test_unknown_task_raises_not_found(self):
        with DoorServer() as s:
            d = Door(s.url, timeout=5)
            d.create_board("ops")
            with self.assertRaises(NotFound):
                d.card("nope")

    def test_delete_card_returns_the_confirmed_id(self):
        with DoorServer() as srv:
            d = Door(srv.url, timeout=5)
            d.create_board("B")
            c = d.add_card("B", "temporary")
            self.assertEqual(d.delete_card(c.id), c.id)

    def test_delete_card_raises_when_the_door_refuses(self):
        """Fail loud: a caller that ignored the old False return would have
        believed the card was gone."""
        with DoorServer() as srv:
            d = Door(srv.url, timeout=5)
            with self.assertRaises(DoorError):
                d.delete_card("no-such-task")

    def test_delete_card_is_gone_afterwards(self):
        with DoorServer() as srv:
            d = Door(srv.url, timeout=5)
            d.create_board("B")
            c = d.add_card("B", "temporary")
            d.delete_card(c.id)
            with self.assertRaises(NotFound):
                d.card(c.id)

    def test_delete_card_old_behaviour(self):
        with DoorServer() as s:
            d = Door(s.url, timeout=5)
            d.create_board("ops")
            c = d.add_card("ops", "job")
            self.assertTrue(d.delete_card(c.id))
            with self.assertRaises(NotFound):
                d.card(c.id)

    def test_delete_board(self):
        with DoorServer() as s:
            d = Door(s.url, timeout=5)
            d.create_board("ops")
            d.add_card("ops", "job")
            self.assertTrue(d.delete_board("ops"))
            self.assertEqual(d.board_names(), ())

    def test_set_done_column(self):
        with DoorServer() as s:
            d = Door(s.url, timeout=5)
            d.create_board("ops")
            self.assertTrue(d.set_done_column("ops", "done"))
            self.assertEqual(d.board("ops").done_columns, ("done",))

    def test_set_done_column_rejects_a_wrong_name(self):
        with DoorServer() as s:
            d = Door(s.url, timeout=5)
            d.create_board("ops")
            with self.assertRaises(NotFound):
                d.set_done_column("ops", "typo")


class TestMigration(unittest.TestCase):
    def test_reads_the_foreign_schema(self):
        with TemporaryDirectory() as td:
            src = Path(td) / "foreign.db"
            make_foreign_db(src)
            boards = read_foreign_boards(src)
            self.assertEqual(len(boards), 1)
            self.assertEqual(boards[0]["name"], "Fleet HQ")
            self.assertEqual(len(boards[0]["tasks"]), 5)
            self.assertEqual(len(boards[0]["columns"]), 4)

    def test_rejects_a_non_kanban_sqlite_file(self):
        with TemporaryDirectory() as td:
            p = Path(td) / "other.db"
            conn = sqlite3.connect(p)
            conn.execute("CREATE TABLE unrelated (x INTEGER)")
            conn.commit()
            conn.close()
            with self.assertRaises(DoorError):
                read_foreign_boards(p)

    def test_inspect_does_not_write(self):
        with TemporaryDirectory() as td:
            src = Path(td) / "foreign.db"
            make_foreign_db(src)
            before = sha256(src)
            rep = inspect(src)
            self.assertEqual(sha256(src), before)
            self.assertTrue(rep.source_unchanged)
            self.assertEqual(rep.cards, 5)

    def test_dry_run_writes_nothing(self):
        with DoorServer() as s, TemporaryDirectory() as td:
            src = Path(td) / "foreign.db"
            make_foreign_db(src)
            door = Door(s.url, timeout=5)
            rep = migrate_file(src, door=door, dry_run=True)
            self.assertEqual(rep.cards, 5)
            self.assertEqual(door.board_names(), ())

    def test_migration_lands_every_card(self):
        with DoorServer() as s, TemporaryDirectory() as td:
            src = Path(td) / "foreign.db"
            make_foreign_db(src)
            door = Door(s.url, timeout=5)
            rep = migrate_file(src, door=door)
            self.assertEqual(rep.errors, [])
            self.assertEqual(door.board_names(), ("Fleet HQ",))
            b = door.board("Fleet HQ")
            self.assertEqual(len(b.cards), 5)
            self.assertEqual({c.name for c in b.columns},
                             {"Backlog", "In Progress", "Review", "Done"})

    def test_migration_leaves_the_source_byte_identical(self):
        """The data-integrity rule: migration inspects, it never rewrites."""
        with DoorServer() as s, TemporaryDirectory() as td:
            src = Path(td) / "foreign.db"
            make_foreign_db(src)
            before = hashlib.sha256(src.read_bytes()).hexdigest()
            mtime = src.stat().st_mtime_ns
            migrate_file(src, door=Door(s.url, timeout=5))
            self.assertEqual(hashlib.sha256(src.read_bytes()).hexdigest(), before)
            self.assertEqual(src.stat().st_mtime_ns, mtime)

    def test_migration_preserves_assignee_and_priority(self):
        with DoorServer() as s, TemporaryDirectory() as td:
            src = Path(td) / "foreign.db"
            make_foreign_db(src)
            door = Door(s.url, timeout=5)
            migrate_file(src, door=door)
            b = door.board("Fleet HQ")
            owners = {c.assignee for c in b.cards}
            self.assertIn("someone", owners)
            self.assertIn("high", {t for c in b.cards for t in c.tags})

    def test_migration_records_its_provenance(self):
        with DoorServer() as s, TemporaryDirectory() as td:
            src = Path(td) / "foreign.db"
            make_foreign_db(src)
            door = Door(s.url, timeout=5)
            migrate_file(src, door=door)
            for c in door.board("Fleet HQ").cards:
                self.assertIn("migrated_from", c.metadata)

    def test_migration_can_rename_a_board(self):
        with DoorServer() as s, TemporaryDirectory() as td:
            src = Path(td) / "foreign.db"
            make_foreign_db(src)
            door = Door(s.url, timeout=5)
            migrate_file(src, door=door,
                         board_names={"Fleet HQ": "fleet-hq"})
            self.assertEqual(door.board_names(), ("fleet-hq",))

    def test_migration_is_idempotent_across_runs(self):
        with DoorServer() as s, TemporaryDirectory() as td:
            src = Path(td) / "foreign.db"
            make_foreign_db(src)
            door = Door(s.url, timeout=5)
            migrate_file(src, door=door)
            migrate_file(src, door=door)
            self.assertEqual(door.board_names(), ("Fleet HQ",))
            self.assertEqual(len(door.board("Fleet HQ").cards), 5)

    def test_report_hashes_match_for_a_real_file(self):
        with TemporaryDirectory() as td:
            src = Path(td) / "foreign.db"
            make_foreign_db(src)
            rep = inspect(src)
            self.assertEqual(rep.source_sha_before, sha256(src))
            self.assertEqual(rep.source_sha_after, rep.source_sha_before)


class TestCli(unittest.TestCase):
    def _run(self, argv):
        from mem20kanbanz import cli
        return cli.main(argv)

    def test_version_flag(self):
        self.assertEqual(self._run(["--version"]), 0)

    def test_no_command_prints_help_and_exits_two(self):
        self.assertEqual(self._run([]), 2)

    def test_health_exit_zero_when_up(self):
        with DoorServer() as s:
            self.assertEqual(self._run(["--door", s.url, "health"]), 0)

    def test_health_exit_one_when_down(self):
        self.assertEqual(
            self._run(["--door", "http://127.0.0.1:1", "--timeout", "2",
                       "health"]), 1)

    def test_door_error_exits_one(self):
        self.assertEqual(
            self._run(["--door", "http://127.0.0.1:1", "--timeout", "2",
                       "boards"]), 1)

    def test_boards_and_jobs_and_claim_and_done(self):
        with DoorServer() as s:
            base = ["--door", s.url, "--json"]
            self.assertEqual(self._run(base + ["boards"]), 0)
            # The board must exist before a card can land on it.
            self._run(base + ["show", "ops"])
            from mem20kanbanz.door import Door
            Door(s.url, timeout=5).create_board("ops")
            self.assertEqual(
                self._run(base + ["add", "ops", "job one"]), 0)
            self.assertEqual(
                self._run(base + ["add", "ops", "job two"]), 0)
            self.assertEqual(self._run(base + ["jobs", "ops"]), 0)
            self.assertEqual(self._run(base + ["jobs", "ops", "--unclaimed"]), 0)
            self.assertEqual(
                self._run(base + ["show", "ops"]), 0)
            # A full lifecycle: claim it, then report it done.
            import json as _json
            import io
            import contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self._run(base + ["jobs", "ops"])
            tid = _json.loads(buf.getvalue())[0]["id"]
            self.assertEqual(
                self._run(base + ["claim", "ops", tid, "crewbot"]), 0)
            self.assertEqual(
                self._run(base + ["done", "ops", tid]), 0)

    def test_bad_rename_pair_exits_two(self):
        self.assertEqual(
            self._run(["--door", "http://127.0.0.1:1", "migrate",
                       "/nonexistent.db", "--as", "nope"]), 2)

    def test_inspect_missing_file_exits_one(self):
        self.assertEqual(
            self._run(["inspect", "/nonexistent/foreign.db"]), 1)

    def test_inspect_a_real_foreign_file(self):
        with TemporaryDirectory() as td:
            src = Path(td) / "foreign.db"
            make_foreign_db(src)
            self.assertEqual(self._run(["inspect", str(src)]), 0)

    def test_inspect_rejects_a_non_kanban_file(self):
        with TemporaryDirectory() as td:
            p = Path(td) / "other.db"
            conn = sqlite3.connect(p)
            conn.execute("CREATE TABLE unrelated (x INTEGER)")
            conn.commit()
            conn.close()
            self.assertEqual(self._run(["inspect", str(p)]), 1)

    def test_migrate_dry_run_then_real(self):
        """The CLI migrate path itself, which the unit tests never touched."""
        with DoorServer() as s, TemporaryDirectory() as td:
            src = Path(td) / "foreign.db"
            make_foreign_db(src)
            before = hashlib.sha256(src.read_bytes()).hexdigest()
            base = ["--door", s.url, "migrate", str(src)]
            self.assertEqual(self._run(base + ["--dry-run"]), 0)
            self.assertEqual(
                Door(s.url, timeout=5).board_names(), ())
            self.assertEqual(self._run(base), 0)
            self.assertEqual(Door(s.url, timeout=5).board_names(), ("Fleet HQ",))
            self.assertEqual(hashlib.sha256(src.read_bytes()).hexdigest(),
                             before)

    def test_migrate_honours_rename(self):
        with DoorServer() as s, TemporaryDirectory() as td:
            src = Path(td) / "foreign.db"
            make_foreign_db(src)
            self.assertEqual(
                self._run(["--door", s.url, "migrate", str(src),
                           "--as", "Fleet HQ=fleet-hq"]), 0)
            self.assertEqual(Door(s.url, timeout=5).board_names(),
                             ("fleet-hq",))

    def test_migrate_twice_does_not_duplicate(self):
        with DoorServer() as s, TemporaryDirectory() as td:
            src = Path(td) / "foreign.db"
            make_foreign_db(src)
            base = ["--door", s.url, "migrate", str(src)]
            self.assertEqual(self._run(base), 0)
            self.assertEqual(self._run(base), 0)
            self.assertEqual(len(Door(s.url, timeout=5).board("Fleet HQ").cards),
                             5)

    def test_done_column_override_marks_a_done_column(self):
        """The orphan store has no done flag, so the name supplies it."""
        with DoorServer() as s, TemporaryDirectory() as td:
            src = Path(td) / "foreign.db"
            make_foreign_db(src)
            door = Door(s.url, timeout=5)
            migrate_file(src, door=door, done_column="Done")
            b = door.board("Fleet HQ")
            self.assertEqual(b.done_columns, ("Done",))
            # And a card can therefore actually be completed.
            c = b.cards[0]
            self.assertEqual(door.complete(c.id, board="Fleet HQ").status,
                             "Done")

    def test_without_the_override_a_doubleless_column_is_not_done(self):
        with DoorServer() as s, TemporaryDirectory() as td:
            src = Path(td) / "foreign.db"
            make_foreign_db(src)
            door = Door(s.url, timeout=5)
            migrate_file(src, door=door)
            self.assertEqual(door.board("Fleet HQ").done_columns, ())

    def test_migrate_reports_source_change_as_failure(self):
        """If the source ever moved under us, say so instead of claiming ok."""
        with DoorServer() as s, TemporaryDirectory() as td:
            src = Path(td) / "foreign.db"
            make_foreign_db(src)
            import mem20kanbanz.migrate as M
            real = M.sha256
            calls = {"n": 0}

            def flaky(p):
                calls["n"] += 1
                return "deadbeef" if calls["n"] == 1 else real(p)

            M.sha256 = flaky
            try:
                self.assertEqual(
                    self._run(["--door", s.url, "migrate", str(src)]), 1)
            finally:
                M.sha256 = real


if __name__ == "__main__":
    unittest.main()


class TestCardReturnsFullContent(unittest.TestCase):
    """Regression guard: card() used to discard a card's content.

    It fetched /api/tasks/{id} -- the authoritative record, body included --
    then returned the board listing's stripped copy instead, because
    ``board()`` deliberately omits content to keep listings light. Every caller
    wanting the full card therefore got an empty string. The IRC bot DMing a
    worker its brief is exactly such a caller.
    """

    def setUp(self):
        self._server = DoorServer().__enter__()
        self.door = Door(self._server.url)
        self.door.create_board("B", "goal")

    def tearDown(self):
        self._server.__exit__(None, None, None)

    def test_card_returns_the_body(self):
        made = self.door.add_card("B", "a task", content="the full brief here")
        self.assertEqual(self.door.card(made.id).content, "the full brief here")

    def test_board_listing_still_omits_the_body(self):
        """The listing stays light on purpose; only card() is the full record."""
        self.door.add_card("B", "a task", content="the full brief here")
        self.assertEqual(self.door.board("B").cards[0].content, "")

    def test_card_keeps_board_and_column_context(self):
        made = self.door.add_card("B", "a task", content="brief")
        full = self.door.card(made.id)
        self.assertEqual(full.metadata.get("board"), "B")
        self.assertIn(full.status, {"todo", "done"})
        self.assertIn("is_done_column", full.metadata)
