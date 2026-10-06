"""The persistent connection owner.

One process holds the IRC sockets so an agent never has to. The agent asks a
question over a local socket and gets an answer from a connection that has been
open for hours -- that is the whole difference between this and polling a log
file.

Design points that are load-bearing rather than stylistic:

* **Reuse, not rewrite.** The protocol layer is ``mem20botz.irc``, already
  dependency-free and already tested with literal wire lines. This module owns
  the *lifecycle* (heartbeat, reconnect, buffering), not the wire format.
* **A ring buffer per connection, not one shared.** Two nicks in one room each
  receive their own copy of every message from the server. A single shared
  buffer would double-count, so each connection owns its own.
* **Monotonic sequence numbers.** An agent's cursor is a number, not a
  timestamp. Timestamps collide inside one second, and a colliding cursor makes
  an agent silently re-read or silently miss.
* **Truncation and gaps are reported, never hidden.** If an agent asks for
  messages the buffer has already discarded, the answer says so instead of
  quietly returning a partial set that reads like the whole conversation.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Optional

from mem20botz.irc import IRCClient, IRCError

from .filter import NoiseMeter, apply_roster, classify, numeric_channel

DEFAULT_BUFFER = 500


@dataclass(frozen=True)
class ChatMessage:
    """One message that survived the filter."""

    seq: int
    ts: float
    nick: str
    target: str
    text: str
    mine: bool = False

    def to_dict(self) -> dict:
        return {"seq": self.seq, "ts": self.ts, "nick": self.nick,
                "target": self.target, "text": self.text, "mine": self.mine}


class RingBuffer:
    """A bounded, monotonically numbered buffer of channel messages.

    Bounded because an agent must never be able to make the daemon's memory grow
    without limit, and because an unbounded backlog is not something an agent
    would read anyway.
    """

    def __init__(self, maxlen: int = DEFAULT_BUFFER) -> None:
        self._items: deque = deque(maxlen=maxlen)
        self._seq = 0
        self._lock = threading.Lock()

    def append(self, *, ts: float, nick: str, target: str, text: str,
               mine: bool = False) -> ChatMessage:
        with self._lock:
            self._seq += 1
            msg = ChatMessage(seq=self._seq, ts=ts, nick=nick, target=target,
                              text=text, mine=mine)
            self._items.append(msg)
            return msg

    @property
    def latest_seq(self) -> int:
        with self._lock:
            return self._seq

    @property
    def oldest_seq(self) -> int:
        with self._lock:
            return self._items[0].seq if self._items else 0

    def since(self, since: int = 0, limit: int = 50) -> tuple:
        """Return ``(messages, truncated, latest_seq)``.

        ``truncated`` is True when ``since`` points at messages the buffer has
        already discarded. The caller is then looking at a conversation with a
        hole in it, and has to be told rather than left to assume continuity.

        ``since=0`` is not exempt. An agent's *first* read after a long absence
        asks for everything, and if the buffer has rolled in the meantime that
        read is missing history -- which is precisely the case that is easiest
        to miss and most misleading to get wrong.
        """
        with self._lock:
            latest = self._seq
            oldest = self._items[0].seq if self._items else 0
            truncated = bool(oldest and since < oldest - 1)
            out = [m for m in self._items if m.seq > since][:max(1, limit)]
            return [m.to_dict() for m in out], truncated, latest


class Connection:
    """One real IRC connection, owned by the daemon, supervised in a thread.

    The connection has to survive things an agent cannot see: a server restart,
    an idle TCP connection quietly dropped by a middlebox, a nick collision.
    Each of those is handled here rather than surfacing as a failed tool call.
    """

    def __init__(self, *, host: str, port: int, nick: str, channels,
                 buffer_size: int = DEFAULT_BUFFER,
                 ping_every: float = 60.0, dead_after: float = 180.0,
                 reconnect_delay: float = 2.0, max_delay: float = 30.0,
                 read_timeout: float = 1.0,
                 nick_attempts: int = 6) -> None:
        self.host = host
        self.port = port
        self.nick = nick
        self.channels = tuple(channels)
        self.ping_every = ping_every
        self.dead_after = dead_after
        self.reconnect_delay = reconnect_delay
        self.max_delay = max_delay
        self.read_timeout = read_timeout
        #: How many times to be told the nick is taken before believing it.
        #: Not 1 -- see _run.
        self.nick_attempts = nick_attempts
        self.nick_conflicts = 0

        self.buffer = RingBuffer(buffer_size)
        self.meter = NoiseMeter()
        self.rosters: dict = {}

        self.connected = threading.Event()
        #: Set once the server has registered us *and* the channel roster has
        #: arrived, which is the first moment we can actually hear the room and
        #: be heard in it. ``connected`` only means the socket is up, and
        #: treating the two as the same is how a caller ends up speaking into a
        #: channel it has not joined yet and losing the message.
        self.ready = threading.Event()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_rx = 0.0
        self._last_ping = 0.0
        self.disconnects = 0
        self.last_error: str = ""
        #: Set when the nick is taken. Retrying cannot fix this, so the
        #: connection stops instead of hammering the server forever.
        self.fatal: str = ""
        self._client: Optional[IRCClient] = None

    # ------------------------------------------------------------- lifecycle
    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name=f"irc-{self.nick}")
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=timeout)
        self._close()

    def _close(self) -> None:
        client = self._client
        self._client = None
        self.connected.clear()
        # Readiness does not survive a dropped socket. Leaving it set would let
        # a caller speak into a room we are no longer in and lose the message
        # with no error to explain why.
        self.ready.clear()
        if client is not None:
            try:
                client.close()
            except OSError:
                pass

    def _run(self) -> None:
        delay = self.reconnect_delay
        while not self._stop.is_set():
            try:
                self._session()
                delay = self.reconnect_delay
            except IRCError as exc:
                self.last_error = str(exc)
                # A nick conflict is usually *transient*: after a restart the
                # previous session's nick has not been released yet, and the
                # server answers the first attempt with 433. Giving up on the
                # first one wedged the daemon permanently -- the process stayed
                # alive, so systemd never restarted it, and the hub sat there
                # refusing to connect while looking healthy. So retry it, with
                # the usual bounded backoff, and only believe the conflict once
                # the server has said it repeatedly.
                if "already in use" in str(exc):
                    self.nick_conflicts += 1
                    if self.nick_conflicts >= self.nick_attempts:
                        self.fatal = (
                            f"nick {self.nick!r} still in use after "
                            f"{self.nick_conflicts} attempts: {exc}")
                        break
                else:
                    self.disconnects += 1
                self._close()
            except OSError as exc:
                self.last_error = str(exc)
                self.disconnects += 1
                self._close()

            if self._stop.is_set() or self.fatal:
                break

            # Capped backoff: a server that is down for a while must not turn
            # into a reconnect storm against its log.
            self._stop.wait(delay)
            delay = min(delay * 2, self.max_delay)
        self._close()

    def _session(self) -> None:
        """One connected lifetime: register, then serve until it breaks."""
        client = IRCClient(host=self.host, port=self.port, nick=self.nick,
                           channels=self.channels, on_message=self._on_wire,
                           realname=f"{self.nick} (mem20ircz)",
                           timeout=self.read_timeout)
        self._client = client
        self._last_rx = time.time()
        self._last_ping = time.time()
        client.connect()
        self.connected.set()

        while not self._stop.is_set():
            msg = client.read_message()
            if msg is not None:
                self._last_rx = time.time()
                client.dispatch(msg)
                continue
            # read_message returned None: a socket timeout, not a message.
            self._heartbeat()

    def _heartbeat(self) -> None:
        """Keep the connection provably alive.

        A TCP socket on a quiet channel can be dropped by a middlebox with no
        error at all, and the next write fails much later with a confusing
        error. So: ping on a timer, and declare the socket dead if nothing has
        come *back* for ``dead_after``. A dead socket is reconnected here
        rather than discovered by an agent mid-conversation.
        """
        client = self._client
        if client is None:
            return
        now = time.time()
        if now - self._last_rx > self.dead_after:
            self.last_error = "no traffic from server; recycling socket"
            self._close()
            raise IRCError("connection stale")
        if now - self._last_ping >= self.ping_every:
            self._last_ping = now
            try:
                client.send_raw(f"PING :mem20ircz-{self.nick}")
            except (OSError, IRCError):
                self._close()
                raise IRCError("write failed during heartbeat")

    # ----------------------------------------------------------------- wire
    def _on_wire(self, msg) -> None:
        """The single point where a protocol line is judged.

        Roster bookkeeping happens for every line regardless of verdict, which
        is the whole reason ``who`` can work while the roster events themselves
        are treated as noise.
        """
        apply_roster(self.rosters, msg)

        # Readiness is signalled by the roster arriving for a channel we asked
        # for -- either our own JOIN echo or the NAMES reply. That is the point
        # at which the server will accept a PRIVMSG from us and relay other
        # people's, which is what "ready" has to mean to be worth anything.
        if not self.ready.is_set():
            if ((msg.command == "JOIN"
                 and (msg.nick or "").lower() == self.nick.lower())
                    or (msg.command in ("353", "366")
                        and numeric_channel(msg) in self.channels)):
                self.ready.set()

        verdict = self.meter.record(classify(msg, my_nicks=(self.nick,)))
        if not verdict.keep:
            return
        self.buffer.append(ts=time.time(), nick=msg.nick, target=msg.target,
                           text=msg.text,
                           mine=(msg.nick or "").lower() == self.nick.lower())

    # ------------------------------------------------------------------ api
    def say(self, text: str, target: Optional[str] = None) -> None:
        client = self._client
        if client is None or not self.connected.is_set():
            raise IRCError(f"{self.nick} is not connected")
        client.say(target or self.channels[0], text)

    def status(self) -> dict:
        return {
            "nick": self.nick,
            "connected": self.connected.is_set(),
            "ready": self.ready.is_set(),
            "channels": list(self.channels),
            "disconnects": self.disconnects,
            "last_error": self.last_error,
            "fatal": self.fatal,
            "buffered": len(self.buffer._items),
            "latest_seq": self.buffer.latest_seq,
            "noise": self.meter.report(),
        }

    def who(self) -> list:
        names: set = set()
        for members in self.rosters.values():
            names |= set(members)
        return sorted(n for n in names if n)


class Hub:
    """Owns every connection and routes agent requests to the right one."""

    def __init__(self, *, host: str = "127.0.0.1", port: int = 6667,
                 channels=("#mem20",), default_nick: str = "mem20agents",
                 buffer_size: int = DEFAULT_BUFFER) -> None:
        self.host = host
        self.port = port
        self.channels = tuple(channels)
        self.default_nick = default_nick
        self.buffer_size = buffer_size
        self.connections: dict = {}
        self._lock = threading.Lock()

    def _new_connection(self, nick: str) -> Connection:
        return Connection(host=self.host, port=self.port, nick=nick,
                          channels=self.channels,
                          buffer_size=self.buffer_size)

    def join(self, nick: str, wait: float = 5.0) -> Connection:
        """Return the connection for ``nick``, opening it if needed.

        Re-joining an existing nick returns the live connection rather than
        starting a second one, so an agent that calls ``join`` on every turn
        does not slowly accumulate duplicate connections and duplicate messages.

        Waits a bounded moment for the channel roster to arrive, so the caller
        gets an honest answer. Returning the instant the socket is up made
        ``join`` report ``connected=False`` on a perfectly healthy connection
        and tempted a caller into speaking before it could be heard. Bounded,
        because a join must never be able to hang an agent turn.
        """
        with self._lock:
            conn = self.connections.get(nick)
            if conn is None:
                conn = self._new_connection(nick)
                self.connections[nick] = conn
        conn.start()
        if wait:
            conn.ready.wait(timeout=max(0.0, wait))
        return conn

    def get(self, nick: Optional[str] = None) -> Connection:
        name = nick or self.default_nick
        conn = self.connections.get(name)
        if conn is None:
            conn = self.join(name)
        return conn

    def stop(self) -> None:
        with self._lock:
            conns = list(self.connections.values())
            self.connections.clear()
        for conn in conns:
            conn.stop()

    # ------------------------------------------------------------- requests
    def status(self) -> dict:
        return {
            "host": self.host,
            "port": self.port,
            "channels": list(self.channels),
            "default_nick": self.default_nick,
            "connections": {n: c.status() for n, c in self.connections.items()},
        }

    def read(self, since: int = 0, limit: int = 50,
             nick: Optional[str] = None) -> dict:
        conn = self.get(nick)
        messages, truncated, latest = conn.buffer.since(since, limit)
        return {
            "nick": conn.nick,
            "connected": conn.connected.is_set(),
            "messages": messages,
            "count": len(messages),
            "latest_seq": latest,
            "oldest_seq": conn.buffer.oldest_seq,
            "truncated": truncated,
            "disconnects": conn.disconnects,
        }

    def say(self, text: str, nick: Optional[str] = None,
            target: Optional[str] = None) -> dict:
        conn = self.get(nick)
        conn.say(text, target=target)
        return {"nick": conn.nick, "sent": text}

    def who(self, nick: Optional[str] = None) -> dict:
        conn = self.get(nick)
        return {"nick": conn.nick, "nicks": conn.who()}