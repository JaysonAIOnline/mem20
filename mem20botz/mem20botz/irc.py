"""A small, dependency-free IRC client for the mem20 crew channel.

Written against RFC 1459 because the estate should not need a third-party IRC
library to have four bots talk to each other. The surface is deliberately
tiny: connect, register, join, read lines, send, stay alive.

Every blocking operation is bounded. An IRC socket that stops delivering must
not wedge a systemd unit into a silent hang, because a hung bot is
indistinguishable from a dead one and nobody notices until the channel is
quiet. So reads are timeouts, the reconnect backoff is capped, and shutdown is
a signal-driven flag rather than an exception.
"""

from __future__ import annotations

import re
import signal
import socket
import ssl
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

CRLF = b"\r\n"
# An IRC line is 512 bytes including CRLF. A longer buffer means a malformed
# or hostile peer, and unbounded reads are how a client gets OOM-killed.
MAX_LINE = 2048


class IRCError(RuntimeError):
    """The IRC conversation failed."""


@dataclass
class Message:
    """One parsed IRC line.

    ``prefix`` is the sender (nick!user@host), or the server name for numerics.
    ``command`` is PRIVMSG, JOIN, 001, PING, ...
    ``params`` holds the arguments, with the trailing human-readable text in
    ``text`` when the command has one.
    """

    raw: str
    prefix: str
    command: str
    params: list[str] = field(default_factory=list)
    text: str = ""

    @property
    def nick(self) -> str:
        """The sender's nick, or "" when the line came from the server.

        A numeric like ``001`` is prefixed by the *server* name, not a nick.
        Returning that name here would make a server message look like
        something a person said, so a caller filtering on "did a human say
        this" would be wrong.
        """
        if not self.prefix or self.command.isdigit():
            return ""
        return self.prefix.split("!", 1)[0]

    @property
    def is_from_server(self) -> bool:
        return not self.prefix or self.command.isdigit()

    @property
    def target(self) -> str:
        return self.params[0] if self.params else ""

    @property
    def is_channel(self) -> bool:
        t = self.target
        return bool(t) and t[0] in "#&+!"

    def __repr__(self) -> str:
        return (f"Message({self.command} from={self.nick or self.prefix!r} "
                f"target={self.target!r} text={self.text[:40]!r})")


def parse_line(line: str) -> Optional[Message]:
    """Parse one IRC protocol line. Returns None for a blank line."""
    line = line.strip()
    if not line:
        return None
    prefix = ""
    if line.startswith(":"):
        prefix, _, line = line[1:].partition(" ")
    if " :" in line:
        head, _, text = line.partition(" :")
    else:
        head, text = line, ""
    parts = head.split()
    if not parts:
        return None
    command = parts[0]
    params = parts[1:]
    return Message(raw=line, prefix=prefix, command=command,
                   params=params, text=text)


