"""Wire-level noise filter.

The whole reason this module exists: an agent pays tokens for every line it
reads. Measured against the live ``#mem20`` room on this box, a fresh connection
received 24 raw protocol lines and 3 real messages — 87.5% waste — and 21 of
those 24 arrived in the connect burst, before anybody had said anything.

So the filter runs *at the wire*, inside the daemon, before anything reaches a
ring buffer. Swallowed lines are never buffered, so there is no code path by
which server noise can reach a model even if an agent asks for everything.

One distinction carries the design. The daemon still needs to know who is in the
room, so the roster events (JOIN/PART/QUIT/NICK) and the NAMES reply (353) are
*consumed* here to maintain internal state and then dropped. They are swallowed
from the agent's stream, not from the daemon's awareness. Collapsing those two
ideas -- "throw it away" versus "I don't forward it" -- is how a client ends up
either wasting tokens or being unable to answer ``who``.

Text is never rewritten. An agent that reads a message gets the bytes the
sender's client put on the wire, so what the agent sees is what was said.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable

# Numerics the daemon interprets for its own bookkeeping rather than forwarding.
# Compared as text: Message.command is always a string.
NAMES_REPLY = "353"

#: MOTD burst. The single largest block of waste on connect. Strings, not ints:
#: an int set matches nothing here, which is the bug this module shipped with
#: until a test fed it a real parsed line.
MOTD_NUMERICS = frozenset({"372", "375", "376", "422"})

#: Roster movement: who is here, tracked internally for ``who``.
ROSTER_COMMANDS = frozenset({"JOIN", "PART", "QUIT", "NICK"})

#: Channel and mode administration. Never conversational.
ADMIN_COMMANDS = frozenset({"MODE", "KICK", "INVITE", "TOPIC", "WALLOPS",
                            "AWAY"})

#: Protocol housekeeping. The client already answers PING itself; these must
#: never surface as content.
PROTOCOL_COMMANDS = frozenset({"PING", "PONG", "ERROR", "AWAY"})

KEEP = "keep"


@dataclass(frozen=True)
class Verdict:
    """What the filter decided about one protocol line."""

    keep: bool
    reason: str

    def __bool__(self) -> bool:  # pragma: no cover - trivial
        return self.keep


def _is_ctcp_noise(text: str) -> bool:
    """True for a CTCP query rather than a CTCP ACTION.

    ``\\x01ACTION waves\\x01`` is something a person did and is worth reading.
    ``\\x01VERSION\\x01`` is a client capability probe addressed to a machine,
    and the reply is never wanted. Only the non-ACTION half is noise.
    """
    if not text.startswith("\x01"):
        return False
    return not text.upper().startswith("\x01ACTION")


def classify(msg, my_nicks: Iterable[str] = ()) -> Verdict:
    """Decide whether one parsed IRC line is worth an agent's tokens.

    :param msg: a :class:`mem20botz.irc.Message`.
    :param my_nicks: the nicks this connection answers to, used to tell a
        direct message apart from a broadcast to somebody else.
    """
    command = msg.command
    mine = {n.lower() for n in my_nicks if n}

    if command.isdigit():
        # Numerics are the server talking to the client, never a person.
        if command == NAMES_REPLY:
            return Verdict(False, "numeric.names")
        if command in MOTD_NUMERICS:
            return Verdict(False, "numeric.motd")
        return Verdict(False, "numeric.other")

    if command == "PRIVMSG":
        if not msg.text.strip():
            return Verdict(False, "empty")
        if _is_ctcp_noise(msg.text):
            return Verdict(False, "ctcp")
        if msg.is_channel:
            return Verdict(True, "channel")
        target = msg.target.lower()
        if target in mine:
            return Verdict(True, "direct")
        # A PRIVMSG to some third party leaked into our view; it is not ours.
        return Verdict(False, "not-for-us")

    if command == "NOTICE":
        return Verdict(False, "notice")

    if command in ROSTER_COMMANDS:
        return Verdict(False, "roster")

    if command in ADMIN_COMMANDS or command in PROTOCOL_COMMANDS:
        return Verdict(False, "admin" if command in ADMIN_COMMANDS
                       else "protocol")

    return Verdict(False, "other")


def numeric_channel(msg) -> str:
    """The channel a numeric refers to.

    On a numeric, ``params[0]`` is the *recipient nick*, not the channel --
    ``:server 353 mynick = #room :names`` puts the room in ``params[2]``. Reading
    ``target`` instead is the trap that made ``who`` silently return nothing,
    because the roster was being filed under the connection's own nick.
    """
    for param in reversed(msg.params):
        if param[:1] in "#&+!":
            return param
    return ""


def apply_roster(rosters: dict, msg) -> None:
    """Fold one protocol line into the per-channel roster, in place.

    ``rosters`` maps channel name to a set of nicks. PART removes from the one
    channel being left; QUIT and NICK removal apply everywhere, because a nick
    that quits or renames leaves every room at once. Tracking per channel is
    what keeps ``who`` honest when the hub is in more than one room -- a single
    flat set would report someone as present in a channel they left.

    This is the daemon consuming roster events for its own state. The same
    lines are still classified as noise, so they are never buffered and never
    reach an agent.
    """
    command = msg.command

    if command == "JOIN":
        channel = msg.target
        if channel and msg.nick:
            rosters.setdefault(channel, set()).add(msg.nick)

    elif command == "PART":
        channel = msg.target
        if channel and msg.nick:
            rosters.setdefault(channel, set()).discard(msg.nick)

    elif command == "QUIT":
        if msg.nick:
            for members in rosters.values():
                members.discard(msg.nick)

    elif command == "NICK":
        # The *old* nick is in the prefix; the new one is the parameter. Reading
        # the new nick out of the prefix yields "u@h" and renames the roster to
        # garbage.
        old = msg.nick
        new = msg.params[0] if msg.params else ""
        if old and new:
            for members in rosters.values():
                if old in members:
                    members.discard(old)
                    members.add(new)

    elif command == NAMES_REPLY:
        channel = numeric_channel(msg)
        if not channel:
            return
        # Trailing "=channel" / "@channel" markers are not nicks.
        names = {t.lstrip("@%+~&") for t in msg.text.split()
                 if t and not t.startswith("=") and not t.startswith("#")}
        rosters[channel] = {n for n in names if n}


class NoiseMeter:
    """Counts what was swallowed, so the saving is evidence rather than a claim.

    Every verdict passes through :meth:`record`. ``status`` reports the totals,
    which is how a claim like "87.5% of the wire is noise" becomes something a
    caller can check instead of something it has to believe.
    """

    def __init__(self) -> None:
        self.seen = 0
        self.kept = 0
        self.swallowed = 0
        self.by_reason: Counter = Counter()

    def record(self, verdict: Verdict) -> Verdict:
        self.seen += 1
        if verdict.keep:
            self.kept += 1
        else:
            self.swallowed += 1
            self.by_reason[verdict.reason] += 1
        return verdict

    @property
    def waste_ratio(self) -> float:
        """Fraction of wire lines that never became content."""
        if not self.seen:
            return 0.0
        return self.swallowed / self.seen

    def report(self) -> dict:
        return {
            "lines_seen": self.seen,
            "kept": self.kept,
            "swallowed": self.swallowed,
            "waste_ratio": round(self.waste_ratio, 4),
            "by_reason": dict(self.by_reason),
        }

    def reset(self) -> None:
        self.seen = 0
        self.kept = 0
        self.swallowed = 0
        self.by_reason.clear()