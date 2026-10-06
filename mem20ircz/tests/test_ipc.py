"""The request surface: dispatch, the socket, and the CLI an agent calls.

The dispatch tests need no socket at all, which is the point of keeping
routing in a plain function. The socket tests then only have to prove that
bytes get in and bytes come out.
"""

from __future__ import annotations

import json
import os
import socket
import tempfile
import threading
import time
from typing import ClassVar

import pytest

from mem20ircz.ipc import (MAX_LIMIT, HubClient, HubError, HubServer,
                           dispatch)


class StubConnection:
    def __init__(self, nick="tester"):
        self.nick = nick
        self.connected = threading.Event()
        self.connected.set()
        self.sent = []
        self.members = ["muse", "jayson"]

        class _Buf:
            _items: ClassVar[list] = [1, 2, 3]

            def latest_seq(self):
                return 3

            def oldest_seq(self):
                return 1

            def since(self, since=0, limit=50):
                return ([{"seq": 1, "text": "hello", "nick": "muse",
                          "mine": False}], False, 3)

        self.buffer = _Buf()
        self.fatal = ""

    def start(self):
        return self

    def say(self, text, target=None):
        self.sent.append((text, target))

    def who(self):
        # Sorted, because that is the contract Connection.who() offers and a
        # test that accepts unsorted output would not notice it drifting.
        return sorted(self.members)

    def status(self):
        return {"nick": self.nick, "connected": True, "ready": True,
                "channels": ["#c"],
                "disconnects": 0, "last_error": "", "fatal": "",
                "buffered": 3, "latest_seq": 3,
                "noise": {"lines_seen": 24, "kept": 3, "swallowed": 21,
                          "waste_ratio": 0.875, "by_reason": {}}}


class StubHub:
    default_nick = "tester"

    def __init__(self):
        self.conn = StubConnection()
        self.connections = {"tester": self.conn}

    def get(self, nick=None):
        return self.conn

    def join(self, nick):
        self.conn.nick = nick or self.default_nick
        return self.conn

    def status(self):
        return {"host": "127.0.0.1", "port": 6667, "channels": ["#c"],
                "default_nick": "tester",
                "connections": {"tester": self.conn.status()}}

    def read(self, since=0, limit=50, nick=None):
        msgs, truncated, latest = self.conn.buffer.since(since, limit)
        return {"nick": self.conn.nick, "connected": True, "messages": msgs,
                "count": len(msgs), "latest_seq": latest, "oldest_seq": 1,
                "truncated": truncated, "disconnects": 0}

    def say(self, text, nick=None, target=None):
        self.conn.say(text, target)
        return {"nick": self.conn.nick, "sent": text}

    def who(self, nick=None):
        return {"nick": self.conn.nick, "nicks": self.conn.who()}


class TestDispatch:
    def test_status_is_answered(self):
        reply = dispatch(StubHub(), {"op": "status"})
        assert reply["ok"] is True
        assert reply["connections"]["tester"]["noise"]["waste_ratio"] == 0.875

    def test_read_returns_messages(self):
        reply = dispatch(StubHub(), {"op": "read", "since": 0})
        assert reply["ok"] is True
        assert reply["count"] == 1
        assert reply["messages"][0]["text"] == "hello"

    def test_say_sends(self):
        hub = StubHub()
        reply = dispatch(hub, {"op": "say", "text": "hello room"})
        assert reply["ok"] is True
        assert hub.conn.sent == [("hello room", None)]

    def test_say_without_text_is_refused(self):
        reply = dispatch(StubHub(), {"op": "say", "text": "  "})
        assert reply["ok"] is False
        assert "needs text" in reply["error"]

    def test_who_lists_the_room(self):
        reply = dispatch(StubHub(), {"op": "who"})
        assert reply["nicks"] == ["jayson", "muse"]

    def test_unknown_op_is_refused_not_crashed(self):
        reply = dispatch(StubHub(), {"op": "rm -rf"})
        assert reply["ok"] is False
        assert "unknown op" in reply["error"]

    def test_limit_is_capped(self):
        # A caller must not be able to make the daemon build an unbounded reply.
        assert MAX_LIMIT == 500
        reply = dispatch(StubHub(), {"op": "read", "limit": 10_000_000})
        assert reply["ok"] is True

    def test_fatal_nick_is_reported_not_hidden(self):
        hub = StubHub()
        hub.conn.fatal = "Nickname is already in use"
        reply = dispatch(hub, {"op": "read"})
        assert reply["ok"] is False
        assert "already in use" in reply["error"]


