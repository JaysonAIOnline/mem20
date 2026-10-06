"""Shared fixtures: a real in-process IRC server to talk to.

The tests point the hub at an actual socket speaking the actual protocol rather
than at a mock object. The wire contract and the delta-read semantics are the
two things worth protecting, and neither is protected by a mock that agrees
with whatever the code does today.
"""

from __future__ import annotations

import socket
import threading
import time

import pytest


class FakeIRCServer:
    """A minimal RFC 1459 server: enough to register, join and talk.

    Bounded everywhere. Each test gets a fresh instance on an ephemeral port and
    shuts it down, so no test can hang the suite or collide with a live daemon
    on 6667.
    """

    def __init__(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(8)
        self._sock.settimeout(0.5)
        self.port = self._sock.getsockname()[1]
        self.clients: list = []
        self.received: list = []
        self._clients_lock = threading.Lock()
        self._stop = threading.Event()
        self.motd_sent = threading.Event()
        #: Nicks this server refuses on every attempt, which is what a nick
        #: genuinely held by somebody else looks like.
        self.rejected_nicks: set = set()
        #: How many TCP connections this server has accepted. A test can watch
        #: this to know a reconnect genuinely happened, rather than inferring it
        #: from a connection flag that a previous session already set.
        self.accept_count = 0
        self._thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._thread.start()

    # ------------------------------------------------------------- lifecycle
    def _accept_loop(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _addr = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            conn.settimeout(0.5)
            with self._clients_lock:
                self.clients.append(conn)
                self.accept_count += 1
            threading.Thread(target=self._serve, args=(conn,),
                             daemon=True).start()

    def _serve(self, conn: socket.socket) -> None:
        buf = b""
        registered = False
        while not self._stop.is_set():
            try:
                chunk = conn.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                return
            if not chunk:
                return
            buf += chunk
            *lines, buf = buf.split(b"\n")
            for line in lines:
                text = line.decode("utf-8", "replace").rstrip("\r")
                if not text:
                    continue
                with self._clients_lock:
                    self.received.append(text)
                if text.startswith("NICK "):
                    wanted = text.split()[1]
                    if wanted in self.rejected_nicks:
                        # As a real server does: refuse every attempt, so the
                        # client sees a conflict it cannot retry its way out of.
                        self.send(conn,
                                  f":fakeirc 433 * {wanted} :Nickname is already "
                                  f"in use")
                        continue
                    self._nicks[id(conn)] = wanted
                    continue
                if text.startswith("USER "):
                    if not registered:
                        registered = True
                        self._send_burst(conn)
                        self.motd_sent.set()
                    continue
                if text.startswith("PING"):
                    self.send(conn, f"PONG :{text.split(':', 1)[-1]}")
                elif text.startswith("JOIN"):
                    chan = text.split()[1]
                    self.send(conn, f":{self._nick_of(conn)}!u@h JOIN {chan}")
                    self.send(conn, f":fakeirc 353 {self._nick_of(conn)} = {chan} "
                                    f":fakeirc someone")
                    self.send(conn, f":fakeirc 366 {self._nick_of(conn)} {chan}"
                                    f" :End of NAMES")

    _nicks: dict = {}

    def _nick_of(self, conn) -> str:
        return self._nicks.get(id(conn), "fake")

    def register_nick(self, conn, nick: str) -> None:
        self._nicks[id(conn)] = nick

    def _send_burst(self, conn) -> None:
        """The connect burst that is pure waste: MOTD plus server numerics."""
        nick = self._nick_of(conn)
        for line in [
            f":fakeirc 001 {nick} :Welcome to the test network {nick}",
            f":fakeirc 002 {nick} :Your host is fakeirc, running version test-1",
            f":fakeirc 003 {nick} :This server was created today",
            f":fakeirc 004 {nick} fakeirc test-1 iow abc",
            f":fakeirc 005 {nick} NETWORK=Test :are supported by this server",
            f":fakeirc 251 {nick} :There are 2 users and 0 services on 1 servers",
            f":fakeirc 254 {nick} :3 channels formed",
            f":fakeirc 255 {nick} :I have 2 users, 0 services and 0 servers",
            f":fakeirc 265 {nick} 5 10 :Current local users 5, max 10",
            f":fakeirc 266 {nick} 5 10 :Global users 5, max 10",
            f":fakeirc 375 {nick} :- fakeirc Message of the Day -",
            f":fakeirc 372 {nick} :- a wall of text nobody asked for",
            f":fakeirc 376 {nick} :End of MOTD command.",
        ]:
            self.send(conn, line)

    def _send(self, conn, line: str) -> None:
        try:
            conn.sendall((line + "\r\n").encode("utf-8"))
        except OSError:
            pass

    # ---------------------------------------------------------------- public
    def send(self, conn, line: str) -> None:
        self._send(conn, line)

    def broadcast(self, line: str) -> None:
        with self._clients_lock:
            conns = list(self.clients)
        for conn in conns:
            self.send(conn, line)

    def say(self, nick: str, target: str, text: str) -> None:
        self.broadcast(f":{nick}!u@h PRIVMSG {target} :{text}")

    def wait_for(self, predicate, timeout: float = 5.0) -> bool:
        """Bounded wait. Returns False rather than hanging the suite."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._clients_lock:
                if predicate(list(self.received)):
                    return True
            time.sleep(0.02)
        return False

    def stop(self) -> None:
        self._stop.set()
        try:
            self._sock.close()
        except OSError:
            pass
        with self._clients_lock:
            conns = list(self.clients)
        for conn in conns:
            try:
                conn.close()
            except OSError:
                pass


@pytest.fixture
def ircd():
    server = FakeIRCServer()
    try:
        yield server
    finally:
        server.stop()


@pytest.fixture
def hub(ircd):
    from mem20ircz.hub import Hub

    instance = Hub(host="127.0.0.1", port=ircd.port, channels=("#test",),
                  default_nick="tester", buffer_size=100)
    try:
        yield instance
    finally:
        instance.stop()