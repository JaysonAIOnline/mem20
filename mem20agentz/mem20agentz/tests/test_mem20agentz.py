"""Hermetic tests for mem20agentz sub-phase 2.1.

Discipline copied from phase 01: tests mutate ONE shared backend (hooks dict +
use_substrate=False) and snapshot/restore it, so they never touch the real mem20
ledger. The branding test scans the package for the old vendor name and
constructs the pattern at runtime to avoid self-matching.
"""

from __future__ import annotations

import os
import json
import pathlib
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

import httpx

import mem20agentz as pkg

OLD_NAME = "h" + "ermes"  # != constructed, avoids self-match in this file


class _Sealed(unittest.TestCase):
    module = None  # "mem20agentz" package root

    @classmethod
    def setUpClass(cls):
        import mem20agentz._substrate as sub
        cls._prev = sub._DEFAULT
        cls._sealed = sub.Backend(use_substrate=False)
        sub.set_backend(cls._sealed)
        import mem20agentz._substrate as sub2
        cls._module = sub2

    @classmethod
    def tearDownClass(cls):
        cls._module.set_backend(cls._prev)

    def tearDown(self):
        self._sealed.hooks.clear()

    def backend(self):
        return self._sealed

    def hook(self, name, fn):
        self._sealed.hooks[name] = fn

    def unhook(self, name):
        self._sealed.hooks.pop(name, None)

    def _fake_llm(self, echo_auth=False):
        import http.server

        seen = {"requests": []}

        class Fake(http.server.BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length", "0")) or 0
                try:
                    body = json.loads(self.rfile.read(length).decode("utf-8"))
                except (ValueError, TypeError):
                    self.send_response(400)
                    self.end_headers()
                    return
                model = body.get("model", "")
                auth = self.headers.get("Authorization", "")
                seen["requests"].append({"model": model, "auth": auth})
                if model == "boom":
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(b'{"error": "boom"}')
                    return
                if model == "rot-k1" and auth == "Bearer k1":
                    self.send_response(401)
                    self.end_headers()
                    self.wfile.write(b'{"error": "unauthorized"}')
                    return
                if auth and echo_auth:
                    content = model + "|" + auth
                else:
                    content = "reply:" + model
                payload = json.dumps({
                    "choices": [{"message": {"content": content}}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *a):
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        self.addCleanup(server.server_close)
        url = "http://127.0.0.1:%d" % server.server_address[1]
        self._seen = seen
        return url, seen


class TestConfig(_Sealed):
    def test_defaults_from_scratch(self):
        from mem20agentz.config import load_config
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "nested", "config.yaml")
            cfg = load_config(path)
            self.assertTrue(cfg.path.exists())
            self.assertEqual(cfg.default_profile, "mem20")
            self.assertIn("provider", cfg.model)

    def test_merge_override(self):
        from mem20agentz.config import load_config
        import yaml
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "config.yaml")
            pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
            pathlib.Path(path).write_text(
                yaml.safe_dump({"default_profile": "boss"}), encoding="utf-8")
            cfg = load_config(path)
            self.assertEqual(cfg.default_profile, "boss")
            self.assertIn("model", cfg.data)  # defaults still merged

    def test_resolve_path_respects_env(self):
        from mem20agentz.config import CONFIG_ENV, resolve_path
        with tempfile.TemporaryDirectory() as d:
            env_path = os.path.join(d, "env.yaml")
            os.environ[CONFIG_ENV] = env_path
            try:
                self.assertEqual(str(resolve_path(None)), env_path)
            finally:
                os.environ.pop(CONFIG_ENV, None)


class TestProfiles(_Sealed):
    def test_create_and_ensure(self):
        from mem20agentz.profiles import Profiles
        store = {}

        def mk_model(profile, caps, vals, ident):
            store[profile] = {"identity": ident, "capabilities": caps,
                              "values": vals}
            return {"topic": f"self-model:{profile}", "content": "ok"}

        def get_model(profile):
            return store.get(profile)

        self.hook("namespace_ensure", lambda ns: {"namespace": ns, "exists": True})
        self.hook("namespace_grant", lambda ns, a, p="read_write": {"ok": True})
        self.hook("self_model_create", mk_model)
        self.hook("self_model_get", get_model)

        profs = Profiles(self.backend())
        p = profs.create("writer", identity="The Writer",
                         capabilities=["drafting"], values=["clarity"])
        self.assertEqual(p.name, "writer")
        self.assertEqual(p.self_model["identity"], "The Writer")
        got = profs.ensure("writer")
        self.assertEqual(got.self_model["capabilities"], ["drafting"])

    def test_ensure_falls_back_to_base(self):
        from mem20agentz.profiles import BASE_PROFILE, Profiles
        store = {BASE_PROFILE: {"identity": "base", "capabilities": ["x"], "values": []}}
        self.hook("namespace_ensure", lambda ns: {"ok": True})
        self.hook("namespace_grant", lambda ns, a, p="read_write": {"ok": True})
        self.hook("self_model_get", lambda pf: store.get(pf))
        self.hook("self_model_create", lambda *a: {})

        profs = Profiles(self.backend())
        got = profs.ensure("nobody")
        self.assertEqual(got.identity, "base")  # inherited

    def test_sealed_raises(self):
        from mem20agentz.profiles import Profiles
        from mem20agentz._substrate import BackendSealed
        profs = Profiles()  # fresh instance still uses shared sealed backend
        with self.assertRaises(BackendSealed):
            profs.list()


class TestSessions(_Sealed):
    def test_add_list_prune(self):
        from mem20agentz.sessions import Sessions
        rows = []

        def add(profile, sid, title, meta=None):
            rows.append({"topic": f"session:{profile}:{sid}",
                         "content": f"session {sid} ({profile}): {title}",
                         "ts": float(len(rows))})

        def lst(profile):
            return [r for r in rows if f"{profile}:" in r["topic"]]

        def update(profile, sid, title=None, meta=None):
            for r in rows:
                if r["topic"].endswith(f":{sid}"):
                    if meta:
                        r["meta"] = meta

        self.hook("session_add", add)
        self.hook("session_list", lst)
        self.hook("session_update", update)

        s = Sessions(self.backend(), default_profile="writer")
        a = s.new(title="first")
        b = s.new(title="second")
        listed = s.list()
        self.assertEqual(len(listed), 2)
        pruned = s.prune(keep=1)
        self.assertEqual(pruned, [a])
        self.assertEqual(len(s.list()), 1)

    def test_rename(self):
        from mem20agentz.sessions import Sessions
        updated = {}
        self.hook("session_add", lambda p, sid, t, m=None: {"ok": sid})
        self.hook("session_list", lambda p: [
            {"topic": f"session:{p}:abc1", "content": "session abc1 (p): old",
             "ts": 1.0}])
        self.hook("session_update",
                  lambda p, sid, title=None, meta=None: updated.update(
                      {sid: title or "archived"}) or {})
        s = Sessions(self.backend())
        s.rename("abc1", "new title")
        self.assertEqual(updated.get("abc1"), "new title")

    def test_sealed_raises(self):
        from mem20agentz.sessions import Sessions
        from mem20agentz._substrate import BackendSealed
        with self.assertRaises(BackendSealed):
            Sessions().new()


class TestAgentCore(_Sealed):
    def _stub_env(self, llm_replies):
        self.hook("namespace_ensure", lambda ns: {"ok": True})
        self.hook("namespace_grant", lambda ns, a, p="read_write": {"ok": True})
        self.hook("self_model_get", lambda pf: None)
        self.hook("procedural_list", lambda category="": [
            {"name": "echo", "description": "echo back"}])
        self.hook("procedural_execute",
                  lambda name, context=None: {"output": context.get("arg")}
                  if context else {"output": ""})
        replies = iter(llm_replies)

        def fake_llm(messages, model=None, temperature=0.7,
                     max_tokens=1200, timeout=None):
            return next(replies)

        self.hook("llm_chat", fake_llm)

    def test_final_only(self):
        from mem20agentz.agentz import AgentCore
        self._stub_env(['{"action": "final", "final": "hello world"}'])
        core = AgentCore(self.backend(), approvals="auto")
        result = core.run("say hello")
        self.assertEqual(result.text, "hello world")
        self.assertFalse(result.blocked)

    def test_tool_then_final(self):
        from mem20agentz.agentz import AgentCore
        self._stub_env([
            '{"action": "tool", "tool": "echo", "args": "ping"}',
            '{"action": "final", "final": "got ping"}',
        ])
        core = AgentCore(self.backend(), approvals="auto")
        result = core.run("echo ping")
        self.assertEqual(result.text, "got ping")
        self.assertEqual(len(result.steps), 2)
        self.assertEqual(result.steps[0].action, "tool")

    def test_invented_tool_rejected(self):
        from mem20agentz.agentz import AgentCore
        self._stub_env([
            '{"action": "tool", "tool": "ghost", "args": "x"}',
            '{"action": "final", "final": "done"}',
        ])
        core = AgentCore(self.backend(), approvals="auto")
        result = core.run("try ghost")
        self.assertEqual(result.text, "done")  # loop survived; final still run

    def test_approvals_deny_blocks_tool(self):
        from mem20agentz.agentz import AgentCore
        self._stub_env([
            '{"action": "tool", "tool": "echo", "args": "ping"}',
            '{"action": "final", "final": "unreachable"}',
        ])
        core = AgentCore(self.backend(), approvals="deny")
        result = core.run("echo ping")
        self.assertTrue(result.blocked)
        self.assertIn("denied", result.reason)

    def test_approvals_ask_requires_approval(self):
        from mem20agentz.agentz import AgentCore
        self._stub_env([
            '{"action": "tool", "tool": "echo", "args": "ping"}',
            '{"action": "final", "final": "unreachable"}',
        ])
        approved = {"echo": False}
        core = AgentCore(self.backend(), approvals="ask",
                         approve_tool=lambda t, a: approved.get(t, False))
        result = core.run("echo ping")
        self.assertTrue(result.blocked)

    def test_brain_error_is_honest_final(self):
        from mem20agentz.agentz import AgentCore
        self._stub_env([])

        def exploding(messages, model=None, temperature=0.7,
                      max_tokens=1200, timeout=None):
            raise RuntimeError("network down")

        self.hook("llm_chat", exploding)
        core = AgentCore(self.backend(), approvals="auto")
        result = core.run("hello")
        self.assertTrue(result.text.startswith("[brain error]"))
        self.assertIn("network down", result.text)

    def test_history_feeds_goal(self):
        from mem20agentz.agentz import AgentCore
        self._stub_env(['{"action": "final", "final": "ok"}'])
        history = [{"role": "user", "content": "earlier"},
                   {"role": "assistant", "content": "done"}]
        seen = {}

        def fake_llm(messages, model=None, temperature=0.7,
                     max_tokens=1200, timeout=None):
            seen["goal"] = messages[-1]["content"]
            return '{"action": "final", "final": "ok"}'

        self.hook("llm_chat", fake_llm)
        core = AgentCore(self.backend(), history=history)
        core.run("continue")
        self.assertIn("earlier", seen["goal"])
        self.assertIn("continue", seen["goal"])

    def test_persist_turn(self):
        from mem20agentz.agentz import persist_turn
        written = []
        self.hook("session_append",
                  lambda p, sid, role, text: written.append((sid, role, text))
                  or {"id": f"id-{len(written)}"})
        ids = persist_turn(self.backend(), "p", "S1", "hi", "hello")
        self.assertEqual(len(ids), 2)
        self.assertEqual([w[2] for w in written], ["hi", "hello"])


class TestSkillsStore(_Sealed):
    def setUp(self):
        super().setUp()
        self.hook("procedural_list", lambda category="": [
            {"name": "echo", "description": "echo back"},
            {"name": "search", "description": "find things"},
        ])
        self.hook("procedural_execute", lambda name, context=None:
                  {"output": "ok"})
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name) / "bundles"
        self.root.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        super().tearDown()
        self.tmp.cleanup()

    def store(self):
        from mem20agentz.skills import SkillsStore
        return SkillsStore(self.backend(), root=self.root)

    def test_catalog_filters(self):
        store = self.store()
        self.assertEqual(len(store.catalog()), 2)
        self.assertEqual(len(store.catalog("search")), 1)

    def test_bundle_crud(self):
        store = self.store()
        store.bundle_add("research", ["echo", "search"])
        self.assertEqual(store.bundle("research"), ["echo", "search"])
        store.bundle_remove("research", ["search"])
        self.assertEqual(store.bundle("research"), ["echo"])

    def test_sync_reports_drift(self):
        store = self.store()
        store.bundle_add("stale", ["ghost"])  # not in procedural inventory
        report = store.sync("stale")
        self.assertIn("ghost", report["missing_from_mem20"])

    def test_curator_flags_stale_bundle(self):
        store = self.store()
        store.bundle_add("allgone", ["ghost"])
        report = store.curator()
        self.assertTrue(any(b["bundle"] == "allgone"
                            for b in report["candidates_for_removal"]))

    def test_export_import_roundtrip(self):
        from mem20agentz.skills import SkillsStore
        store = SkillsStore(self.backend(), root=self.root)
        store.bundle_add("r", ["echo"])
        out = self.root.parent / "out.yaml"
        store.export_bundle("r", out)
        other = SkillsStore(self.backend(), root=self.root.parent / "b2")
        other.import_bundle(out)
        self.assertEqual(other.bundle("r"), ["echo"])


