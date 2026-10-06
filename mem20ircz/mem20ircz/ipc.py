"""Local IPC between the daemon and whoever is asking.

A unix domain socket carrying one JSON object per line, in each direction. The
alternative -- a TCP port or an HTTP server -- would be strictly worse here:
this traffic never leaves the box, and a socket file under ``/run`` is created
and destroyed by systemd with the unit, so there is no stale port to collide
with another service and nothing to clean up by hand.

Line-delimited JSON rather than a framing protocol, because the payloads are
one-line status objects and a reader that gets killed mid-frame loses nothing
that matters.
"""

from __future__ import annotations

import fcntl
import json
import os
import socket
import socketserver
from typing import Optional

DEFAULT_SOCKET = "/run/mem20ircz/hub.sock"

#: Refuse an absurd request rather than allocating for it. A caller asking for
#: a million messages is a bug or an attack, and either way it should not be
#: able to make the daemon build a million-message reply.
MAX_LIMIT = 500


class HubError(RuntimeError):
    """The hub could not satisfy the request."""


def dispatch(hub, request: dict) -> dict:
    """Route one decoded request to the hub. Shared by IPC and tests.

    Keeping this a plain function means the whole request surface is testable
    without a socket in sight, and the socket layer stays a thin shim that has
    no behaviour of its own to get wrong.
    """
    op = request.get("op")

    if op == "status":
        return {"ok": True, **hub.status()}

    if op == "join":
        nick = str(request.get("nick") or hub.default_nick)
        conn = hub.join(nick)
        return {"ok": True, "nick": conn.nick,
                "connected": conn.connected.is_set(),
                "ready": conn.ready.is_set(),
                "latest_seq": conn.buffer.latest_seq,
                "backlog": len(conn.buffer._items)}

    if op == "read":
        conn = hub.get(request.get("nick"))
        if conn.fatal:
            return {"ok": False,
                    "error": f"nick unavailable: {conn.fatal}"}
        return {"ok": True, **hub.read(
            since=int(request.get("since") or 0),
            limit=min(int(request.get("limit") or 50), MAX_LIMIT),
            nick=request.get("nick"))}

    if op == "say":
        text = str(request.get("text") or "").strip()
        if not text:
            return {"ok": False, "error": "say needs text"}
        try:
            return {"ok": True, **hub.say(text, nick=request.get("nick"),
                                          target=request.get("target"))}
        except Exception as exc:  # noqa: BLE001 - reported, not raised at the edge
            return {"ok": False, "error": str(exc)}

    if op == "who":
        return {"ok": True, **hub.who(request.get("nick"))}

    return {"ok": False, "error": f"unknown op: {op!r}"}


class _Handler(socketserver.StreamRequestHandler):
    """One request per connection, then close."""

    timeout = 15

    def handle(self) -> None:
        line = self.rfile.readline()
        if not line:
            return
        hub = getattr(self.server, "hub", None)
        if hub is None:
            reply = {"ok": False, "error": "hub not attached to server"}
            self.wfile.write((json.dumps(reply) + "\n").encode("utf-8"))
            return
        try:
            request = json.loads(line.decode("utf-8"))
            if not isinstance(request, dict):
                raise ValueError("request must be a JSON object")
            reply = dispatch(hub, request)
        except Exception as exc:  # noqa: BLE001
            reply = {"ok": False, "error": str(exc)}
        self.wfile.write((json.dumps(reply, default=str) + "\n").encode("utf-8"))


class HubServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True
    allow_reuse_address = True

    #: Set in __init__. Declared here so the request handler can reach it --
    #: socketserver's own type does not describe per-server attributes.
    hub: object

    def __init__(self, path: str, hub) -> None:
        self.hub = hub
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        # Take an exclusive lock *before* touching the socket path. Unlinking
        # first and binding after is what a second daemon used to do: it stole
        # the path from a live hub, which then kept running while every client
        # got "connection refused". The fleet control plane health-probes every
        # console script it discovers, so a stray second invocation was not a
        # hypothetical -- it happened on a timer. With the lock, a second
        # instance is refused, and only a lock we own means no live owner, so
        # removing the leftover socket file is safe.
        self._lock_fd = os.open(path + ".lock",
                                os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(self._lock_fd)
            self._lock_fd = None
            raise HubError(
                f"another mem20ircz hub already owns {path}; refusing to "
                f"take its socket") from exc

        try:
            if os.path.exists(path):
                os.unlink(path)
            super().__init__(path, _Handler)
            os.chmod(path, 0o660)
        except Exception:
            fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
            os.close(self._lock_fd)
            self._lock_fd = None
            raise

    def server_close(self) -> None:
        super().server_close()
        if self._lock_fd is not None:
            try:
                fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
                os.close(self._lock_fd)
            except OSError:
                pass
            self._lock_fd = None


class HubClient:
    """Talk to a running hub. Raises :class:`HubError` on transport failure."""

    def __init__(self, path: str = DEFAULT_SOCKET, timeout: float = 10.0) -> None:
        self.path = path
        self.timeout = timeout

    def call(self, op: str, **kwargs) -> dict:
        payload = json.dumps({"op": op, **kwargs}).encode("utf-8")
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(self.timeout)
                sock.connect(self.path)
                sock.sendall(payload + b"\n")
                buf = b""
                while not buf.endswith(b"\n"):
                    chunk = sock.recv(65536)
                    if not chunk:
                        break
                    buf += chunk
        except (OSError, socket.timeout) as exc:
            raise HubError(
                f"cannot reach the mem20ircz hub at {self.path}: {exc}. "
                f"Is mem20ircz.service running?") from exc
        if not buf.strip():
            raise HubError("hub closed the connection without replying")
        try:
            return json.loads(buf.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise HubError(f"unreadable reply from hub: {exc}") from exc

    # Convenience wrappers, so callers read like the API rather than the wire.
    def status(self) -> dict:
        return self.call("status")

    def join(self, nick: Optional[str] = None) -> dict:
        return self.call("join", nick=nick or "")

    def read(self, since: int = 0, limit: int = 50,
             nick: Optional[str] = None) -> dict:
        return self.call("read", since=since, limit=limit, nick=nick or "")

    def say(self, text: str, nick: Optional[str] = None,
            target: Optional[str] = None) -> dict:
        return self.call("say", text=text, nick=nick or "", target=target or "")

    def who(self, nick: Optional[str] = None) -> dict:
        return self.call("who", nick=nick or "")