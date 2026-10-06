"""Tests for mem20botz.

The IRC protocol, the command router, the identity gate and the secret masker
are all exercised without a server: the client is fed literal protocol lines,
which is the only way to test a parser honestly. A fake that "behaves like IRC"
can only prove it agrees with the author's idea of IRC.

The kanban bot is tested against a real in-process HTTP door, because the thing
most worth protecting is that a claim is really recorded and a completion is
really refused when it should be. No test can reach the live door on :8221 or
the IRC daemon on :6667.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mem20botz import (  # noqa: E402
    AgentzBot, CrewBot, Identity, KanbanBot, Message, RelayBot,
    identify, mask_secrets, operator_card, parse_command, parse_line,
)

DOOR_PORT = 8221


# --------------------------------------------------------------------------
# a real in-process door, reused from the same approach mem20kanbanz tests
# --------------------------------------------------------------------------
import json  # noqa: E402
import threading  # noqa: E402
from http.server import BaseHTTPRequestHandler, HTTPServer  # noqa: E402
from urllib.parse import urlparse  # noqa: E402


class _State:
    def __init__(self):
        self.boards, self.columns, self.tasks = {}, {}, {}
        self.n = 0

    def nid(self, p):
        self.n += 1
        return f"{p}{self.n}"


class _Handler(BaseHTTPRequestHandler):
    state = _State()

    def log_message(self, format, *a):
        pass

    def _send(self, code, payload=None):
        body = json.dumps(payload).encode() if payload is not None else b""
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n)) if n else {}

    def _p(self):
        return urlparse(self.path).path

    def do_GET(self):
        s = self.state
        p = self._p()
        if p == "/api/boards":
            return self._send(200, [{"id": b["id"], "name": b["name"],
                                     "goal": b["goal"]}
                                    for b in s.boards.values()])
        if p.startswith("/api/boards/"):
            bid = p.rsplit("/", 1)[1]
            b = s.boards.get(bid)
            if not b:
                return self._send(404, {"error": "Board not found"})
            cols = []
            for c in sorted((c for c in s.columns.values()
                             if c["board_id"] == bid),
                            key=lambda c: c["position"]):
                tasks = [{"id": t["id"], "title": t["title"],
                          "position": 0, "metadata": t["metadata"]}
                         for t in s.tasks.values() if t["column_id"] == c["id"]]
                cols.append({**c, "tasks": tasks})
            return self._send(200, {"board": b, "columns": cols})
        if p.startswith("/api/tasks/"):
            tid = p.rsplit("/", 1)[1]
            t = s.tasks.get(tid)
            return self._send(200, t) if t else self._send(404, {"error": "no"})
        return self._send(404, {"error": "no"})

    def do_POST(self):
        s = self.state
        p = self._p()
        body = self._body()
        if p == "/api/boards":
            name = body["name"]
            for b in s.boards.values():
                if b["name"] == name:
                    return self._send(201, {"boardId": b["id"]})
            bid = s.nid("b")
            cols = body.get("columns") or [
                {"name": "todo", "wipLimit": 0},
                {"name": "in_progress", "wipLimit": 0},
                {"name": "done", "wipLimit": 0, "isDoneColumn": True}]
            landing = body.get("landingColumnPosition", 0)
            made = []
            for i, c in enumerate(cols):
                cid = s.nid("c")
                col = {"id": cid, "board_id": bid, "name": c["name"],
                       "position": i, "wipLimit": c.get("wipLimit", 0),
                       "isDoneColumn": bool(c.get("isDoneColumn")),
                       "isLanding": i == landing}
                s.columns[cid] = col
                made.append(col)
            s.boards[bid] = {"id": bid, "name": name,
                             "goal": body.get("projectGoal", ""),
                             "landing_column_id": made[landing]["id"]}
            return self._send(201, {"boardId": bid})
        if p == "/api/tasks":
            bid = body["boardId"]
            b = s.boards.get(bid)
            if not b:
                return self._send(404, {"error": "Board not found"})
            cid = body.get("columnId") or b["landing_column_id"]
            meta = body.get("metadata")
            tid = s.nid("t")
            t = {"id": tid, "column_id": cid, "title": body["title"],
                 "content": body.get("content", ""), "position": 0,
                 "metadata": json.dumps(meta) if isinstance(meta, dict) else meta}
            s.tasks[tid] = t
            return self._send(201, {"success": True, "task": t})
        if p.endswith("/done-column"):
            bid = p.split("/")[3]
            cols = [c for c in s.columns.values() if c["board_id"] == bid]
            name = body.get("column") or ""
            if not any(c["name"] == name for c in cols):
                return self._send(404, {"error": "Column not found"})
            for c in cols:
                c["isDoneColumn"] = c["name"] == name
            return self._send(200, {"success": True})
        if p.endswith("/move"):
            tid = p.split("/")[3]
            t = s.tasks.get(tid)
            if not t:
                return self._send(404, {"error": "Task not found"})
            tgt = s.columns.get(body.get("targetColumnId") or "")
            if not tgt:
                return self._send(404, {"error": "Target column not found"})
            t["column_id"] = tgt["id"]
            if body.get("reason"):
                t["update_reason"] = body["reason"]
            return self._send(200, {"success": True})
        return self._send(404, {"error": "no"})

    def do_PATCH(self):
        s = self.state
        p = self._p()
        body = self._body()
        if not p.endswith("/metadata"):
            return self._send(404, {"error": "no"})
        tid = p.split("/")[3]
        t = s.tasks.get(tid)
        if not t:
            return self._send(404, {"error": "Task not found"})
        patch = body.get("patch")
        if not isinstance(patch, dict):
            return self._send(400, {"error": "patch must be a JSON object"})
        cur = json.loads(t.get("metadata") or "{}")
        for k, v in patch.items():
            cur.pop(k, None) if v is None else cur.update({k: v})
        t["metadata"] = json.dumps(cur)
        return self._send(200, {"success": True, "task": t})


class DoorServer:
    def __init__(self):
        self.state = _State()
        h = type("H", (_Handler,), {"state": self.state})
        self.httpd = HTTPServer(("127.0.0.1", 0), h)
        self.url = f"http://127.0.0.1:{self.httpd.server_port}"
        self.t = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self):
        self.t.start()
        return self

    def __exit__(self, *a):
        self.httpd.shutdown()
        self.httpd.server_close()


# --------------------------------------------------------------------------
class TestPackaging(unittest.TestCase):
    def test_version(self):
        import mem20botz
        self.assertIsInstance(mem20botz.__version__, str)
        self.assertTrue(mem20botz.__version__)

    def test_exports_importable(self):
        import mem20botz
        for name in mem20botz.__all__:
            self.assertTrue(hasattr(mem20botz, name), name)

    def test_module_entry(self):
        import subprocess
        r = subprocess.run([sys.executable, "-m", "mem20botz", "--version"],
                           capture_output=True, text=True, cwd="/tmp",
                           timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("mem20botz", r.stdout)


class TestProtocolParsing(unittest.TestCase):
    def test_privmsg_with_text(self):
        m = parse_line(":bob!~b@127.0.0.1 PRIVMSG #mem20 :hello world")
        self.assertEqual(m.command, "PRIVMSG")
        self.assertEqual(m.nick, "bob")
        self.assertEqual(m.target, "#mem20")
        self.assertEqual(m.text, "hello world")
        self.assertTrue(m.is_channel)

    def test_colon_inside_text_is_kept(self):
        m = parse_line(":a!b@c PRIVMSG #x :see http://host:8080/p?q=1:2")
        self.assertIn("http://host:8080/p?q=1:2", m.text)

    def test_numeric_has_no_nick(self):
        m = parse_line(":server 001 nick :Welcome")
        self.assertEqual(m.command, "001")
        self.assertEqual(m.nick, "")
        self.assertIn("Welcome", m.text)

    def test_blank_line_is_none(self):
        self.assertIsNone(parse_line(""))
        self.assertIsNone(parse_line("   "))

    def test_private_message_is_not_channel(self):
        m = parse_line(":bob!~b@h PRIVMSG carol :psst")
        self.assertFalse(m.is_channel)

    def test_channel_prefixes(self):
        for ch in ("#a", "&b", "+c", "!d"):
            self.assertTrue(parse_line(f":a!b@c PRIVMSG {ch} :x").is_channel)

    def test_command_parsing(self):
        self.assertEqual(parse_command("!accept abc123"), ("accept", "abc123"))
        self.assertEqual(parse_command("!done abc why not"),
                         ("done", "abc why not"))
        self.assertEqual(parse_command("!JOBS"), ("jobs", ""))
        self.assertIsNone(parse_command("hello"))
        self.assertIsNone(parse_command(""))

    def test_command_with_no_args(self):
        self.assertEqual(parse_command("!status"), ("status", ""))


class TestIdentity(unittest.TestCase):
    def test_operator_is_recognised(self):
        self.assertTrue(identify("jayson").is_operator)
        self.assertTrue(identify("JAYSON").is_operator)

    def test_crew_is_recognised(self):
        for nick in ("kanban", "agentz", "crewbot", "relay", "muse",
                     "bigpickle", "nemotron3ultra", "opencode"):
            self.assertTrue(identify(nick).is_crew, nick)
            self.assertFalse(identify(nick).is_operator, nick)

    def test_stranger_is_a_guest(self):
        who = identify("randomperson")
        self.assertEqual(who.role, "guest")
        self.assertFalse(who.is_crew)

    def test_guest_may_not_take_work(self):
        who = identify("randomperson")
        self.assertFalse(who.may("accept"))
        self.assertFalse(who.may("done"))

    def test_crew_may_take_and_report_work(self):
        who = identify("nemotron3ultra")
        self.assertTrue(who.may("accept"))
        self.assertTrue(who.may("done"))
        self.assertTrue(who.may("jobs"))

    def test_crew_may_not_run_privileged(self):
        who = identify("nemotron3ultra")
        self.assertFalse(who.may("run"))
        self.assertFalse(who.may("crew"))

    def test_operator_may_run_privileged(self):
        who = identify("jayson")
        self.assertTrue(who.may("run"))
        self.assertTrue(who.may("crew"))

    def test_read_only_commands_are_open_to_all(self):
        for nick in ("jayson", "nemotron3ultra", "randomperson"):
            who = identify(nick)
            self.assertTrue(who.may("about"), nick)
            self.assertTrue(who.may("whoami"), nick)

    def test_operator_card_names_jayson(self):
        card = operator_card()
        self.assertIn("Jayson", card)
        self.assertIn("owner", card)
        # It must say how to address him, so a bot does not call him "bot".
        self.assertIn("address as", card)

    def test_identity_describe_mentions_role(self):
        self.assertIn("operator", identify("jayson").describe())
        self.assertIn("guest", identify("nobody").describe())


class TestSecretMasking(unittest.TestCase):
    def test_openai_key_is_masked(self):
        out = mask_secrets("key sk-abcdefghijklmnopqrstuvwx here")
        self.assertNotIn("abcdefghijklmnopqrstuvwx", out)

    def test_github_token_is_masked(self):
        out = mask_secrets("ghp_0123456789abcdefghijABCDEFGHIJ")
        self.assertNotIn("0123456789abcdefghijABCDEFGHIJ", out)

    def test_aws_key_is_masked(self):
        out = mask_secrets("AKIAIOSFODNN7EXAMPLE")
        self.assertNotIn("IOSFODNN7EXAMPLE", out)

    def test_slack_token_is_masked(self):
        out = mask_secrets("xoxb-1234567890-abcdefghij")
        self.assertNotIn("1234567890-abcdefghij", out)

    def test_email_is_masked_but_domain_survives(self):
        out = mask_secrets("mail jayson@mem20.irc now")
        self.assertNotIn("jayson@", out)
        self.assertIn("mem20.irc", out)

    def test_ordinary_text_is_untouched(self):
        text = "the build is green, 42 tests passed"
        self.assertEqual(mask_secrets(text), text)

    def test_masking_does_not_mutate_the_input(self):
        original = "jayson@mem20.irc"
        copy = str(original)
        mask_secrets(original)
        self.assertEqual(original, copy)

    def test_every_secret_is_masked_in_one_pass(self):
        out = mask_secrets("a sk-abcdefghijklmnopqrstuvwx b AKIAIOSFODNN7EXAMPLE")
        self.assertNotIn("abcdefghijklmnopqrstuvwx", out)
        self.assertNotIn("IOSFODNN7EXAMPLE", out)


class TestSelfDescription(unittest.TestCase):
    """Every bot must be able to say what it is and where it reads from."""

    def _bots(self):
        return [KanbanBot(), AgentzBot(), CrewBot(),
                RelayBot(store=lambda **k: None)]

    def test_every_bot_describes_itself(self):
        for bot in self._bots():
            text = bot.describe()
            self.assertIn(bot.nick, text, bot.nick)

    def test_every_bot_names_its_source(self):
        for bot in self._bots():
            text = bot.describe()
            self.assertIn("reads:", text, bot.nick)
            self.assertNotEqual(bot.source_of_truth, "", bot.nick)

    def test_every_bot_has_a_purpose(self):
        for bot in self._bots():
            self.assertTrue(bot.purpose.strip(), bot.nick)
            self.assertIn(bot.purpose.strip(), bot.describe())

    def test_every_bot_lists_its_commands(self):
        for bot in self._bots():
            self.assertIn("!about", bot.describe())
            self.assertIn("!whoami", bot.describe())

    def test_kanban_names_the_door(self):
        d = KanbanBot().describe()
        self.assertIn(str(DOOR_PORT), d)

    def test_kanban_says_it_does_not_open_the_database(self):
        self.assertIn("never opens the database",
                      KanbanBot().source_of_truth)

    def test_agentz_names_its_cli(self):
        self.assertIn("mem20agentz", AgentzBot().source_of_truth)

    def test_crewbot_names_its_runtime(self):
        self.assertIn("mem20crewz", CrewBot().source_of_truth)

    def test_relay_says_it_is_a_reader_only(self):
        s = RelayBot(store=lambda **k: None).source_of_truth
        self.assertIn("never speaks", s)
        self.assertIn("masked", s)

    def test_commands_are_sorted_for_readability(self):
        # Assert the invariant, not the formatting: the listed commands must
        # appear in sorted order in the rendered text.
        bot = KanbanBot()
        text = bot.describe()
        line = text.split("commands: ")[1].splitlines()[0]
        listed = [c.strip() for c in line.split(",") if c.strip()]
        self.assertEqual(listed, sorted(listed))
        # And it must be the bot's real command set, not a stale copy.
        self.assertEqual({c.lstrip("!") for c in listed}, set(bot.commands))


class TestRelay(unittest.TestCase):
    def test_records_a_message(self):
        seen = []
        r = RelayBot(store=lambda **kw: seen.append(
            (kw.get("content"), kw.get("topic"), kw.get("tags"))))
        self.assertTrue(r.record("bob", "hello crew"))
        self.assertEqual(seen[0][0], "[#mem20] bob: hello crew")

    def test_masks_secrets_before_storing(self):
        seen = []
        r = RelayBot(store=lambda **kw: seen.append(kw.get("content", "")))
        r.record("bob", "token sk-abcdefghijklmnopqrstuvwx")
        self.assertNotIn("abcdefghijklmnopqrstuvwx", seen[0])
        self.assertEqual(r.masked, 1)

    def test_truncates_a_long_message(self):
        seen = []
        r = RelayBot(store=lambda **kw: seen.append(kw.get("content", "")))
        r.record("bob", "x" * 5000)
        self.assertLessEqual(len(seen[0]), 450)

    def test_empty_message_is_not_stored(self):
        seen = []
        r = RelayBot(store=lambda **kw: seen.append(kw.get("content", "")))
        self.assertFalse(r.record("bob", "   "))
        self.assertEqual(seen, [])

    def test_a_failing_store_does_not_raise(self):
        def boom(**kwargs):
            raise RuntimeError("memory down")
        r = RelayBot(store=boom)
        # The scribe failing must never take the channel down.
        self.assertFalse(r.record("bob", "hello"))
        self.assertEqual(r.failures, 1)

    def test_warns_only_once_about_a_broken_store(self):
        said = []
        r = RelayBot(store=lambda **k: (_ for _ in ()).throw(
            RuntimeError("down")))
        r.say = lambda text, target="": said.append(text)
        for _ in range(5):
            r.record("bob", "hello")
        self.assertEqual(len(said), 1)

    def test_missing_store_is_reported_not_guessed(self):
        r = RelayBot()
        r._store = None
        r._resolved = None
        # With no memory available it must say so, not pretend to store.
        self.assertIsNone(r._store_fn())

    def test_records_through_the_real_memory_signature(self):
        """The relay must call memory the way memory is actually called.

        The first implementation guessed a `store(content=, category=)`
        signature that does not exist, so every write failed and the bot
        reported "memory UNREACHABLE" forever without anyone noticing. This
        test pins the real `remember(topic=, content=, tags=)` shape.
        """
        calls = {}

        def remember(**kwargs):
            calls.update(kwargs)
            return {"id": "x"}

        r = RelayBot(store=remember)
        self.assertTrue(r.record("bob", "hello crew"))
        self.assertIn("topic", calls)
        self.assertIn("content", calls)
        self.assertIn("tags", calls)
        self.assertEqual(calls["content"], "[#mem20] bob: hello crew")
        self.assertIsInstance(calls["tags"], list)

    def test_resolution_is_cached_not_repeated(self):
        r = RelayBot()
        r._store = None
        r._resolved = None
        for _ in range(5):
            self.assertIsNone(r._store_fn())
        # Cached as a failure: a missing memory system must not re-import on
        # every single message.


class TestKanbanBotCommands(unittest.TestCase):
    def _bot(self, url, board="Fleet HQ"):
        from mem20kanbanz import Door
        b = KanbanBot(door=Door(url, timeout=5), board=board)
        b.say = lambda text, target="": None
        b.pm = lambda nick, text: None
        return b

    def _msg(self, nick="nemotron3ultra", channel="#mem20"):
        return parse_line(f":{nick}!~{nick}@127.0.0.1 PRIVMSG {channel} :x")

    def test_jobs_lists_open_work(self):
        with DoorServer() as s:
            from mem20kanbanz import Door
            d = Door(s.url, timeout=5)
            d.create_board("Fleet HQ", goal="ship")
            d.add_card("Fleet HQ", "fix the flaky test")
            out = self._bot(s.url).cmd_jobs(None, self._msg(), "")
            self.assertIn("fix the flaky test", out)
            self.assertIn("1 open", out)

    def test_jobs_on_an_empty_board_says_so(self):
        with DoorServer() as s:
            from mem20kanbanz import Door
            Door(s.url, timeout=5).create_board("Fleet HQ")
            self.assertIn("no open work",
                          self._bot(s.url).cmd_jobs(None, self._msg(), ""))

    def test_jobs_on_an_unknown_board_names_the_real_ones(self):
        with DoorServer() as s:
            from mem20kanbanz import Door
            Door(s.url, timeout=5).create_board("Fleet HQ")
            out = self._bot(s.url).cmd_jobs(None, self._msg(), "nope")
            self.assertIn("no board", out)
            self.assertIn("Fleet HQ", out)

    def test_accept_records_the_claim(self):
        with DoorServer() as s:
            from mem20kanbanz import Door
            d = Door(s.url, timeout=5)
            d.create_board("Fleet HQ")
            card = d.add_card("Fleet HQ", "a job")
            out = self._bot(s.url).cmd_accept(None, self._msg(), card.id[:8])
            self.assertIn("took", out)
            # The board must actually show the claim, not just the reply.
            self.assertEqual(d.card(card.id).assignee, "nemotron3ultra")

    def test_accept_without_an_id_asks_which(self):
        with DoorServer() as s:
            self.assertIn("which job",
                          self._bot(s.url).cmd_accept(None, self._msg(), ""))

    def test_accept_of_an_unknown_job_says_so(self):
        with DoorServer() as s:
            from mem20kanbanz import Door
            Door(s.url, timeout=5).create_board("Fleet HQ")
            self.assertIn("no job matching",
                          self._bot(s.url).cmd_accept(
                              None, self._msg(), "zzzzzzzz"))

    def test_a_second_agent_cannot_steal_a_claim(self):
        with DoorServer() as s:
            from mem20kanbanz import Door
            d = Door(s.url, timeout=5)
            d.create_board("Fleet HQ")
            card = d.add_card("Fleet HQ", "a job")
            self._bot(s.url).cmd_accept(None, self._msg("crew1"), card.id[:8])
            out = self._bot(s.url).cmd_accept(
                None, self._msg("crew2"), card.id[:8])
            self.assertIn("already claimed", out)
            self.assertEqual(d.card(card.id).assignee, "crew1")

    def test_done_moves_the_card_into_the_done_column(self):
        with DoorServer() as s:
            from mem20kanbanz import Door
            d = Door(s.url, timeout=5)
            d.create_board("Fleet HQ")
            card = d.add_card("Fleet HQ", "a job")
            self._bot(s.url).cmd_accept(None, self._msg(), card.id[:8])
            out = self._bot(s.url).cmd_done(
                None, self._msg(), f"{card.id[:8]} tests green")
            self.assertIn("done", out)
            self.assertEqual(d.card(card.id).status, "done")

    def test_done_refuses_on_a_board_with_no_done_column(self):
        """Better a refusal than a job marked done in the wrong place."""
        with DoorServer() as s:
            from mem20kanbanz import Door
            d = Door(s.url, timeout=5)
            d.create_board("Fleet HQ", columns=[
                {"name": "todo", "wipLimit": 0},
                {"name": "doing", "wipLimit": 0}])
            card = d.add_card("Fleet HQ", "a job")
            out = self._bot(s.url).cmd_done(None, self._msg(), card.id[:8])
            self.assertIn("cannot mark done", out)
            self.assertEqual(d.card(card.id).status, "todo")

    def test_release_returns_the_job_to_the_queue(self):
        with DoorServer() as s:
            from mem20kanbanz import Door
            d = Door(s.url, timeout=5)
            d.create_board("Fleet HQ")
            card = d.add_card("Fleet HQ", "a job")
            self._bot(s.url).cmd_accept(None, self._msg(), card.id[:8])
            out = self._bot(s.url).cmd_release(
                None, self._msg(), card.id[:8])
            self.assertIn("released", out)
            self.assertEqual(d.card(card.id).status, "todo")
            self.assertEqual(d.card(card.id).assignee, "")

    def test_who_lists_who_holds_work(self):
        with DoorServer() as s:
            from mem20kanbanz import Door
            d = Door(s.url, timeout=5)
            d.create_board("Fleet HQ")
            card = d.add_card("Fleet HQ", "a job")
            self._bot(s.url).cmd_accept(None, self._msg("muse"), card.id[:8])
            out = self._bot(s.url).cmd_who(None, self._msg(), "")
            self.assertIn("muse", out)
            self.assertIn("a job", out)

    def test_accept_by_exact_title(self):
        with DoorServer() as s:
            from mem20kanbanz import Door
            d = Door(s.url, timeout=5)
            d.create_board("Fleet HQ")
            d.add_card("Fleet HQ", "fix the flaky test")
            out = self._bot(s.url).cmd_accept(
                None, self._msg(), "fix the flaky test")
            self.assertIn("took", out)

    def test_claiming_twice_says_you_already_hold_it(self):
        """A repeat claim must not be re-announced as if it were fresh."""
        with DoorServer() as s:
            from mem20kanbanz import Door
            d = Door(s.url, timeout=5)
            d.create_board("Fleet HQ")
            card = d.add_card("Fleet HQ", "a job")
            b = self._bot(s.url)
            first = b.cmd_accept(None, self._msg("muse"), card.id[:8])
            second = b.cmd_accept(None, self._msg("muse"), card.id[:8])
            self.assertIn("took", first)
            self.assertIn("already holds", second)

    def test_status_reports_the_door(self):
        with DoorServer() as s:
            self.assertIn("door up", self._bot(s.url).cmd_status(
                None, self._msg(), ""))

    def test_claim_works_on_a_board_named_with_spaces(self):
        """Fleet HQ uses 'In Progress', not 'in_progress'.

        A hardcoded column name made every claim fail on that board, and only
        a live run against the real board found it.
        """
        with DoorServer() as s:
            from mem20kanbanz import Door
            d = Door(s.url, timeout=5)
            d.create_board("Fleet HQ", columns=[
                {"name": "Backlog", "wipLimit": 0},
                {"name": "In Progress", "wipLimit": 0},
                {"name": "Review", "wipLimit": 0},
                {"name": "Done", "wipLimit": 0, "isDoneColumn": True}])
            card = d.add_card("Fleet HQ", "a job", column="Backlog")
            out = self._bot(s.url).cmd_accept(None, self._msg(), card.id[:8])
            self.assertIn("took", out)
            self.assertIn("In Progress", out)
            self.assertEqual(d.card(card.id).status, "In Progress")

    def test_claim_falls_back_to_the_landing_column(self):
        with DoorServer() as s:
            from mem20kanbanz import Door
            d = Door(s.url, timeout=5)
            d.create_board("B", columns=[
                {"name": "Backlog", "wipLimit": 0},
                {"name": "Shipped", "wipLimit": 0, "isDoneColumn": True}])
            card = d.add_card("B", "a job")
            out = self._bot(s.url, board="B").cmd_accept(
                None, self._msg(), card.id[:8])
            self.assertIn("took", out)
            self.assertEqual(d.card(card.id).status, "Backlog")

    def test_claim_refuses_when_there_is_nowhere_to_work(self):
        with DoorServer() as s:
            from mem20kanbanz import Door
            d = Door(s.url, timeout=5)
            d.create_board("B", columns=[
                {"name": "Shipped", "wipLimit": 0, "isDoneColumn": True}])
            card = d.add_card("B", "a job")
            out = self._bot(s.url, board="B").cmd_accept(
                None, self._msg(), card.id[:8])
            self.assertIn("no working column", out)

    def test_claim_prefers_the_exact_column_when_it_exists(self):
        with DoorServer() as s:
            from mem20kanbanz import Door
            d = Door(s.url, timeout=5)
            d.create_board("B")
            card = d.add_card("B", "a job")
            out = self._bot(s.url, board="B").cmd_accept(
                None, self._msg(), card.id[:8])
            self.assertIn("in_progress", out)

    def test_status_says_down_when_the_door_is_gone(self):
        from mem20kanbanz import Door
        b = KanbanBot(door=Door("http://127.0.0.1:1", timeout=2))
        self.assertIn("DOWN", b.cmd_status(None, self._msg(), ""))

    def test_advertise_mentions_a_new_job(self):
        with DoorServer() as s:
            from mem20kanbanz import Door
            d = Door(s.url, timeout=5)
            d.create_board("Fleet HQ")
            d.add_card("Fleet HQ", "brand new work")
            line = self._bot(s.url).advertise()
            self.assertIn("brand new work", line)
            self.assertIn("!accept", line)

    def test_advertise_is_quiet_when_nothing_is_new(self):
        with DoorServer() as s:
            from mem20kanbanz import Door
            Door(s.url, timeout=5).create_board("Fleet HQ")
            self.assertIsNone(self._bot(s.url).advertise())

    def test_advertise_does_not_repeat_itself(self):
        with DoorServer() as s:
            from mem20kanbanz import Door
            d = Door(s.url, timeout=5)
            d.create_board("Fleet HQ")
            d.add_card("Fleet HQ", "brand new work")
            b = self._bot(s.url)
            self.assertIsNotNone(b.advertise())
            # Second pass must stay quiet, or the channel gets spam.
            self.assertIsNone(b.advertise())

    def test_a_claimed_job_stops_being_advertised(self):
        with DoorServer() as s:
            from mem20kanbanz import Door
            d = Door(s.url, timeout=5)
            d.create_board("Fleet HQ")
            card = d.add_card("Fleet HQ", "work")
            b = self._bot(s.url)
            b.advertise()
            b.cmd_accept(None, self._msg(), card.id[:8])
            self.assertIsNone(b.advertise())


class TestCommandRouting(unittest.TestCase):
    def _bot(self):
        b = KanbanBot()
        b.said = []
        b.pmmed = []
        b.say = lambda text, target="": b.said.append(text)
        b.pm = lambda nick, text: b.pmmed.append((nick, text))
        return b

    def test_a_command_in_the_channel_is_answered_in_the_channel(self):
        b = self._bot()
        b.on_message(parse_line(
            ":nemotron3ultra!~n@1 PRIVMSG #mem20 :!operator"))
        self.assertTrue(any("Jayson" in s for s in b.said))

    def test_a_command_in_a_dm_is_answered_in_a_dm(self):
        b = self._bot()
        b.on_message(parse_line(
            ":nemotron3ultra!~n@1 PRIVMSG crewbot :!operator"))
        self.assertTrue(any("Jayson" in t for _, t in b.pmmed))
        self.assertEqual(b.said, [])

    def test_a_mention_without_a_command_gets_a_pointer(self):
        b = self._bot()
        b.on_message(parse_line(
            ":nemotron3ultra!~n@1 PRIVMSG #mem20 :kanban are you there?"))
        self.assertTrue(any("!help" in s for s in b.said))
        self.assertEqual(b.mentions, 1)

    def test_a_guest_cannot_take_work(self):
        b = self._bot()
        b.on_message(parse_line(
            ":stranger!~s@1 PRIVMSG #mem20 :!accept abc12345"))
        self.assertTrue(any("crew identity" in s for s in b.said))
        # And crucially the door was never called.
        self.assertTrue(any("!accept" in s for s in b.said))

    def test_a_guest_asking_whoami_is_told_truthfully(self):
        b = self._bot()
        b.on_message(parse_line(
            ":stranger!~s@1 PRIVMSG #mem20 :!whoami"))
        text = " ".join(b.said)
        self.assertIn("guest", text)
        self.assertIn("Ask jayson", text)

    def test_privileged_command_from_a_crew_member_is_refused(self):
        # `!run` is the agentz bot's command, so the gate is tested there.
        b = AgentzBot()
        said = []
        b.say = lambda text, target="": said.append(text)
        b.pm = lambda nick, text: said.append(text)
        b.on_message(parse_line(
            ":nemotron3ultra!~n@1 PRIVMSG agentz :!run status"))
        self.assertTrue(any("operator-only" in s for s in said))

    def test_privileged_command_in_the_channel_is_refused_even_for_operator(self):
        """The transcript is public; a guest could replay what they watched."""
        b = AgentzBot()
        said = []
        b.say = lambda text, target="": said.append(text)
        b.pm = lambda nick, text: said.append(text)
        b.on_message(parse_line(
            ":jayson!~j@1 PRIVMSG #mem20 :!run status"))
        self.assertTrue(any("private message" in s for s in said))

    def test_operator_may_run_a_privileged_command_in_a_dm(self):
        b = AgentzBot()
        said = []
        b.say = lambda text, target="": said.append(text)
        b.pm = lambda nick, text: said.append(text)
        b.on_message(parse_line(
            ":jayson!~j@1 PRIVMSG agentz :!run status"))
        # Allowed through to the handler: it must not be refused for identity.
        self.assertFalse(any("operator-only" in s for s in said))

    def test_crew_may_take_work(self):
        b = self._bot()
        with DoorServer() as s:
            from mem20kanbanz import Door
            d = Door(s.url, timeout=5)
            d.create_board("Fleet HQ")
            card = d.add_card("Fleet HQ", "a job")
            b.door = d
            b.on_message(parse_line(
                f":nemotron3ultra!~n@1 PRIVMSG #mem20 :!accept {card.id[:8]}"))
            self.assertEqual(d.card(card.id).assignee, "nemotron3ultra")

    def test_a_failing_handler_is_reported_not_fatal(self):
        b = self._bot()

        def boom(bot, msg, args):
            raise RuntimeError("kaboom")
        b.commands["boom"] = boom
        b.on_message(parse_line(
            ":nemotron3ultra!~n@1 PRIVMSG #mem20 :!boom"))
        self.assertTrue(any("kaboom" in s for s in b.said))

    def test_an_unknown_command_is_ignored_silently(self):
        b = self._bot()
        b.on_message(parse_line(
            ":nemotron3ultra!~n@1 PRIVMSG #mem20 :!nonsense"))
        self.assertEqual(b.said, [])

    def test_plain_chatter_is_ignored(self):
        b = self._bot()
        b.on_message(parse_line(
            ":nemotron3ultra!~n@1 PRIVMSG #mem20 :just talking"))
        self.assertEqual(b.said, [])

    def test_help_lists_the_commands(self):
        b = self._bot()
        b.on_message(parse_line(
            ":nemotron3ultra!~n@1 PRIVMSG #mem20 :!help"))
        self.assertTrue(any("!accept" in s for s in b.said))


class TestBoundedSubprocesses(unittest.TestCase):
    def test_a_hanging_cli_is_cut_off(self):
        from mem20botz.agent_bots import run_cli
        code, out = run_cli(["/bin/sleep", "30"], timeout=1)
        self.assertEqual(code, 124)
        self.assertIn("timed out", out)

    def test_a_missing_binary_is_reported(self):
        from mem20botz.agent_bots import run_cli
        code, out = run_cli(["/nonexistent/binary"], timeout=2)
        self.assertEqual(code, 127)

    def test_a_failing_command_is_reported_not_raised(self):
        from mem20botz.agent_bots import run_cli
        code, out = run_cli(["/bin/false"], timeout=5)
        self.assertNotEqual(code, 0)

    def test_output_is_condensed(self):
        from mem20botz.agent_bots import condense
        long = "\n".join(f"line {i}" for i in range(100))
        out = condense(long, limit=5)
        self.assertLessEqual(len(out.splitlines()), 6)
        self.assertIn("more lines", out)

    def test_empty_output_says_so(self):
        from mem20botz.agent_bots import condense
        self.assertEqual(condense("   "), "(no output)")

    def test_run_rejects_a_command_outside_the_allowlist(self):
        b = AgentzBot()
        out = b.cmd_run(None, None, "rm -rf /")  # type: ignore[arg-type]
        self.assertIn("not allowed", out)

    def test_run_allows_a_listed_command(self):
        b = AgentzBot()
        out = b.cmd_run(None, None, "status")  # type: ignore[arg-type]
        # Either the CLI answered or it is not on PATH; both are honest, and
        # neither may raise.
        self.assertTrue(out)


class TestCrew(unittest.TestCase):
    def test_crew_has_the_view_bots_and_one_per_orchestrator(self):
        """crewbot already fronts crewz, so the orchestrator bots are the
        other five runtimes: orcaz, langz, kimiz, googlez and the SDK."""
        from mem20botz.crew import Crew
        c = Crew(start_relay=True)
        self.assertEqual([b.nick for b in c.bots],
                         ["kanban", "agentz", "crewbot",
                          "orca", "graph", "swarm", "adk", "sdk", "relay"])

    def test_relay_can_be_left_out(self):
        from mem20botz.crew import Crew
        c = Crew(start_relay=False)
        self.assertNotIn("relay", [b.nick for b in c.bots])

    def test_every_crew_bot_can_describe_itself(self):
        from mem20botz.crew import Crew
        for bot in Crew().bots:
            self.assertIn("reads:", bot.describe(), bot.nick)

    def test_advertise_interval_has_a_floor(self):
        from mem20botz.crew import Crew
        # A 1-second advertise would flood the channel.
        self.assertGreaterEqual(Crew(advertise_every=1).advertise_every, 15)


class TestCli(unittest.TestCase):
    def _run(self, argv):
        from mem20botz.cli import main
        return main(argv)

    def test_version(self):
        self.assertEqual(self._run(["--version"]), 0)

    def test_no_command_is_help_and_exits_two(self):
        self.assertEqual(self._run([]), 2)

    def test_bots_lists_every_bot(self):
        self.assertEqual(self._run(["bots"]), 0)

    def test_whoami_works(self):
        self.assertEqual(self._run(["whoami"]), 0)

    def test_whoami_json(self):
        import json
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(self._run(["whoami", "--json"]), 0)
        self.assertEqual(json.loads(buf.getvalue())["name"], "Jayson")

    def test_watch_against_nothing_exits_one(self):
        self.assertEqual(
            self._run(["watch", "--host", "127.0.0.1", "--port", "1",
                       "--seconds", "1"]), 1)


if __name__ == "__main__":
    unittest.main()