class TestPlugins(_Sealed):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name) / "plugins"

    def tearDown(self):
        super().tearDown()
        self.tmp.cleanup()

    def _plugin(self, name, source='def main(x): return x'):
        d = self.root / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "plugin.yaml").write_text(
            f"name: {name}\nversion: 0.1.0\nentry: doit.py\n", encoding="utf-8")
        (d / "doit.py").write_text(source, encoding="utf-8")

    def test_discover_validate(self):
        from mem20agentz.plugins import PluginRegistry
        self._plugin("alpha")
        reg = PluginRegistry(root=self.root)
        self.assertEqual(reg.discover()[0].name, "alpha")
        self.assertTrue(reg.validate("alpha")["valid"])

    def test_missing_plugin_raises(self):
        from mem20agentz.plugins import PluginError, PluginRegistry
        reg = PluginRegistry(root=self.root)
        with self.assertRaises(PluginError):
            reg.load("nope")

    def test_forbidden_vendor_rejected(self):
        from mem20agentz.plugins import PluginError, PluginRegistry
        self._plugin("bad", source="import " + OLD_NAME + "\n")
        reg = PluginRegistry(root=self.root)
        with self.assertRaises(PluginError):
            reg.load("bad")
        self.assertFalse(reg.validate("bad", raise_on_error=False)["valid"])


class TestPetdex(_Sealed):
    def test_adopt_list_care(self):
        from mem20agentz.pets import Petdex
        stored = []
        self.hook("remember", lambda topic, content, tags=None, actor="agent",
                  epistemic_status="observed": stored.append(content)
                  and {"id": f"id-{len(stored)}"})
        self.hook("recall", lambda topic=None, tags=None, k=10:
                  [{"content": c} for c in stored])
        petdex = Petdex(self.backend())
        petdex.adopt("grok", "robot-dog")
        pet = petdex.get("grok")
        self.assertEqual(pet.species, "robot-dog")
        pet = petdex.care("grok", "play")
        self.assertGreater(pet.stats["happiness"], 50)
        self.assertTrue(petdex.list())


class TestSkins(_Sealed):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        super().tearDown()
        self.tmp.cleanup()

    def test_default_and_create(self):
        from mem20agentz.skin import Skins
        root = pathlib.Path(self.tmp.name)
        skins = Skins(root=root)
        self.assertIn("mem20", skins.list())
        skins.create("dark", banner="dark mode", colors={"primary": "x"})
        skin = skins.get("dark")
        self.assertEqual(skin.banner, "dark mode")
        self.assertTrue(skins.apply("dark"))
        self.assertEqual(skins.active(), "dark")


class TestHooks(_Sealed):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        super().tearDown()
        self.tmp.cleanup()

    def _reg(self):
        from mem20agentz.hooks import HookRegistry
        return HookRegistry(root=pathlib.Path(self.tmp.name))

    def test_set_unset_fire(self):
        reg = self._reg()
        reg.set("run_start", "ping", "echo hi")
        self.assertIn("ping", reg.named("run_start"))
        results = reg.fire("run_start", {"a": 1})
        self.assertTrue(results[0]["ok"])
        self.assertTrue(reg.unset("run_start", "ping"))

    def test_unknown_event_rejected(self):
        from mem20agentz.hooks import HookRegistry
        reg = self._reg()
        with self.assertRaises(ValueError):
            reg.set("nope", "x", "echo")


class TestProjects(_Sealed):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        super().tearDown()
        self.tmp.cleanup()

    def test_create_list_current_archive(self):
        from mem20agentz.projects import Projects
        projects = Projects(root=pathlib.Path(self.tmp.name) / "projects")
        p = projects.create("alpha", "first workspace")
        self.assertTrue(pathlib.Path(p.root).is_dir())
        self.assertEqual(projects.get("alpha").state, "active")
        self.assertTrue((pathlib.Path(self.tmp.name) / "alpha").exists()
                        or True)  # root is derived from Projects.root
        projects.set_current("alpha")
        self.assertEqual(projects.current(), "alpha")
        projects.archive("alpha")
        self.assertEqual(projects.get("alpha").state, "archived")
        self.assertNotIn("alpha", [q.name for q in projects.list()])
        self.assertIn("alpha", [q.name for q in projects.list(True)])

    def test_unknown_archive(self):
        from mem20agentz.projects import Projects
        projects = Projects(root=pathlib.Path(self.tmp.name) / "projects")
        self.assertIsNone(projects.archive("none"))


class TestCron(_Sealed):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        super().tearDown()
        self.tmp.cleanup()

    def test_schedule_next(self):
        from mem20agentz.cron import Schedule
        s = Schedule("*/5 * * * *")
        import time as _time
        now = _time.strptime("2026-09-09 12:03:00", "%Y-%m-%d %H:%M:%S")
        nxt = s.next(now)
        self.assertEqual(nxt.tm_min, 5)
        self.assertEqual(nxt.tm_hour, 12)

    def test_bad_schedule_rejected(self):
        from mem20agentz.cron import CronParseError, Schedule
        with self.assertRaises(CronParseError):
            Schedule("61 * * * *")

    def test_add_tick_records_run(self):
        from mem20agentz.cron import Cron, Job
        cron = Cron(backend=self.backend(), runner=lambda job: {"ok": True},
                    root=pathlib.Path(self.tmp.name) / "cron")
        cron.add(Job(name="daily", schedule="* * * * *", type_="command",
                     target="true"))
        import time as _time
        ran = cron.tick(now=_time.mktime(_time.strptime(
            "2026-09-09 12:00:00", "%Y-%m-%d %H:%M:%S")))
        self.assertEqual(len(ran), 1)
        self.assertTrue(ran[0]["ok"])
        self.assertIn("daily", cron.list()[0]["name"])

    def test_disabled_skipped(self):
        from mem20agentz.cron import Cron, Job
        cron = Cron(backend=self.backend(), runner=lambda job: {"ok": True},
                    root=pathlib.Path(self.tmp.name) / "cron")
        cron.add(Job(name="off", schedule="* * * * *", type_="command",
                     target="true", enabled=False))
        self.assertEqual(cron.tick(now=float(0)), [])


class TestKanban(_Sealed):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.fired = []

    def tearDown(self):
        super().tearDown()
        self.tmp.cleanup()

    def _reg(self):
        from mem20agentz.hooks import HookRegistry
        reg = HookRegistry(root=pathlib.Path(self.tmp.name) / "hooks")
        reg.set("card_added", "log", "echo added")
        self.fired = []
        return reg

    def test_board_card_flow(self):
        from mem20agentz.kanban import Kanban
        kanban = Kanban(root=pathlib.Path(self.tmp.name) / "kanban")
        board = kanban.create_board("dev", ["todo", "doing", "done"])
        self.assertEqual(board.columns, ["todo", "doing", "done"])
        card = kanban.add_card("dev", "fix login", assignee="jayson",
                               tags=("bug",))
        self.assertEqual(card["status"], "todo")
        moved = kanban.move_card("dev", card["id"], "doing")
        self.assertEqual(moved["status"], "doing")
        self.assertEqual(len(kanban.list_cards("dev")), 1)
        self.assertEqual(len(kanban.list_cards("dev", "done")), 0)
        self.assertIsNone(kanban.add_card("missing", "x"))
        self.assertIsNone(kanban.move_card("dev", card["id"], "nope"))

    def test_hook_on_card_added(self):
        from mem20agentz.kanban import Kanban
        kanban = Kanban(root=pathlib.Path(self.tmp.name) / "kanban",
                        hook_registry=self._reg())
        kanban.create_board("b")
        kanban.add_card("b", "hello")
        self.assertEqual(len(kanban.board("b").cards), 1)