class TestSocketTransport:
    @pytest.fixture
    def sock_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            yield os.path.join(tmp, "hub.sock")

    @pytest.fixture
    def server(self, sock_path):
        srv = HubServer(sock_path, StubHub())
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            yield srv
        finally:
            srv.shutdown()
            srv.server_close()

    def test_round_trip_over_the_socket(self, server, sock_path):
        reply = HubClient(sock_path).call("say", text="over the wire")
        assert reply["ok"] is True
        assert reply["sent"] == "over the wire"

    def test_read_over_the_socket(self, server, sock_path):
        reply = HubClient(sock_path).read(since=0, limit=10)
        assert reply["count"] == 1

    def test_garbage_does_not_kill_the_connection(self, server, sock_path):
        # A malformed request must come back as an error, not as a dead socket.
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(5)
            sock.connect(sock_path)
            sock.sendall(b"this is not json\n")
            data = sock.recv(65536)
        assert json.loads(data.decode())["ok"] is False

    def test_json_array_request_is_refused(self, server, sock_path):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(5)
            sock.connect(sock_path)
            sock.sendall(b"[1,2,3]\n")
            data = sock.recv(65536)
        assert json.loads(data.decode())["ok"] is False

    def test_missing_daemon_gives_an_actionable_error(self, sock_path):
        with pytest.raises(HubError) as excinfo:
            HubClient(sock_path).status()
        # The message has to say what to do, not just that it failed.
        assert "mem20ircz.service" in str(excinfo.value)

    def test_stale_socket_file_is_replaced(self, sock_path):
        # A daemon killed hard leaves its socket file behind; bind must not fail.
        with open(sock_path, "w") as fh:
            fh.write("")
        srv = HubServer(sock_path, StubHub())
        try:
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            assert HubClient(sock_path).status()["ok"] is True
        finally:
            srv.shutdown()
            srv.server_close()

    def test_a_second_server_cannot_steal_a_live_socket(self, server, sock_path):
        # This is not hypothetical: mem20controlz health-probes every console
        # script it finds with `<binary> --json health`, and a daemon entry
        # point that ignored argv turned that routine probe into a second hub
        # unlinking the live one's socket. The first hub kept running while every
        # client got "connection refused".
        with pytest.raises(HubError) as excinfo:
            HubServer(sock_path, StubHub())
        assert "already owns" in str(excinfo.value)
        # And the original is still serving, not orphaned.
        assert HubClient(sock_path).status()["ok"] is True

    def test_lock_is_released_when_the_server_closes(self, sock_path):
        srv = HubServer(sock_path, StubHub())
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        srv.shutdown()
        srv.server_close()
        # After a clean stop the path is free again, so a restart is not blocked
        # by its own lock file.
        second = HubServer(sock_path, StubHub())
        try:
            threading.Thread(target=second.serve_forever, daemon=True).start()
            assert HubClient(sock_path).status()["ok"] is True
        finally:
            second.shutdown()
            second.server_close()


class TestCli:
    def _run(self, argv, sock_path):
        from mem20ircz.cli import main
        return main(["--socket", sock_path] + argv)

    @pytest.fixture
    def cli_server(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "hub.sock")
            srv = HubServer(path, StubHub())
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            try:
                yield path
            finally:
                srv.shutdown()
                srv.server_close()

    def test_who_prints_the_room(self, cli_server, capsys):
        assert self._run(["who"], cli_server) == 0
        assert "muse" in capsys.readouterr().out

    def test_status_prints_the_noise_evidence(self, cli_server, capsys):
        assert self._run(["status"], cli_server) == 0
        out = capsys.readouterr().out
        assert "wire lines=24" in out
        assert "swallowed=21" in out
        assert "87.5% waste" in out

    def test_read_prints_messages_and_cursor(self, cli_server, capsys):
        assert self._run(["read"], cli_server) == 0
        captured = capsys.readouterr()
        assert "<muse> hello" in captured.out
        # The cursor goes to stderr so stdout stays a clean message stream that
        # an agent can pipe somewhere without picking up its own bookkeeping.
        assert "latest seq 3" in captured.err

    def test_say_prints_confirmation(self, cli_server, capsys):
        assert self._run(["say", "hello", "room"], cli_server) == 0
        assert "sent to tester" in capsys.readouterr().out

    def test_json_output_is_parseable(self, cli_server, capsys):
        assert self._run(["--json", "who"], cli_server) == 0
        assert json.loads(capsys.readouterr().out)["nicks"] == ["jayson", "muse"]

    def test_missing_daemon_exits_nonzero(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            code = self._run(["status"], os.path.join(tmp, "absent.sock"))
        assert code == 1
        assert "mem20ircz.service" in capsys.readouterr().err

    def test_health_verb_answers_the_control_plane_probe(self, cli_server,
                                                          capsys):
        # mem20controlz probes every console script with `<binary> --json
        # health`, so this verb has to exist and return real state.
        assert self._run(["--json", "health"], cli_server) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["healthy"] is True
        assert payload["connections"]["tester"]["ready"] is True

    def test_health_is_not_ok_when_the_hub_is_absent(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            code = self._run(["--json", "health"],
                             os.path.join(tmp, "absent.sock"))
        assert code == 1
        capsys.readouterr()

    def test_version(self, capsys):
        from mem20ircz.cli import main
        assert main(["--version"]) == 0
        assert "mem20ircz" in capsys.readouterr().out

    def test_no_command_prints_help(self, capsys):
        from mem20ircz.cli import main
        assert main([]) == 2
        assert "usage" in capsys.readouterr().out.lower()

    def test_bounded_wait_returns_promptly_when_idle(self, cli_server):
        # A read that waits must still return when nothing arrives; an agent
        # turn must not hang on a quiet channel.
        started = time.time()
        assert self._run(["read", "--wait", "1"], cli_server) == 0
        assert time.time() - started < 6.0