"""Who is in the channel, and what that means for a bot.

A crew that cannot say who it is talking to will happily answer a stranger the
same way it answers the operator. So identity is a first-class concept here
rather than an afterthought bolted onto the IRC nick.

The hierarchy is deliberate and small:

* **operator** — Jayson. Full command rights, including anything that could
  cost money, spend a resource, or reach outside the box.
* **crew** — a registered mem20 agent. May take and report work; may not run
  privileged commands.
* **guest** — anyone else. Read-only. The channel is watchable by design, so
  this is the default and not a special case.

A bot is a *view* of state, so identity here is about **authority over
commands**, not about pretending to authenticate a human. IRC on loopback is
trusted transport, not proof of identity: the nick is a claim, and the
authority it grants is scoped accordingly. A bot that treated an IRC nick as
proof would be repeating the mistake that made the four-kanban drift possible
in the first place — trusting a label over the thing the label points at.

`PRIVMSG`-only escalation is deliberate. A command typed in the channel is
visible to everyone, so a guest could otherwise watch an operator run a
privileged command and then replay it. Requiring a DM keeps privileged
instructions out of the shared transcript.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

#: The operator. Everything else is measured against this.
OPERATOR = "jayson"

#: Nicks that are the estate's own agents. A crew member, not a guest.
CREW = frozenset({
    "kanban", "agentz", "crewbot", "relay",
    "orca", "graph", "swarm", "adk", "sdk",
    "muse", "bigpickle", "spacebunny", "nemotron3ultra", "opencode",
})

#: Commands no one but the operator may run, whatever their role.
PRIVILEGED = frozenset({
    "run", "crew", "shutdown", "restart", "exec", "shell", "deploy", "spend",
    # One execute verb per orchestrator bot. Listing agents or checking
    # health stays open to crew; actually running a workflow does not.
    "orca_run", "graph_run", "swarm_run", "adk_run", "sdk_run", "dream_run",
})

#: Read-only self-description. Open to everyone, including a stranger.
#:
#: This is the counterweight to guest-lockout: the channel is watchable by
#: design, and the first thing a newcomer needs is to ask a bot what it is and
#: where it reads from. Locking that behind crew status would leave a stranger
#: unable to find out what the crew even does.
READ_ONLY = frozenset({
    "about", "whoami", "operator", "help", "status", "jobs", "boards",
    "board", "who", "peers", "crewhelp", "relaystatus", "profiles", "sessions",
    "skills", "model",
})


@dataclass
class Identity:
    """What a bot believes about who is talking, and what they may do."""

    nick: str
    role: str = "guest"
    reason: str = ""

    @property
    def is_operator(self) -> bool:
        return self.role == "operator"

    @property
    def is_crew(self) -> bool:
        return self.role in ("operator", "crew")

    def may(self, command: str) -> bool:
        """May this identity run ``command``?"""
        if command in PRIVILEGED:
            return self.is_operator
        if command in READ_ONLY:
            # Read-only self-description is open to all, so a newcomer can
            # find out what this crew is without already being in it.
            return True
        # Work-taking and reporting are the point of the channel, so any
        # identified crew member may do them; a guest may not, because a
        # stranger should not be able to claim the operator's board.
        return self.is_crew

    def describe(self) -> str:
        return f"{self.nick} ({self.role}{': ' + self.reason if self.reason else ''})"


#: The operator's own description, so a bot can answer "who is Jayson"
#: without a database lookup and without inventing anything.
OPERATOR_PROFILE = {
    "name": "Jayson",
    "nick": OPERATOR,
    "role": "operator and owner of the mem20 estate",
    "works": [
        "the mem20 control plane and the estate of mem20*z organs",
        "agent crews: Muse, Nemotron 3 Ultra, Big Pickle, Space Bunny",
        "the JAYSONai network this board tracks",
    ],
    "how_to_address": "Jayson",
    "not": "not a bot; a person, addressed directly, never as @jayson-bot",
}


def identify(nick: str, is_channel: bool = False) -> Identity:
    """Decide who is speaking.

    :param nick: the IRC nick.
    :param is_channel: whether the message was public. A privileged command
        sent publicly is refused regardless of role, so an operator's
        privileged instruction never sits in the shared transcript to be
        replayed by a guest.
    """
    n = (nick or "").strip()
    low = n.lower()
    if low == OPERATOR:
        return Identity(n, "operator", "the estate owner")
    if low in CREW:
        return Identity(n, "crew", "registered mem20 agent")
    if is_channel:
        return Identity(n, "guest", "unrecognised nick, public channel")
    return Identity(n, "guest", "unrecognised nick")


def operator_card() -> str:
    """The operator's profile, for ``!whoami`` / ``!operator``."""
    p = OPERATOR_PROFILE
    lines = [f"{p['name']} — {p['role']}",
             f"  nick on IRC: {p['nick']} ({p['not']})",
             "  works on:"]
    lines += [f"    - {w}" for w in p["works"]]
    lines.append(f"  address as: {p['how_to_address']}")
    return "\n".join(lines)