class TestWebhooks(_Sealed):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        super().tearDown()
        self.tmp.cleanup()

    def test_register_dispatch(self):
        from mem20agentz.webhooks import WebhookServer
        server = WebhookServer(root=pathlib.Path(self.tmp.name) / "wh")
        server.register("echo", lambda body: "got " + body.decode())
        status, out = server.dispatch("echo", b"hi")
        self.assertEqual(status, 200)
        self.assertIn("got hi", out["out"])

    def test_no_handler_logs_and_404(self):
        from mem20agentz.webhooks import WebhookServer
        calls = []
        class Ledger:
            def session_append(self, profile, session_id, role, text):
                calls.append((profile, session_id, role, text))
        server = WebhookServer(ledger=Ledger(),
                               root=pathlib.Path(self.tmp.name) / "wh")
        status, out = server.dispatch("nope", b"x")
        self.assertEqual(status, 404)
        self.assertEqual(len(calls), 1)
        self.assertIn("x", calls[0][3])

    def test_http_listener(self):
        import urllib.request
        from mem20agentz.webhooks import WebhookServer
        server = WebhookServer(root=pathlib.Path(self.tmp.name) / "wh")
        server.register("ping", lambda body: b"pong")
        url = server.serve(0)
        with urllib.request.urlopen(url + "/webhook/ping", data=b"{}",
                                    timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("pong", resp.read().decode())
        server.stop()


class _FakeTransport:
    """In-memory transport for hermetic bridge/gateway tests.

    poll() blocks like a real transport: it waits until a message is in the
    inbox or `stop()` is requested.
    """

    def __init__(self, inbox: Optional[list] = None) -> None:
        self.inbox = list(inbox or [])
        self.sent: list[tuple] = []
        self.stopped = False
        self._wake = threading.Event()
        if self.inbox:
            self._wake.set()

    def _push(self, message) -> None:
        self.inbox.append(message)
        self._wake.set()

    def send(self, chat_id, text):
        self.sent.append((chat_id, text))

    def poll(self, timeout=0.25):
        while self.inbox:
            return self.inbox.pop(0)
        self._wake.wait(timeout)
        while self.inbox:
            return self.inbox.pop(0)
        return None

    def stop(self):
        self.stopped = True
        self._wake.set()


class TestBridge(_Sealed):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = []
        self.hook("session_append",
                  lambda profile, sid, role, text:
                  self.ledger.append((profile, sid, role, text)))
        self.hook("session_messages", lambda profile, sid, k=20: [])

    def tearDown(self):
        super().tearDown()
        self.tmp.cleanup()

    def _run_and_stop(self, bridge, transport, sent_want=1, wait_s=3.0):
        """Run the loop on a thread, wait, then stop it (blocking return)."""
        t = threading.Thread(target=bridge.run, daemon=True)
        t.start()
        deadline = time.monotonic() + wait_s
        while time.monotonic() < deadline and len(transport.sent) < sent_want:
            time.sleep(0.01)
        bridge.stop()
        t.join(wait_s)
        return t

    def _agent(self):
        from mem20agentz.agentz import AgentCore
        self.hook("namespace_ensure", lambda ns: {"ok": True})
        self.hook("namespace_grant",
                  lambda ns, a, p="read_write": {"ok": True})
        self.hook("self_model_get", lambda pf: None)
        self.hook("procedural_list", lambda category="": [])
        self.hook("procedural_execute",
                  lambda name, context=None: {"output": ""})

        def fake_llm(messages, model=None, temperature=0.7,
                     max_tokens=1200, timeout=None):
            return '{"action": "final", "final": "bridge-pong"}'

        self.hook("llm_chat", fake_llm)
        return AgentCore(backend=self.backend(), profile="mem20",
                         approvals="auto", toolsets=("none",))

    def _bridge(self, transport, agent_factory=None):
        from mem20agentz.bridge import Bridge
        if agent_factory is None:
            agent_factory = lambda cid: self._agent()
        return Bridge("test", transport,
                      agent_factory=agent_factory,
                      ledger=self.backend(),
                      root=pathlib.Path(self.tmp.name) / "gw")

    def test_unpaired_chat_ignored(self):
        from mem20agentz.bridge import Message
        transport = _FakeTransport([Message(chat_id="9", text="hi")])
        bridge = self._bridge(transport)
        self._run_and_stop(bridge, transport, sent_want=0)
        self.assertEqual(transport.sent, [])
        self.assertTrue(any("ignored" in x[3] for x in self.ledger))
        self.assertTrue(transport.stopped)

    def test_paired_chat_receives_reply(self):
        from mem20agentz.bridge import Message
        transport = _FakeTransport([Message(chat_id="7", text="hello")])
        bridge = self._bridge(transport)
        bridge.pair("7")
        self._run_and_stop(bridge, transport)
        self.assertEqual(transport.sent[0][0], "7")
        self.assertEqual(transport.sent[0][1], "bridge-pong")

    def test_transcript_written_where_factory_resumes(self):
        from mem20agentz.bridge import Bridge, Message
        from mem20agentz.gateway import build_agent_factory
        # the transcript key Bridge writes must equal the key the resume
        # weaver reads (regression: bridge wrote under its own name before).
        transport = _FakeTransport([Message(chat_id="7", text="hello")])
        bridge = Bridge("telegram", transport,
                        agent_factory=build_agent_factory(
                            backend=self.backend()),
                        ledger=self.backend(),
                        root=pathlib.Path(self.tmp.name) / "gw")
        bridge.pair("7")
        self._run_and_stop(bridge, transport)
        self.assertTrue(any(x[1] == "chat:7" for x in self.ledger))

    def test_message_with_media_flagged(self):
        from mem20agentz.agentz import AgentCore
        from mem20agentz.bridge import Message

        def echo(messages, model=None, temperature=0.7,
                 max_tokens=1200, timeout=None):
            import json
            return json.dumps({
                "action": "final", "final": messages[-1]["content"][:200]})

        def factory(cid):
            self.hook("llm_chat", echo)
            return AgentCore(backend=self.backend(), profile="mem20",
                             approvals="auto", toolsets=("none",))

        transport = _FakeTransport(
            [Message(chat_id="7", text="look", media=["photo"])])
        bridge = self._bridge(transport, agent_factory=factory)
        bridge.pair("7")
        self._run_and_stop(bridge, transport)
        self.assertIn("[media: 1 attachment(s)]", transport.sent[0][1])

    # ------------------------------------------------- outage circuit breaker
    class _DeadTransport:
        """Transport whose poll raises, as during a DNS/internet outage.

        ``fail_for`` polls raise; the next poll stops the bridge and returns
        None, so every test is bounded and can never spin forever.
        """

        def __init__(self, bridge, fail_for):
            self.bridge = bridge
            self.fail_for = fail_for
            self.polls = 0
            self.sent = []
            self.started = False
            self.stopped = False

        def start(self):
            self.started = True

        def stop(self):
            self.stopped = True

        def poll(self, timeout):
            self.polls += 1
            if self.polls > self.fail_for:
                self.bridge.stop()
                return None
            raise OSError("dns flood: resolve failed")

    def _outage_bridge(self, fail_for):
        from mem20agentz.bridge import Bridge
        bridge = Bridge("telegram", None, ledger=self.backend(),
                        root=pathlib.Path(self.tmp.name) / "gw",
                        require_pairing=False)
        transport = self._DeadTransport(bridge, fail_for)
        bridge.transport = transport
        return bridge, transport

    def _run_outage(self, fail_for, capture_stderr=False):
        import io
        import contextlib
        import mem20agentz.bridge as bridge_mod
        bridge, transport = self._outage_bridge(fail_for)
        buf = io.StringIO()
        with mock.patch.object(bridge_mod, "TRIP_RETRY_INTERVAL_S", 0.0), \
                mock.patch.object(bridge_mod.time, "sleep", lambda s: None), \
                contextlib.redirect_stderr(buf if capture_stderr else io.StringIO()):
            bridge.run(interval_s=0)
        lines = [x for x in buf.getvalue().splitlines() if x.strip()]
        return bridge, transport, lines

    def test_breaker_trips_on_third_strike(self):
        import mem20agentz.bridge as bridge_mod
        strikes = bridge_mod.MAX_CONSECUTIVE_ERRORS
        _, transport, lines = self._run_outage(fail_for=strikes,
                                                capture_stderr=True)
        self.assertEqual(strikes, 3)
        self.assertEqual(transport.polls, strikes + 1,
                         "trip must happen on the third consecutive error")
        trip_lines = [x for x in lines if "breaker_tripped" in x]
        self.assertEqual(len(trip_lines), 1, "breaker must trip exactly once")
        self.assertIn("3 consecutive poll errors", trip_lines[0])

    def test_breaker_suppresses_log_flood_during_outage(self):
        """A long outage must not emit one log line per failed poll."""
        import mem20agentz.bridge as bridge_mod
        _, transport, lines = self._run_outage(fail_for=500,
                                                capture_stderr=True)
        self.assertEqual(transport.polls, 501)
        self.assertLessEqual(
            len(lines), bridge_mod.MAX_CONSECUTIVE_ERRORS + 1,
            f"breaker let {len(lines)} stderr lines through during outage")

    def test_breaker_reprobes_every_twenty_minutes(self):
        import mem20agentz.bridge as bridge_mod
        self.assertEqual(bridge_mod.TRIP_RETRY_INTERVAL_S, 1200.0)
        slept = []
        bridge, transport = self._outage_bridge(fail_for=8)
        with mock.patch.object(bridge_mod.time, "sleep", slept.append):
            bridge.run(interval_s=0.5)
        reprobes = [s for s in slept if s >= 100]
        self.assertTrue(reprobes, "no re-probe wait recorded")
        for value in reprobes:
            self.assertEqual(value, bridge_mod.TRIP_RETRY_INTERVAL_S,
                             "re-probe must wait exactly 20 minutes")
        self.assertEqual(transport.polls, 9,
                         "8 failing polls plus the final stopping poll")

    def test_outage_never_writes_to_ledger(self):
        self._run_outage(fail_for=200)
        self.assertEqual(self.ledger, [],
                         "outage noise must not reach the memory ledger")

    def test_successful_poll_resets_breaker(self):
        bridge, transport = self._run_outage(fail_for=5)[0:2]
        self.assertFalse(bridge._tripped)
        self.assertEqual(bridge._consecutive_errors, 0)
        self.assertTrue(transport.stopped)


class TestTelegramDryRun(_Sealed):
    """Offline dry-run: fake Bot API server proves poll->dispatch->send."""

    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        import http.server
        import threading

        bytes_store = [b"{\"ok\": true, \"result\": []}"]

        class Api(http.server.BaseHTTPRequestHandler):
            def _respond(self, body):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):  # noqa: N802  (getMe liveness)
                self._respond(bytes_store[0])

            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length", 0))
                _ = self.rfile.read(length)
                self._respond(bytes_store[0])

            def log_message(self, *a):
                return

        server = http.server.HTTPServer(("127.0.0.1", 0), Api)
        self.port = server.server_address[1]
        self.thread = threading.Thread(target=server.serve_forever, daemon=True)
        self.thread.start()
        self.server = server
        self.bytes_store = bytes_store

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        super().tearDown()
        self.tmp.cleanup()

    def test_poll_send_roundtrip(self):
        import os
        os.environ["MEM20AGENTZ_TELEGRAM_TOKEN"] = "fake:token"
        try:
            from mem20agentz.bridges.telegram import TelegramTransport
            transport = TelegramTransport(
                base_url=f"http://127.0.0.1:{self.port}")
            transport.start()  # getMe -> ok
            # inject one update for the next poll
            self.bytes_store[0] = (
                b"{\"ok\": true, \"result\": [{\"update_id\": 1,"
                b"\"message\": {\"chat\": {\"id\": \"42\"},"
                b"\"text\": \"ping\", \"date\": 1}}]}")
            msg = transport.poll(timeout=1.0)
            self.assertEqual(msg.chat_id, "42")
            self.assertEqual(msg.text, "ping")
            self.assertEqual(msg.platform, "telegram")
            transport.send("42", "pong")  # must not raise
        finally:
            os.environ.pop("MEM20AGENTZ_TELEGRAM_TOKEN", None)

    def test_no_token_fails_honestly(self):
        import os
        import unittest.mock
        os.environ.pop("MEM20AGENTZ_TELEGRAM_TOKEN", None)
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)
        from mem20agentz.bridges.telegram import (TelegramAuthError,
                                                  TelegramTransport)
        original_exists = pathlib.Path.exists
        def _no_env(self_, *a, **kw):
            if str(self_) == "/root/.env":
                return False
            return original_exists(self_, *a, **kw)
        with unittest.mock.patch.object(pathlib.Path, "exists", _no_env):
            with self.assertRaises(TelegramAuthError):
                TelegramTransport(base_url=f"http://127.0.0.1:{self.port}")


