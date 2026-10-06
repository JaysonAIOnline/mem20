"""The daemon entry point.

The behaviour that matters here is not "it runs a server" -- it is that a
routine health probe cannot turn into a second one. mem20controlz discovers
console scripts and runs ``<binary> --json health`` against each, so the daemon
entry point has to answer that sanely instead of binding a socket.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading

import pytest

from mem20ircz import daemon as daemon_mod
from mem20ircz.ipc import HubError, HubServer
from tests.test_ipc import StubHub


class TestHealthVerb:
    def test_health_reports_ok_as_json_when_the_hub_is_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "hub.sock")
            srv = HubServer(path, StubHub())
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            try:
                assert daemon_mod.main(["--json", "--socket", path,
                                        "health"]) == 0
            finally:
                srv.shutdown()
                srv.server_close()

    def test_health_json_is_parseable(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "hub.sock")
            srv = HubServer(path, StubHub())
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            try:
                daemon_mod.main(["--json", "--socket", path, "health"])
                payload = json.loads(capsys.readouterr().out)
            finally:
                srv.shutdown()
                srv.server_close()
        assert payload["ok"] is True
        assert payload["healthy"] is True
        assert payload["status"]["host"] == "127.0.0.1"

    def test_health_fails_cleanly_when_nothing_is_listening(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "absent.sock")
            assert daemon_mod.main(["--json", "--socket", path,
                                    "health"]) == 1
            payload = json.loads(capsys.readouterr().out)
        assert payload["healthy"] is False
        assert "mem20ircz.service" in payload["error"]

    def test_health_does_not_bind_a_socket(self):
        # The whole point. A health probe must leave the running hub alone.
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "hub.sock")
            srv = HubServer(path, StubHub())
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            try:
                daemon_mod.main(["--json", "--socket", path, "health"])
                # A second server on the same path must still be refused.
                with pytest.raises(HubError):
                    HubServer(path, StubHub())
            finally:
                srv.shutdown()
                srv.server_close()


class TestServeRefusesToSteal:
    def test_serve_exits_nonzero_when_another_hub_owns_the_socket(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "hub.sock")
            srv = HubServer(path, StubHub())
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            try:
                code = daemon_mod.serve(socket_path=path, port=1,
                                        channel="#x", nick="other")
                assert code == 1
                assert "already owns" in capsys.readouterr().err
            finally:
                srv.shutdown()
                srv.server_close()

    def test_unknown_subcommand_is_refused_not_run_as_a_daemon(self, capsys):
        # Silently becoming a server on a typo is how the original bug happened.
        # argparse owns this path and exits 2 itself, which is the right exit
        # code for a usage error and is what a caller actually observes.
        with pytest.raises(SystemExit) as excinfo:
            daemon_mod.main(["frobnicate"])
        assert excinfo.value.code == 2
        assert "usage" in capsys.readouterr().err.lower()