class IRCClient:
    """A single IRC connection.

    :param host: server host.
    :param port: server port.
    :param nick: nickname to register. Must fit the server's nick length.
    :param channels: channels to join once registered.
    :param on_message: called for every inbound message, including numerics.
        Exceptions raised here are caught and reported through
        :attr:`last_handler_error` rather than killing the connection, so one
        bad command cannot take the bot offline.
    :param ssl_context: wrap the socket in TLS when given.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 6667,
                 nick: str = "mem20bot", channels: tuple[str, ...] = ("#mem20",),
                 on_message: Optional[Callable[[Message], None]] = None,
                 realname: str = "mem20 crew bot",
                 timeout: float = 30.0,
                 ssl_context: Optional[ssl.SSLContext] = None) -> None:
        self.host = host
        self.port = port
        self.nick = nick
        self.channels = tuple(channels)
        self.on_message = on_message
        self.realname = realname
        self.timeout = timeout
        self.ssl_context = ssl_context
        self.sock: Optional[socket.socket] = None
        self._buffer = b""
        self._stop = False
        #: Last exception raised by the message handler, for the health check.
        self.last_handler_error: Optional[BaseException] = None
        #: Set once the server has sent 001 (end of MOTD).
        self.registered = False

    # ------------------------------------------------------------ lifecycle
    def stop(self, *_args) -> None:
        """Ask the read loop to finish. Safe to call from a signal handler."""
        self._stop = True

    def connect(self) -> None:
        self.sock = socket.create_connection((self.host, self.port),
                                             timeout=self.timeout)
        if self.ssl_context is not None:
            self.sock = self.ssl_context.wrap_socket(
                self.sock, server_hostname=self.host)
        self.sock.settimeout(self.timeout)
        self._buffer = b""
        self.registered = False
        self.send_raw(f"NICK {self.nick}")
        self.send_raw(f"USER {self.nick} 0 * :{self.realname}")

    def close(self) -> None:
        if self.sock is not None:
            try:
                self.send_raw("QUIT :leaving")
            except OSError:
                pass
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None

    # ----------------------------------------------------------------- send
    def send_raw(self, line: str) -> None:
        if self.sock is None:
            raise IRCError("not connected")
        payload = line.encode("utf-8", "replace")[:MAX_LINE - 2] + CRLF
        self.sock.sendall(payload)

    def say(self, target: str, text: str) -> None:
        """Send a message, splitting on newlines.

        IRC has no multi-line message; a raw newline would be read by the peer
        as a protocol injection. So each line is sent as its own PRIVMSG.
        """
        for chunk in str(text).splitlines() or [""]:
            self.send_raw(f"PRIVMSG {target} :{chunk[:400]}")

    def join(self, channel: str) -> None:
        self.send_raw(f"JOIN {channel}")

    def part(self, channel: str, reason: str = "") -> None:
        self.send_raw(f"PART {channel} :{reason}" if reason else f"PART {channel}")

    # ----------------------------------------------------------------- read
    def read_message(self) -> Optional[Message]:
        """Block for one message, or return None on timeout/EOF.

        A timeout is not an error: the caller decides whether to keep going.
        EOF (the peer closed) raises, because that is a real disconnect.
        """
        while b"\n" not in self._buffer:
            if len(self._buffer) > MAX_LINE * 8:
                # Refuse to grow without bound. A peer that never sends a
                # newline must not be able to exhaust memory.
                self._buffer = b""
                raise IRCError("line buffer overflow (malformed peer)")
            try:
                chunk = self.sock.recv(4096)  # type: ignore[union-attr]
            except socket.timeout:
                return None
            if not chunk:
                raise IRCError("server closed the connection")
            self._buffer += chunk
        raw, _, rest = self._buffer.partition(b"\n")
        self._buffer = rest
        return parse_line(raw.decode("utf-8", "replace").rstrip("\r"))

    def dispatch(self, msg: Message) -> None:
        """Apply protocol housekeeping, then hand the message to the callback."""
        if msg.command == "PING":
            self.send_raw(f"PONG :{msg.text or msg.params[-1]}")
            return
        if msg.command == "001":
            self.registered = True
            for ch in self.channels:
                self.join(ch)
        if msg.command == "433":  # nick in use
            raise IRCError(f"nick {self.nick!r} is already in use")
        if self.on_message is not None:
            try:
                self.on_message(msg)
            except Exception as exc:  # noqa: BLE001
                # A failing command handler must not kill the connection.
                self.last_handler_error = exc

    def run_forever(self, reconnect_delay: float = 2.0,
                    max_delay: float = 30.0) -> None:
        """Connect, then serve until :meth:`stop`, reconnecting on failure.

        The backoff doubles up to ``max_delay`` so a server that is down for a
        while does not turn into a reconnect storm against its log.
        """
        delay = reconnect_delay
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                signal.signal(sig, self.stop)
            except (ValueError, OSError):
                pass  # not on the main thread
        while not self._stop:
            try:
                self.connect()
                delay = reconnect_delay
                while not self._stop:
                    msg = self.read_message()
                    if msg is not None:
                        self.dispatch(msg)
            except (OSError, IRCError):
                self.close()
                if self._stop:
                    break
                time.sleep(delay)
                delay = min(delay * 2, max_delay)
        self.close()


def install_signal_handlers(bot) -> None:
    """Wire SIGTERM/SIGINT to ``bot.stop`` for a bot object with one."""

    def _handler(*_a):
        if hasattr(bot, "stop"):
            bot.stop()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _handler)
        except (ValueError, OSError):
            pass


_COMMAND_RE = re.compile(r"^!(\w+)\s*(.*)$")


def parse_command(text: str) -> Optional[tuple[str, str]]:
    """Split ``!accept abc123 rest`` into ``("accept", "abc123 rest")``.

    Returns None when the line is not a command, so a bot can ignore ordinary
    chatter without a regex test at every call site.
    """
    m = _COMMAND_RE.match(text.strip())
    if not m:
        return None
    return m.group(1).lower(), m.group(2).strip()