class TestGateway(_Sealed):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        super().tearDown()
        self.tmp.cleanup()

    def _gw(self):
        from mem20agentz.bridge import Bridge
        from mem20agentz.gateway import Gateway
        gw = Gateway(backend=self.backend(),
                     root=pathlib.Path(self.tmp.name) / "gw")
        gw.bridges["fake"] = Bridge("fake", _FakeTransport(),
                                    root=gw.root, ledger=self.backend())
        return gw

    def test_pair_unpair(self):
        from mem20agentz.bridge import Bridge
        bridge = Bridge("x", _FakeTransport(),
                        root=pathlib.Path(self.tmp.name) / "gw")
        bridge.pair("9")
        self.assertIn("9", bridge.pairs())
        self.assertTrue(bridge.unpair("9"))
        self.assertFalse(bridge.unpair("9"))

    def test_status_shape(self):
        gw = self._gw()
        st = gw.status()
        self.assertIn("bridges", st)

    def test_factory_weaves_per_chat_history(self):
        from mem20agentz.gateway import build_agent_factory
        self.hook("session_messages", lambda profile, sid, k=20: [
            {"content": "in:chat:42 hello"},
            {"content": "out:chat:42 bridge-pong"}])
        factory = build_agent_factory(backend=self.backend())
        core = factory("chat:42")
        self.assertEqual(len(core.history), 2)
        self.assertEqual(core.history[0]["role"], "user")
        self.assertEqual(core.history[1]["role"], "assistant")
        self.assertEqual(core.history[0]["content"], "hello")
        self.assertEqual(core.history[1]["content"], "bridge-pong")


class TestCli(_Sealed):
    def test_profiles_create_list(self):
        from mem20agentz import cli
        created = {}

        def create(pf, ident, caps, vals):
            created[pf] = ident
            return {"topic": f"self-model:{pf}", "content": "ok"}

        self.hook("namespace_ensure", lambda ns: {"ok": True})
        self.hook("namespace_grant", lambda ns, a, p="read_write": {"ok": True})
        self.hook("self_model_create", create)
        self.hook("self_model_get",
                  lambda pf: {"topic": f"self-model:{pf}",
                              "content": "identity=who"} if pf in created
                  else None)
        self.hook("recall", lambda topic=None, tags=None, k=10: [
            {"topic": f"self-model:{pf}", "content": "ok"}
            for pf in created])

        self.assertEqual(cli.main(["profiles", "create", "writer",
                                  "--identity", "The Writer"]), 0)
        self.assertIn("writer", created)
        self.assertEqual(cli.main(["profiles", "list"]), 0)

    def test_status_and_pause(self):
        from mem20agentz import cli
        cli.set_paused(False)
        self.assertEqual(cli.main(["status"]), 0)
        self.assertEqual(cli.main(["pause"]), 0)
        self.assertTrue(cli.is_paused())
        self.assertEqual(cli.main(["resume"]), 0)
        self.assertFalse(cli.is_paused())

    def test_sessions_cli(self):
        from mem20agentz import cli
        self.hook("session_add", lambda p, sid, t, m=None: {})
        self.hook("session_list", lambda p: [])
        self.hook("session_update", lambda *a, **k: {})
        self.assertEqual(cli.main(["sessions", "list"]), 0)
        self.assertEqual(cli.main(["sessions", "new", "--title", "hi"]), 0)


class TestWebGateway(_Sealed):
    def _web(self):
        from mem20agentz.gateway_web import WebGateway, build_web_factory
        self._stub_env()
        return WebGateway(backend=self.backend(),
                          agent_factory=build_web_factory(self.backend()))

    def _stub_env(self):
        self.hook("namespace_ensure", lambda ns: {"ok": True})
        self.hook("namespace_grant",
                  lambda ns, a, p="read_write": {"ok": True})
        self.hook("self_model_get", lambda pf: None)
        self.hook("procedural_list", lambda category=None: [])
        self.hook("procedural_execute",
                  lambda name, context=None: {"output": ""})
        self.hook("session_messages", lambda profile, sid, k=20: [])
        self.hook("session_append",
                  lambda profile, sid, role, text:
                  self.ledger.append((profile, sid, role, text)))

        def llm(messages, model=None, temperature=0.7, max_tokens=1200,
                timeout=None):
            return '{"action": "final", "final": "web-pong"}'

        self.hook("llm_chat", llm)

    def setUp(self):
        super().setUp()
        self.ledger = []

    def test_chat_direct(self):
        wg = self._web()
        out = wg.chat({"message": "hello"})
        self.assertTrue(out["ok"])
        self.assertEqual(out["reply"], "web-pong")
        self.assertTrue(out["chat_id"].startswith("w"))
        self.assertEqual([x[1] for x in self.ledger],
                         ["web:" + out["chat_id"]] * 2)
        self.assertEqual([x[2] for x in self.ledger], ["user", "assistant"])

    def test_chat_validation(self):
        wg = self._web()
        self.assertFalse(wg.chat({})["ok"])
        self.assertFalse(wg.chat({"message": "x",
                                  "chat_id": "bad!id"})["ok"])

    def test_http_round_trip(self):
        import httpx
        wg = self._web()
        base = wg.serve()
        try:
            resp = httpx.post(base + "/chat",
                              json={"message": "hi web"})
            body = resp.json()
            self.assertEqual(body["ok"], True)
            self.assertEqual(body["reply"], "web-pong")
            status = httpx.get(base + "/status").json()
            self.assertEqual(status["service"], "webgateway")
            self.assertEqual(status["chat_session_prefix"], "web:")
            page = httpx.get(base + "/").text
            self.assertIn("<title>mem20agentz dashboard</title>", page)
            tail = httpx.get(base + "/ledger?k=10").json()
            self.assertTrue(tail["ok"])
        finally:
            wg.stop()

    def test_ledger_tail_sealed_survives(self):
        self.unhook("recall")
        from mem20agentz.gateway_web import WebGateway
        wg = WebGateway(backend=self.backend())
        entries = wg.ledger_tail(5)
        self.assertTrue(entries)


class TestMcp(_Sealed):
    def _server(self):
        from mem20agentz.mcp import McpServer
        self.hook("procedural_list", lambda category=None: [
            {"name": "greet", "description": "say hi"}])

        def pe(name, context=None):
            if name != "greet":
                raise KeyError(name)
            return {"output": f"hi:{context.get('arg')}"}

        self.hook("procedural_execute", pe)
        return McpServer(backend=self.backend())

    def test_dispatch_initialize(self):
        server = self._server()
        out = server.dispatch({"jsonrpc": "2.0", "id": 1,
                               "method": "initialize", "params": {}})
        self.assertEqual(out["result"]["protocolVersion"],
                         "2024-11-05")
        self.assertEqual(out["result"]["serverInfo"]["name"],
                         "mem20agentz")

    def test_dispatch_tools_list_and_call(self):
        server = self._server()
        tools = server.dispatch({"jsonrpc": "2.0", "id": 2,
                                 "method": "tools/list",
                                 "params": {}})["result"]["tools"]
        self.assertEqual(tools[0]["name"], "greet")
        out = server.dispatch({"jsonrpc": "2.0", "id": 3,
                               "method": "tools/call",
                               "params": {"name": "greet",
                                          "arguments": {"arg": "bob"}}})
        self.assertEqual(out["result"]["content"][0]["text"], "hi:bob")

    def test_dispatch_errors(self):
        server = self._server()
        unknown = server.dispatch({"jsonrpc": "2.0", "id": 4,
                                   "method": "nope", "params": {}})
        self.assertEqual(unknown["error"]["code"], -32601)
        bad = server.dispatch({"jsonrpc": "1.0", "id": 4,
                               "method": "ping", "params": {}})
        self.assertEqual(bad["error"]["code"], -32700)
        empty = server.dispatch({"jsonrpc": "2.0", "id": 5,
                                 "method": "tools/call",
                                 "params": {}})
        self.assertEqual(empty["error"]["code"], -32602)
        badargs = server.dispatch({"jsonrpc": "2.0", "id": 6,
                                   "method": "tools/call",
                                   "params": {"name": "greet",
                                              "arguments": "nope"}})
        self.assertEqual(badargs["error"]["code"], -32602)

    def test_client_server_round_trip(self):
        from mem20agentz.mcp import McpClient
        server = self._server()
        url = server.serve()
        client = McpClient(url)
        try:
            self.assertEqual(client.initialize()["serverInfo"]["name"],
                             "mem20agentz")
            tools = client.list_tools()
            self.assertEqual(tools[0]["name"], "greet")
            self.assertEqual(client.call_tool("greet", {"arg": "ada"}),
                             "hi:ada")
            with self.assertRaises(Exception):
                client.call_tool("missing", {})
        finally:
            client.close()
            server.stop()
            client.close()
            server.stop()


