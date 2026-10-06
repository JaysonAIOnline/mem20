"""Hermetic tests for mem20teamz (sqlite tmpdirs, loopback HTTP only)."""

from __future__ import annotations

import json
import tempfile
import unittest
import urllib.request
from pathlib import Path


def _store():
    from mem20teamz.store import Store
    tmp = tempfile.mkdtemp(prefix="teamz-")
    return Store(Path(tmp) / "t.sqlite")


class TestStore(unittest.TestCase):
    def test_rooms_members_messages(self):
        store = _store()
        store.create_room("general", "lobby")
        store.join("general", "jayson", "human")
        store.join("general", "scout", "agent")
        self.assertEqual(len(store.members("general")), 2)
        posted = store.post("general", "jayson", "hello crew")
        self.assertEqual(posted["sender"], "jayson")
        history = store.history("general")
        self.assertEqual([m["text"] for m in history], ["hello crew"])

    def test_guards(self):
        from mem20teamz.store import StoreError
        store = _store()
        with self.assertRaises(StoreError):
            store.post("nope", "x", "hi")
        with self.assertRaises(StoreError):
            store.post("general", "x", "   ")
        store.create_room("general")
        with self.assertRaises(StoreError):
            store.create_room("general")
        with self.assertRaises(StoreError):
            store.join("general", "x", "robot")


class TestRouter(unittest.TestCase):
    def test_mention_wakes_profile(self):
        from mem20teamz.router import route
        store = _store()
        store.create_room("ops")
        store.join("ops", "scout", "agent")
        record = route(store, "ops", "jayson", "hey @scout, look here")
        self.assertEqual(record["kind"], "direct")
        self.assertEqual([w["profile"] for w in record["woken"]], ["scout"])

    def test_unnamed_becomes_plan(self):
        from mem20teamz.router import route
        store = _store()
        store.create_room("ops")
        record = route(store, "ops", "jayson", "please build the summary")
        self.assertEqual(record["kind"], "broadcast")
        self.assertIn("build", record["plan"]["actions"])
        self.assertTrue(record["plan"]["steps"])

    def test_unknown_mention_broadcasts(self):
        from mem20teamz.router import route
        store = _store()
        store.create_room("ops")
        record = route(store, "ops", "jayson", "hey @ghost, hello?")
        self.assertEqual(record["kind"], "broadcast")


class TestMemory(unittest.TestCase):
    def test_mirror_and_hooks(self):
        from mem20teamz.memory import Memory
        seen = []
        mem = Memory(remember=lambda r, s, t: seen.append((r, s, t)))
        mem.remember("ops", "jayson", "hi")
        self.assertEqual(mem.recall("ops")[-1]["text"], "hi")
        self.assertEqual(seen, [("ops", "jayson", "hi")])

    def test_broken_hooks_degrade(self):
        from mem20teamz.memory import Memory
        def boom(*a, **k):
            raise RuntimeError("down")
        mem = Memory(recall=boom, remember=boom)
        mem.remember("ops", "jayson", "hi")
        self.assertEqual(mem.recall("ops")[-1]["text"], "hi")


class TestStudio(unittest.TestCase):
    def test_export_and_empty_refused(self):
        from mem20teamz.studio import export_markdown
        with tempfile.TemporaryDirectory(prefix="teamz-exp-") as out:
            path = export_markdown("ops", "lobby",
                                   [{"sender": "jayson", "text": "go"}],
                                   Path(out) / "ops.md")
            text = Path(path).read_text(encoding="utf-8")
        self.assertIn("**jayson**: go", text)
        with tempfile.TemporaryDirectory(prefix="teamz-exp-") as out:
            with self.assertRaises(ValueError):
                export_markdown("ops", "", [], Path(out) / "ops.md")


class TestCli(unittest.TestCase):
    def test_version(self):
        from mem20teamz import cli
        self.assertEqual(cli.main(["--version"]), 0)

    def test_room_roundtrip(self):
        from mem20teamz import cli
        with tempfile.TemporaryDirectory(prefix="teamz-home-") as home:
            import os
            from unittest import mock
            with mock.patch.dict(os.environ, {"MEM20TEAMZ_HOME": home}):
                self.assertEqual(cli.main(["create", "ops",
                                           "--topic", "t"]), 0)
                self.assertEqual(cli.main(["join", "ops", "scout"]), 0)
                self.assertEqual(cli.main(["post", "ops", "jayson",
                                           "hi @scout"]), 0)
                self.assertEqual(cli.main(["history", "ops"]), 0)
                out = str(Path(home) / "ops.md")
                self.assertEqual(cli.main(["export", "ops", out]), 0)
                self.assertIn("hi @scout",
                              Path(out).read_text(encoding="utf-8"))


class TestServe(unittest.TestCase):
    def test_http_round_trip(self):
        from mem20teamz import cli
        store = _store()
        store.create_room("ops")
        store.join("ops", "scout", "agent")
        base, httpd = cli.serve(store)
        try:
            with urllib.request.urlopen(base + "/rooms",
                                        timeout=10) as resp:
                rooms = json.load(resp)
            self.assertTrue(rooms["ok"])
            data = json.dumps({"room": "ops", "sender": "jayson",
                               "text": "go @scout"}).encode()
            req = urllib.request.Request(
                base + "/post", data=data,
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = json.load(resp)
            self.assertTrue(body["ok"])
            self.assertEqual(body["woken"], ["scout"])
            with urllib.request.urlopen(
                    base + "/history?room=ops", timeout=10) as resp:
                history = json.load(resp)
            self.assertEqual(len(history["messages"]), 1)
        finally:
            httpd.shutdown()
            httpd.server_close()


if __name__ == "__main__":
    unittest.main()