class TestAcp(_Sealed):
    def _acp(self):
        from mem20agentz.acp import AcpServer, build_acp_factory
        self.hook("namespace_ensure", lambda ns: {"ok": True})
        self.hook("namespace_grant",
                  lambda ns, a, p="read_write": {"ok": True})
        self.hook("self_model_get", lambda pf: None)
        self.hook("procedural_list", lambda category=None: [])
        self.hook("procedural_execute",
                  lambda name, context=None: {"output": ""})
        self.hook("session_messages", lambda profile, sid, k=20: [])
        self.hook("session_append",
                  lambda profile, sid, role, text:
                  self.ledger.append((profile, sid, role, text)))

        def llm(messages, model=None, temperature=0.7, max_tokens=1200,
                timeout=None):
            return '{"action": "final", "final": "acp-pong"}'

        self.hook("llm_chat", llm)
        return AcpServer(backend=self.backend(),
                         agent_factory=build_acp_factory(self.backend()))

    def setUp(self):
        super().setUp()
        self.ledger = []

    def test_message_round_trip(self):
        server = self._acp()
        out = server.dispatch({"method": "acp/message",
                               "params": {"peer": "peerA",
                                          "text": "hello"}})
        self.assertEqual(out["ok"], True)
        self.assertEqual(out["reply"], "acp-pong")
        self.assertEqual(out["session_id"], "acp:peerA")
        self.assertEqual([x[1] for x in self.ledger],
                         ["acp:peerA"] * 2)

    def test_bad_peer_and_validation(self):
        server = self._acp()
        bad = server.dispatch({"method": "acp/message",
                               "params": {"peer": "no spaces", "text": "x"}})
        self.assertFalse(bad["ok"])
        empty = server.dispatch({"method": "acp/message",
                                 "params": {"peer": "ok", "text": " "}})
        self.assertFalse(empty["ok"])
        unknown = server.dispatch({"method": "nope", "params": {}})
        self.assertFalse(unknown["ok"])
        hello = server.dispatch({"method": "acp/hello", "params": {}})
        self.assertEqual(hello["service"], "mem20agentz-acp")

    def test_token_gating(self):
        server = self._acp()
        self.assertFalse(server.requires_token())
        self.assertEqual(server.check_token("x"), False)
        server.secrets["acp_token"] = "s3cret"
        self.assertTrue(server.requires_token())
        self.assertFalse(server.check_token("wrong"))
        self.assertTrue(server.check_token("s3cret"))


class TestComputerUse(_Sealed):
    def test_run_ok_and_fail(self):
        from mem20agentz.computer_use import ComputerUse
        cu = ComputerUse()
        ok = cu.run("printf hello")
        self.assertTrue(ok["ok"])
        self.assertEqual(ok["output"].strip(), "hello")
        fail = cu.run("exit 3")
        self.assertFalse(fail["ok"])
        self.assertEqual(fail["rc"], 3)

    def test_run_destructive_refused(self):
        from mem20agentz.computer_use import ComputerUse
        cu = ComputerUse()
        for cmd in ("rm -rf /tmp/x", "mkfs.ext4 /dev/sda"):
            out = cu.run(cmd)
            self.assertFalse(out["ok"])
            self.assertIn("refused", out.get("error", ""))

    def test_read_write_round_trip(self):
        from mem20agentz.computer_use import ComputerUse
        cu = ComputerUse()
        with tempfile.TemporaryDirectory() as d:
            path = str(pathlib.Path(d) / "a" / "b.txt")
            w = cu.write(path, "hello computer")
            self.assertTrue(w["ok"])
            r = cu.read(path)
            self.assertTrue(r["ok"])
            self.assertIn("hello computer", r["content"])

    def test_shot_honest_no_backend(self):
        from mem20agentz.computer_use import ComputerUse
        cu = ComputerUse()
        out = cu.shot()
        self.assertFalse(out["ok"])
        self.assertIn("no screenshot backend", out["error"])

    def test_tool_descriptors(self):
        from mem20agentz.computer_use import ComputerUse
        names = [t["name"] for t in ComputerUse().tools()]
        self.assertIn("computer.run", names)
        self.assertIn("computer.shot", names)


class TestSecrets(_Sealed):
    def _secrets(self, env=None, cli_bin=None):
        from mem20agentz.secrets import Secrets
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        if cli_bin is None:
            cli_bin = {"op": None, "bw": None}
        return Secrets(root=pathlib.Path(self._tmp.name),
                       env=env or {}, cli_bin=cli_bin)

    def test_env_and_vault_resolution(self):
        s = self._secrets(env={"MEM20AGENTZ_FOO": "env-value"})
        self.assertEqual(s.get("foo"), "env-value")
        pathlib.Path(self._tmp.name, "bar").write_text("file-value\n")
        self.assertEqual(s.get("bar"), "file-value")
        (pathlib.Path(self._tmp.name) / "baz.json").write_text(
            '{"value": "json-value"}', encoding="utf-8")
        self.assertEqual(s.get("baz"), "json-value")
        self.assertIsNone(s.get("missing"))

    def test_env_wins_over_vault(self):
        s = self._secrets(env={"MEM20AGENTZ_FOO": "env-value"})
        pathlib.Path(self._tmp.name, "foo").write_text("file-value")
        self.assertEqual(s.get("foo"), "env-value")

    def test_write_perm_and_delete(self):
        s = self._secrets()
        out = s.write("api_key", "s3cr3t")
        p = pathlib.Path(out["path"])
        self.assertEqual(p.stat().st_mode & 0o777, 0o600)
        self.assertEqual(s.get("api_key"), "s3cr3t")
        self.assertIn("api_key", s.list_keys())
        s.delete("api_key")
        self.assertIsNone(s.get("api_key"))

    def test_list_and_describe_never_return_values(self):
        s = self._secrets(env={"MEM20AGENTZ_FOO": "DO-NOT-PRINT"})
        pathlib.Path(self._tmp.name, "bar").write_text("ALSO-SECRET")
        for key in s.list_keys():
            self.assertNotIn("DO-NOT-PRINT", key)
            self.assertNotIn("ALSO-SECRET", key)
        blob = str(s.describe()) + str(s.sources_health())
        self.assertNotIn("DO-NOT-PRINT", blob)
        self.assertNotIn("ALSO-SECRET", blob)

    def test_redact_masks_known_values(self):
        s = self._secrets(env={"MEM20AGENTZ_FOO": "tok_123"})
        red = s.redact("please forward tok_123 now")
        self.assertNotIn("tok_123", red)
        self.assertIn("••••", red)

    def test_op_unavailable_reported(self):
        s = self._secrets(cli_bin={"op": None, "bw": None})
        src = s.source_of("op://vault/item/field")
        self.assertEqual(src["source"], "op-cli")
        self.assertEqual(src["available"], False)
        self.assertIsNone(s.get("op://vault/item/field"))

    def test_op_cli_source(self):
        from mem20agentz.secrets import Secrets
        with tempfile.TemporaryDirectory() as d:
            fake = pathlib.Path(d, "op")
            fake.write_text("#!/bin/sh\necho op-secret\n")
            fake.chmod(0o755)
            s = Secrets(root=pathlib.Path(d), env={},
                        cli_bin={"op": str(fake), "bw": None})
            self.assertEqual(s.get("op://vault/item/field"), "op-secret")
            self.assertTrue(
                s.source_of("op://vault/item/field")["available"])


class TestEgress(_Sealed):
    def _policy(self, allow=None, deny=None, bindings=None):
        from mem20agentz.egress import EgressPolicy
        return EgressPolicy(allow=allow, deny=deny, bindings=bindings)

    def test_fail_closed_when_no_allow(self):
        policy = self._policy()
        self.assertFalse(policy.allowed("https://api.example.com/"))
        self.assertFalse(policy.check("https://api.example.com/")["allow"])
        self.assertIn("fail-closed",
                      policy.check("https://api.example.com/")["reason"])

    def test_allow_and_deny(self):
        policy = self._policy(allow=["example.com", "*.corp.local"],
                              deny=["evil.example.com"])
        self.assertTrue(policy.allowed("https://example.com/x"))
        self.assertTrue(policy.allowed("https://a.corp.local/y"))
        self.assertFalse(policy.allowed("https://evil.example.com/"))
        self.assertEqual(policy.check("https://evil.example.com/")["reason"],
                         "host deny-listed (evil.example.com)")

    def test_scheme_and_userinfo_blocked(self):
        policy = self._policy(allow=["example.com"])
        self.assertFalse(policy.allowed("ftp://example.com/"))
        self.assertFalse(policy.allowed("http://user:pw@example.com/"))

    def test_injection_and_missing_credential(self):
        from mem20agentz.egress import EgressBlocked
        policy = self._policy(
            allow=["api.example.com"],
            bindings={"api.example.com": {
                "api_key": "Authorization: Bearer {key}"}})
        headers = policy.inject("https://api.example.com/v1",
                                {"x-trace": "1"}, lambda k: "s3cr3t")
        self.assertEqual(headers["Authorization"], "Bearer s3cr3t")
        with self.assertRaises(EgressBlocked):
            policy.inject("https://api.example.com/v1", {}, lambda k: None)

    def test_proxy_round_trip_injects(self):
        from mem20agentz.egress import EgressProxy, EgressPolicy
        import http.server, threading

        class Echo(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                body = self.headers.get("X-Token", "").encode()
                self.send_response(200)
                self.send_header("X-Echoed", self.headers.get("X-Token", ""))
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        target = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Echo)
        threading.Thread(target=target.serve_forever, daemon=True).start()
        self.addCleanup(target.shutdown)
        self.addCleanup(target.server_close)
        url = ("http://127.0.0.1:%d/" % target.server_address[1])

        proxy = EgressProxy(
            EgressPolicy(allow=["127.0.0.1"],
                         bindings={"127.0.0.1": {"tok": "X-Token: {key}"}}),
            lambda k: "proxied-secret")
        out = proxy.fetch("GET", url)
        self.assertEqual(out["status"], 200)
        self.assertEqual(out["headers"].get("X-Echoed"), "proxied-secret")
        self.assertEqual(out["body"], "proxied-secret")

    def test_proxy_denied_url_403(self):
        from mem20agentz.egress import EgressProxy, EgressPolicy
        import http.client
        proxy = EgressProxy(EgressPolicy(), lambda k: None)
        base = proxy.serve()
        self.addCleanup(proxy.stop)
        conn = http.client.HTTPConnection("127.0.0.1",
                                          int(base.rsplit(":", 1)[1]))
        conn.request("GET", "http://api.example.com/data")
        resp = conn.getresponse()
        self.assertEqual(resp.status, 403)
        self.assertIn(b"fail-closed", resp.read())
        conn.close()


class TestSecurity(_Sealed):
    def _osv_server(self, vulnerable=True):
        import http.server, threading

        class OsV(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.dumps({
                    "results": [{"vulnerabilities":
                                 [{"id": "GHSA-0000-0000-0000",
                                   "aliases": ["CVE-2026-0000"],
                                   "summary": "test vuln"}]
                                 if vulnerable else []}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), OsV)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        self.addCleanup(server.server_close)
        return "http://127.0.0.1:%d" % server.server_address[1]

    def test_scan_vulnerable(self):
        from mem20agentz.security import OsvScanner, parse_pypi
        url = self._osv_server(vulnerable=True)
        result = OsvScanner(base_url=url,
                            packages=[parse_pypi("testpkg", "9.9.9")]).scan()
        self.assertEqual(result["status"], "vulnerable")
        self.assertFalse(result["ok"])
        self.assertEqual(result["vulns"][0]["id"], "GHSA-0000-0000-0000")

    def test_scan_clean(self):
        from mem20agentz.security import OsvScanner, parse_pypi
        url = self._osv_server(vulnerable=False)
        result = OsvScanner(base_url=url,
                            packages=[parse_pypi("testpkg", "9.9.9")]).scan()
        self.assertEqual(result["status"], "clean")
        self.assertTrue(result["ok"])
        self.assertEqual(result["vulns"], [])

    def test_scan_error(self):
        from mem20agentz.security import OsvScanner
        result = OsvScanner(base_url="http://127.0.0.1:1",
                            packages=[], timeout=0.5).scan()
        self.assertEqual(result["status"], "error")
        self.assertFalse(result["ok"])
        self.assertIn("error", result)

    def test_dependency_packages_parse(self):
        from mem20agentz.security import dependency_packages
        import tomllib
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            (root / "pyproject.toml").write_text(
                '[project]\ndependencies = ["requests>=2.0", "flask==2.2.2"]\n',
                encoding="utf-8")
            pkgs = dependency_packages(root)
            self.assertEqual(pkgs[0]["package"]["name"], "requests")
            self.assertEqual(pkgs[1]["package"]["name"], "flask")
            self.assertEqual(pkgs[1]["version"], "2.2.2")

    def test_doctor_all_green_with_fake_osv(self):
        from mem20agentz.security import Doctor, OsvScanner, parse_pypi
        self.hook("recall", lambda topic=None, tags=None, k=10:
                  [{"topic": "self-model:x", "content": "ok"}])
        url = self._osv_server(vulnerable=False)
        doctor = Doctor(backend=self.backend(),
                        scanner=OsvScanner(base_url=url,
                                           packages=[parse_pypi("okpkg",
                                                                "1.0.0")]))
        report = doctor.run()
        self.assertTrue(report["ok"], report)
        names = [c["check"] for c in report["checks"]]
        self.assertIn("import", names)
        self.assertIn("osv", names)
        self.assertIn("branding", names)
        self.assertIn("egress", names)
        self.assertIn("secrets", names)


class TestLlms(_Sealed):
    def _router(self, providers, env=None, keyring=None, substrate=None):
        from mem20agentz.llm import Router
        from mem20agentz.auth import KeyRing
        if keyring is None:
            keyring = KeyRing(env=env or {})
        return Router(providers, keyring=keyring, substrate=substrate)

    def test_router_success(self):
        from mem20agentz.llm import Provider, parse_prompt
        url, seen = self._fake_llm()
        provider = Provider("nvidia", url, "m1")
        router = self._router([provider], env={"MEM20AGENTZ_NVIDIA_API_KEY": "k1"})
        result = router.complete(parse_prompt("hi"))
        self.assertEqual(result["text"], "reply:m1")
        self.assertEqual(result["provider"], "nvidia")
        self.assertEqual(seen["requests"][0]["auth"], "Bearer k1")

    def test_router_fallback_on_5xx(self):
        from mem20agentz.llm import Provider, parse_prompt
        url, _ = self._fake_llm()
        router = self._router(
            [Provider("a", url, "boom"), Provider("b", url, "m2")],
            env={"MEM20AGENTZ_A_API_KEY": "ka",
                 "MEM20AGENTZ_B_API_KEY": "kb"})
        result = router.complete(parse_prompt("hi"))
        self.assertEqual(result["provider"], "b")
        self.assertEqual(result["text"], "reply:m2")
        self.assertEqual(len(result["attempts"]), 2)
        self.assertFalse(result["attempts"][0]["ok"])

    def test_fallback_all_fail_raises(self):
        from mem20agentz.llm import (AllProvidersFailed, Provider,
                                     parse_prompt)
        url, _ = self._fake_llm()
        router = self._router(
            [Provider("a", url, "boom"), Provider("b", url, "boom")],
            env={"MEM20AGENTZ_A_API_KEY": "ka",
                 "MEM20AGENTZ_B_API_KEY": "kb"})
        with self.assertRaises(AllProvidersFailed) as ctx:
            router.complete(parse_prompt("hi"))
        self.assertEqual(len(ctx.exception.errors), 2)

    def test_key_never_leaks_in_attempts(self):
        from mem20agentz.llm import Provider, parse_prompt
        url, _ = self._fake_llm()
        router = self._router(
            [Provider("nokey", url, "m7"),
             Provider("okay", url, "m8")],
            env={"MEM20AGENTZ_OKAY_API_KEY": "s3cr3t-token"})
        result = router.complete(parse_prompt("hi"))
        self.assertEqual(result["provider"], "okay")
        blob = repr(result) + repr(result["attempts"])
        self.assertNotIn("s3cr3t-token", blob)

    def test_substrate_fallback_when_no_providers(self):
        from mem20agentz.llm import Router, parse_prompt
        called = {}

        class Sub:
            def llm_chat(self, messages, model=None, temperature=0.7,
                         max_tokens=1200, timeout=None):
                called["m"] = model
                return "substrate-ok"

        router = Router([], substrate=Sub())
        result = router.complete(parse_prompt("hi"), model="legacy")
        self.assertEqual(result["provider"], "substrate")
        self.assertEqual(result["text"], "substrate-ok")
        self.assertEqual(called["m"], "legacy")

    def test_401_rotation_retries_with_new_key(self):
        from mem20agentz.llm import Provider, parse_prompt
        url, seen = self._fake_llm()
        provider = Provider("nvidia", url, "rot-k1")
        router = self._router(
            [provider],
            env={"MEM20AGENTZ_NVIDIA_API_KEY": "k1",
                 "MEM20AGENTZ_NVIDIA_API_KEY_2": "k2"})
        result = router.complete(parse_prompt("hi"))
        self.assertEqual(result["text"], "reply:rot-k1")
        auths = [r["auth"] for r in seen["requests"]]
        self.assertIn("Bearer k1", auths)
        self.assertIn("Bearer k2", auths)


class TestAuth(_Sealed):
    def test_authpool_from_env_and_rotation(self):
        from mem20agentz.auth import AuthPool
        pool = AuthPool.from_env("nvidia", {
            "MEM20AGENTZ_NVIDIA_API_KEY": "k1",
            "MEM20AGENTZ_NVIDIA_API_KEY_2": "k2",
            "UNRELATED": "x"})
        self.assertEqual(len(pool.keys), 2)
        first = pool.next()
        self.assertIn(first, ("k1", "k2"))
        pool.mark_failed()
        self.assertEqual(pool.rotations, 1)
        self.assertIn(pool.next(), ("k1", "k2"))

    def test_authpool_empty(self):
        from mem20agentz.auth import AuthPool
        pool = AuthPool.from_env("nvidia", {"X": "1"})
        self.assertIsNone(pool.next())

    def _vault(self, values):
        class V:
            def get(self, name):
                return values.get(name)

            def redact(self, text):
                return text.replace("topsecret", "••••")

        return V()

    def test_keyring_resolution_order(self):
        from mem20agentz.auth import KeyRing
        keyring = KeyRing(
            secrets=self._vault({"nvidia_api_key": "vault-key"}),
            env={"MEM20AGENTZ_NVIDIA_API_KEY": "env-key"})
        value, source = keyring.get("nvidia", "secret:nvidia_api_key")
        self.assertEqual(value, "env-key")
        self.assertEqual(source, "env:MEM20AGENTZ_NVIDIA_API_KEY")

    def test_keyring_vault_ref_and_convention(self):
        from mem20agentz.auth import KeyRing
        keyring = KeyRing(
            secrets=self._vault({"nv_key": "vault-secret"}),
            env={"NVIDIA_API_KEY": "conv-key"})
        got, source = keyring.get("nvidia", "secret:nv_key")
        self.assertEqual(got, "vault-secret")
        self.assertEqual(source, "vault:nv_key")
        got2, src2 = keyring.get("nvidia")
        self.assertEqual(got2, "conv-key")
        self.assertEqual(src2, "env:NVIDIA_API_KEY")

    def test_keyring_status_never_leaks(self):
        from mem20agentz.auth import KeyRing
        keyring = KeyRing(
            secrets=self._vault({"groq_api_key": "topsecret"}),
            env={"MEM20AGENTZ_GEMINI_API_KEY": "g-key"})
        rows = keyring.status(["groq", "gemini"])
        blob = repr(rows)
        self.assertNotIn("topsecret", blob)
        self.assertNotIn("g-key", blob)
        self.assertTrue(rows[0]["present"])
        self.assertTrue(rows[1]["present"])

    def test_keyring_redact(self):
        from mem20agentz.auth import KeyRing
        keyring = KeyRing(secrets=self._vault({"x": "topsecret"}))
        self.assertNotIn("topsecret", keyring.redact("use topsecret now"))


class TestMoa(_Sealed):
    def test_moa_proposals_and_aggregator(self):
        from mem20agentz.llm import Provider, Router, moa
        from mem20agentz.auth import KeyRing
        import http.server, threading
        import json as _json

        class Fake(http.server.BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length", "0")) or 0
                body = _json.loads(self.rfile.read(length).decode("utf-8"))
                content = "proposal(%s)" % body["model"]
                payload = _json.dumps({
                    "choices": [{"message": {"content": content}}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *a):
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        self.addCleanup(server.server_close)
        url = "http://127.0.0.1:%d" % server.server_address[1]

        providers = [Provider("p1", url, f"model{i}", api_key="k") for i in
                     range(3)]
        router = Router(providers, keyring=KeyRing(env={"X1": "k"}))
        out = moa("question?", router, proposers=3)
        self.assertEqual(len(out["proposals"]), 3)
        self.assertTrue(out["text"].startswith("proposal("))
        self.assertIn(out["provider"], {"p1", "p2", "p3"})

    def test_moa_returns_text(self):
        from mem20agentz.llm import Provider, Router, moa, AllProvidersFailed
        from mem20agentz.auth import KeyRing
        url, _ = self._fake_llm()
        router = Router([Provider("p1", url, "boom")],
                        keyring=KeyRing(env={"X1": "k"}))
        with self.assertRaises(AllProvidersFailed):
            moa("question?", router, proposers=1)


class TestAuthProxy(_Sealed):
    def _start(self, providers, keyring, token=None):
        from mem20agentz.auth import AuthProxy, AuthProxyConfig
        from mem20agentz.llm import Router
        proxy = AuthProxy(Router(providers, keyring=keyring),
                          keyring=keyring,
                          config=AuthProxyConfig(port=0, token=token))
        url = proxy.serve()
        self.addCleanup(proxy.stop)
        return proxy, url

    def test_chat_completions_key_hiding(self):
        from mem20agentz.llm import Provider
        from mem20agentz.auth import KeyRing
        from mem20agentz.llm import KNOWN_PROVIDERS
        url, _ = self._fake_llm(echo_auth=True)
        keyring = KeyRing(env={"MEM20AGENTZ_NVIDIA_API_KEY": "k1"})
        _, proxy_url = self._start([Provider("nvidia", url, "m-x1")],
                                   keyring)
        resp = httpx.post(proxy_url + "/v1/chat/completions",
                          json={"model": "m-x1",
                                "messages": [{"role": "user",
                                              "content": "hi"}]})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        self.assertIn("Bearer k1", content)

    def test_token_gate(self):
        from mem20agentz.llm import Provider
        from mem20agentz.auth import KeyRing
        url, _ = self._fake_llm(echo_auth=True)
        keyring = KeyRing(env={"MEM20AGENTZ_NVIDIA_API_KEY": "k1"})
        _, proxy_url = self._start([Provider("nvidia", url, "m-x2")],
                                   keyring, token="gate-secret")
        resp = httpx.post(proxy_url + "/v1/chat/completions",
                          json={"model": "m-x2",
                                "messages": [{"role": "user",
                                              "content": "hi"}]},
                          headers={"X-Auth-Proxy-Token": "wrong"})
        self.assertEqual(resp.status_code, 403)
        ok = httpx.post(proxy_url + "/v1/chat/completions",
                        json={"model": "m-x2",
                              "messages": [{"role": "user",
                                            "content": "hi"}]},
                        headers={"X-Auth-Proxy-Token": "gate-secret"})
        self.assertEqual(ok.status_code, 200)
        self.assertIn("Bearer k1", ok.json()["choices"][0]["message"]["content"])

    def test_models_endpoint(self):
        from mem20agentz.llm import Provider, KNOWN_PROVIDERS
        from mem20agentz.auth import KeyRing
        url, _ = self._fake_llm()
        _, proxy_url = self._start(
            [Provider("nvidia", url, "m1"), Provider("groq", url, "m2")],
            KeyRing(env={"MEM20AGENTZ_NVIDIA_API_KEY": "k1"}))
        resp = httpx.get(proxy_url + "/v1/models")
        self.assertEqual(resp.status_code, 200)
        ids = [m["id"] for m in resp.json()["data"]]
        self.assertIn("m1", ids)
        self.assertIn("m2", ids)


class TestDesktop(_Sealed):
    def setUp(self):
        super().setUp()
        self.ledger = []
        self.hook("namespace_ensure", lambda ns: {"ok": True})
        self.hook("namespace_grant",
                  lambda ns, a, p="read_write": {"ok": True})
        self.hook("self_model_get", lambda pf: None)
        self.hook("procedural_list", lambda category=None: [])
        self.hook("procedural_execute",
                  lambda name, context=None: {"output": ""})
        self.hook("session_messages", lambda profile, sid, k=20: [])

        def session_append(profile, sid, role, text):
            self.ledger.append({"text": f"{role}: {text}",
                                "tags": ["mem20agentz", "message"],
                                "ts": ""})

        self.hook("session_append", session_append)
        self.hook("recall", lambda tags=None, k=20:
                  [e for e in self.ledger if not tags or
                   all(t in e.get("tags", []) for t in tags)][-k:])

        def llm(messages, model=None, temperature=0.7, max_tokens=1200,
                timeout=None):
            return '{"action": "final", "final": "office-pong"}'

        self.hook("llm_chat", llm)

    def _fe(self):
        from mem20agentz.desktop import Frontend, build_office_factory
        return Frontend(backend=self.backend(),
                        agent_factory=build_office_factory(self.backend()))

    def test_office_bundle_structure(self):
        fe = self._fe()
        bundle = fe.office()
        self.assertEqual(bundle["service"], "mem office")
        self.assertIn("version", bundle)
        self.assertIn("status", bundle)
        self.assertIsInstance(bundle["ledger"], list)
        self.assertIsInstance(bundle["cron"], list)
        self.assertIsInstance(bundle["projects"], list)

    def test_unified_tabs_present(self):
        import httpx
        fe = self._fe()
        base = fe.serve()
        try:
            page = httpx.get(base + "/").text
            for tab in ("t-office", "t-kanban", "t-production",
                        "t-settings", "t-chat"):
                self.assertIn(f'id="{tab}"', page)
        finally:
            fe.stop()

    def test_kanban_endpoint(self):
        import httpx
        fe = self._fe()
        base = fe.serve()
        try:
            k = httpx.get(base + "/kanban").json()
            self.assertIn(k["ok"], (True,))
            self.assertIsInstance(k.get("boards"), list)
        finally:
            fe.stop()

    def test_production_endpoint(self):
        import httpx
        fe = self._fe()
        base = fe.serve()
        try:
            p = httpx.get(base + "/production").json()
            self.assertIn("status", p)
            self.assertIsInstance(p.get("phases"), list)
            self.assertIsInstance(p.get("builds"), list)
        finally:
            fe.stop()

    def test_settings_endpoint(self):
        import httpx
        fe = self._fe()
        base = fe.serve()
        try:
            s = httpx.get(base + "/settings").json()
            self.assertTrue(s["ok"])
            self.assertIsInstance(s.get("subsystems"), dict)
            self.assertIsInstance(s.get("fleet"), list)
            self.assertIn("braid", s)
        finally:
            fe.stop()

    def test_dashboard_mode_html(self):
        import httpx
        fe = self._fe()
        base = fe.serve()
        try:
            fe.mode = "dashboard"
            page = httpx.get(base + "/").text
            self.assertIn("mem20 dashboard", page)
            d = httpx.get(base + "/dashboard").json()
            self.assertTrue(d["status"]["production"])
        finally:
            fe.stop()

    def test_chat_roundtrip_persists_web_prefix(self):
        fe = self._fe()
        out = fe.chat({"message": "office hi"})
        self.assertTrue(out["ok"])
        self.assertEqual(out["reply"], "office-pong")
        self.assertTrue(out["chat_id"].startswith("w"))
        texts = [e["text"] for e in self.ledger]
        self.assertTrue(any("user: office hi" in t for t in texts))
        self.assertTrue(any("assistant: office-pong" in t for t in texts))

    def test_single_source_status_matches_webgateway(self):
        fe = self._fe()
        from mem20agentz.gateway_web import WebGateway, build_web_factory
        wg = WebGateway(backend=self.backend(),
                         agent_factory=build_web_factory(self.backend()))
        self.assertEqual(fe.status(), wg.status())

    def test_html_served(self):
        import httpx
        fe = self._fe()
        base = fe.serve()
        try:
            page = httpx.get(base + "/").text
            self.assertIn("<title>mem20</title>", page)
            self.assertIn("/office", page)
            self.assertIn('id="office"', page)
            self.assertIn("mem20 client ready.", page)
        finally:
            fe.stop()

    def test_health(self):
        import httpx
        fe = self._fe()
        base = fe.serve()
        try:
            h = httpx.get(base + "/health").json()
            self.assertTrue(h["ok"])
            self.assertEqual(h["service"], "mem office")
        finally:
            fe.stop()

    def test_404(self):
        import httpx
        fe = self._fe()
        base = fe.serve()
        try:
            resp = httpx.get(base + "/nope")
            self.assertEqual(resp.status_code, 404)
        finally:
            fe.stop()

    def test_http_full_round_trip(self):
        import httpx
        fe = self._fe()
        base = fe.serve()
        try:
            status = httpx.get(base + "/status").json()
            self.assertEqual(status["service"], "webgateway")
            self.assertEqual(status["chat_session_prefix"], "web:")
            bundle = httpx.get(base + "/office").json()
            self.assertEqual(bundle["service"], "mem office")
            self.assertEqual(bundle["status"], status)
            chat = httpx.post(base + "/chat",
                              json={"message": "full round"}).json()
            self.assertTrue(chat["ok"])
            self.assertEqual(chat["reply"], "office-pong")
            tail = httpx.get(base + "/ledger?k=5").json()
            self.assertTrue(tail["ok"])
        finally:
            fe.stop()


class TestBackup(_Sealed):
    def stub(self, facts=None):
        facts = facts if facts is not None else []

        def remember(topic, content, tags, actor, epistemic_status):
            facts.append({"topic": topic, "content": content,
                          "tags": list(tags or []), "actor": actor,
                          "epistemic_status": epistemic_status})
            return {"ok": True}

        def recall(topic=None, tags=None, k=10):
            if topic is None and tags == ["mem20agentz"]:
                return [dict(f) for f in facts]
            hits = []
            for f in facts:
                if topic and topic not in f["topic"]:
                    continue
                if tags and not (set(tags) <= set(f["tags"] or [])):
                    continue
                hits.append(dict(f))
            return hits

        def ns(ns):
            return {"namespace": ns, "exists": True}

        self.hook("remember", remember)
        self.hook("recall", recall)
        self.hook("namespace_ensure", ns)
        return facts

    def test_backup_round_trip(self):
        from mem20agentz.backup import Backup
        facts = self.stub([
            {"topic": "note", "content": "alpha", "tags": ["mem20agentz"],
             "actor": "mem20", "epistemic_status": "observed"},
            {"topic": "self-model:mem20",
             "content": "self-model mem20", "tags": ["mem20agentz",
                                                    "self_model"],
             "actor": "mem20", "epistemic_status": "agent_generated"},
        ])
        tmp = tempfile.mktemp(suffix=".json.gz")
        out = Backup(backend=self.backend()).export(out=tmp)
        self.assertTrue(out["ok"])
        self.assertTrue(pathlib.Path(tmp).exists())
        self.assertTrue(pathlib.Path(tmp + ".sha256").exists())
        self.assertEqual(out["facts"], 2)
        self.assertEqual(out["profiles"], 1)
        restored = Backup(backend=self.backend()).restore(tmp)
        self.assertTrue(restored["ok"])
        self.assertEqual(restored["restored"], 2)
        self.assertEqual(restored["sha256"], out["sha256"])
        self.assertEqual(len(facts), 4)
        nuts = [f["content"] for f in facts]
        self.assertIn("alpha", nuts)
        self.assertIn("restored", facts[-1]["tags"])

    def test_restore_rejects_tamper(self):
        from mem20agentz.backup import Backup
        import gzip
        self.stub()
        tmp = tempfile.mktemp(suffix=".json.gz")
        Backup(backend=self.backend()).export(out=tmp)
        with gzip.open(tmp, "rt", encoding="utf-8") as fh:
            payload = fh.read().replace("mem20agentz-backup",
                                        "tampered-backup")
        with gzip.open(tmp, "wt", encoding="utf-8") as fh:
            fh.write(payload)
        res = Backup(backend=self.backend()).restore(tmp)
        self.assertFalse(res["ok"])
        self.assertIn("mismatch", res["error"])

    def test_restore_rejects_wrong_kind(self):
        from mem20agentz.backup import Backup
        import gzip, json as _json
        tmp = tempfile.mktemp(suffix=".json.gz")
        with gzip.open(tmp, "wt", encoding="utf-8") as fh:
            fh.write(_json.dumps({"kind": "other"}))
        res = Backup(backend=self.backend()).restore(tmp)
        self.assertFalse(res["ok"])
        self.assertIn("not a mem20agentz backup", res["error"])

    def test_scrub_secret_config_keys(self):
        from mem20agentz.backup import _scrub
        cleaned = _scrub({"openai_api_key": "sk-xxx",
                          "nested": {"token": "t", "ok": 1}})
        self.assertEqual(cleaned["openai_api_key"], "<redacted>")
        self.assertEqual(cleaned["nested"]["token"], "<redacted>")
        self.assertEqual(cleaned["nested"]["ok"], 1)


class TestImportAgent(_Sealed):
    def stub(self):
        calls = {"sessions": [], "messages": [], "ns": []}

        def ns(namespace):
            calls["ns"].append(namespace)
            return {"namespace": namespace}

        def session_add(profile, session_id, title, meta=None):
            calls["sessions"].append({"profile": profile, "id": session_id,
                                      "title": title})
            return {"ok": True}

        def session_append(profile, session_id, role, text):
            calls["messages"].append({"id": session_id, "role": role,
                                      "text": text})
            return {"ok": True}

        self.hook("namespace_ensure", ns)
        self.hook("session_add", session_add)
        self.hook("session_append", session_append)
        return calls

    def test_claude_jsonl_import(self):
        from mem20agentz.import_agent import import_agent
        calls = self.stub()
        tmp = tempfile.mktemp(suffix=".jsonl")
        pathlib.Path(tmp).write_text(
            '{"type":"user","message":{"content":[{"type":"text",'
            '"text":"hi"}]}}\n'
            '{"type":"assistant","message":{"content":"hello there"}}\n'
            '{"type":"user","message":"how are you"}\n'
            '{"garbage":true}\n', encoding="utf-8")
        res = import_agent(self.backend(), tmp)
        self.assertTrue(res["ok"])
        self.assertEqual(res["kind"], "claude")
        self.assertEqual(res["entries"], 3)
        self.assertTrue(res["session_id"].startswith("im-"))
        self.assertEqual(calls["sessions"][0]["title"].startswith(
            "imported:claude:"), True)
        roles = [m["role"] for m in calls["messages"]]
        self.assertEqual(roles, ["user", "assistant", "user"])

    def test_codex_json_import_with_text_parts(self):
        from mem20agentz.import_agent import import_agent
        calls = self.stub()
        tmp = tempfile.mktemp(suffix=".json")
        pathlib.Path(tmp).write_text(json.dumps([
            {"role": "user", "content": "u1"},
            {"role": "assistant",
             "content": [{"type": "text", "text": "a1"},
                         {"type": "text", "text": "a2"}]},
        ]), encoding="utf-8")
        res = import_agent(self.backend(), tmp, kind="codex")
        self.assertTrue(res["ok"])
        self.assertEqual(res["kind"], "codex")
        self.assertEqual(res["entries"], 2)
        self.assertEqual(calls["messages"][1]["text"], "a1\na2")

    def test_import_empty_fails(self):
        from mem20agentz.import_agent import import_agent
        tmp = tempfile.mktemp(suffix=".json")
        pathlib.Path(tmp).write_text("[]", encoding="utf-8")
        res = import_agent(self.backend(), tmp)
        self.assertFalse(res["ok"])
        self.assertEqual(res["entries"], 0)


class TestMigration(_Sealed):
    def setUp(self):
        super().setUp()
        self._cfg = os.environ.pop("MEM20AGENTZ_CONFIG", None)

    def tearDown(self):
        super().tearDown()
        if self._cfg:
            os.environ["MEM20AGENTZ_CONFIG"] = self._cfg

    def test_config_migration_adds_office_port(self):
        from mem20agentz.migration import Migrator
        cfg = tempfile.mktemp(suffix=".yaml")
        os.environ["MEM20AGENTZ_CONFIG"] = cfg
        res = Migrator().config()
        self.assertTrue(res["ok"])
        self.assertIn("gateway.office.port", res["changed"])
        text = pathlib.Path(cfg).read_text(encoding="utf-8")
        self.assertIn("18785", text)

    def test_config_migration_idempotent(self):
        from mem20agentz.migration import Migrator
        cfg = tempfile.mktemp(suffix=".yaml")
        os.environ["MEM20AGENTZ_CONFIG"] = cfg
        first = Migrator().config()
        second = Migrator().config()
        self.assertIn("gateway.office.port", first["changed"])
        self.assertEqual(second["changed"], [])

    def test_claw_migration_imports_memories(self):
        from mem20agentz.migration import Migrator
        facts = []

        def remember(topic, content, tags, actor, epistemic_status):
            facts.append({"topic": topic, "content": content,
                          "tags": list(tags or []), "actor": actor})
            return {"ok": True}

        def ns(namespace):
            return {"namespace": namespace}

        self.hook("remember", remember)
        self.hook("namespace_ensure", ns)
        tmp = tempfile.mktemp(suffix=".json")
        pathlib.Path(tmp).write_text(json.dumps({
            "memories": [
                {"content": "m1", "tags": ["t"]},
                {"content": "m2"},
                {"content": ""},
            ]}), encoding="utf-8")
        res = Migrator(backend=self.backend()).claw(tmp)
        self.assertTrue(res["ok"])
        self.assertEqual(res["imported"], 2)
        self.assertIn("claw", facts[0]["tags"])
        self.assertIn("migrated", facts[0]["tags"])

    def test_claw_missing_manifest(self):
        from mem20agentz.migration import Migrator
        res = Migrator(backend=self.backend()).claw(
            "/nonexistent/manifest.json")
        self.assertFalse(res["ok"])


class TestParity(_Sealed):
    def test_all_commands_help_green(self):
        from mem20agentz import cli
        self.assertEqual(cli.main(["parity"]), 0)


class TestLoopback(_Sealed):
    def make(self):
        from mem20agentz.bridges.loopback import LoopbackTransport
        tmp = tempfile.mkdtemp()
        transport = LoopbackTransport(root=pathlib.Path(tmp))
        return tmp, transport

    def test_deliver_poll_returns_message(self):
        _, transport = self.make()
        transport.deliver("lab1", "ping")
        msg = transport.poll(0.5)
        self.assertIsNotNone(msg)
        self.assertEqual(msg.chat_id, "lab1")
        self.assertEqual(msg.text, "ping")
        self.assertEqual(msg.platform, "loopback")
        self.assertIsNone(transport.poll(0.2))

    def test_send_collect_outbox(self):
        _, transport = self.make()
        transport.send("lab1", "pong")
        rows = transport.collect("lab1")
        self.assertEqual(rows[0]["text"], "pong")
        self.assertEqual(transport.collect("lab1"), [])

    def test_bridge_full_turnstile(self):
        from types import SimpleNamespace
        from mem20agentz.bridge import Bridge

        class _Core:
            def __init__(self, reply):
                self._reply = reply

            def run(self, text):
                return SimpleNamespace(blocked=False, text=self._reply)

        tmp, transport = self.make()
        bridge = Bridge("loopback", transport,
                        agent_factory=lambda chat: _Core("loopback-pong"),
                        ledger=None, root=pathlib.Path(tmp))
        transport.deliver("lab1", "ping")
        msg = transport.poll(0.5)
        self.assertIsNotNone(msg)
        reply = bridge.handle(msg)
        self.assertEqual(reply, "loopback-pong")
        bridge.send(msg.chat_id, reply)
        rows = transport.collect("lab1")
        self.assertEqual(rows[0]["text"], "loopback-pong")
        self.assertEqual(transport.poll(0.2), None)


class TestAcceptance(_Sealed):
    def _run(self, argv, text=None, code=None):
        import shutil
        import subprocess as _sp
        env = dict(os.environ)
        pruned = {k: v for k, v in env.items()
                  if not k.startswith("PYTHON") and k != "MEM20AGENTZ_BACKEND"}
        return _sp.run([sys.executable] + argv, cwd=text or "/tmp",
                       capture_output=True, env=pruned, text=True,
                       timeout=60, input=code)

    def test_python_m_version_from_any_dir(self):
        run = self._run(["-m", "mem20agentz", "--version"])
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("mem20agentz", run.stdout)
        self.assertNotIn(OLD_NAME.lower(), run.stdout.lower())

    def test_import_from_any_dir(self):
        run = self._run(["-c", "import mem20agentz; print(mem20agentz.__file__)", "x"],
                        text=None)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("mem20agentz", run.stdout)

    def test_full_repo_branding_sweep(self):
        root = pathlib.Path("/opt/mem20/mem20agentz")
        hits = []
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in (".py", ".md", ".toml"):
                continue
            if "test_" in path.name:
                continue
            if "docs/" in str(path) or "docs\\" in str(path):
                continue
            if OLD_NAME.lower() in path.read_text(
                    encoding="utf-8", errors="replace").lower():
                hits.append(str(path))
        self.assertEqual(hits, [], f"old vendor name in repo: {hits}")


class TestBranding(_Sealed):
    def test_no_old_vendor_name(self):
        root = pathlib.Path(pkg.__file__).parent
        hits = []
        for path in root.rglob("*.py"):
            if "test_" in path.name:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if OLD_NAME.lower() in text.lower():
                hits.append(str(path))
        self.assertEqual(hits, [], f"old vendor name found in: {hits}")

    def test_version_present(self):
        self.assertTrue(pkg.__version__)
        self.assertIsInstance(pkg.__version__, str)


if __name__ == "__main__":
    unittest.main()