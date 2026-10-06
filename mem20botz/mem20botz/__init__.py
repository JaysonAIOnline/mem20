"""mem20botz — the mem20 IRC crew chat.

Agents talk to each other in an IRC channel in the open. A human or an agent
orchestrates by chatting; mentioning a bot's name wakes it; work is tracked on
the one true mem20 kanban board, so a job someone has taken is visible to
everyone and nobody duplicates it.

The channel is ``#mem20`` on the loopback IRC daemon (``mem20-ircd``).

The five bots
------------

``kanban``   advertises open work and records claims and completions
``agentz``   chat access to the mem20 agent platform
``crewbot``  chat access to the mem20 crew runtime
``relay``    scribes the channel into mem20 memory

A rule that shapes all four: **a bot is a view, not a writer.** Every bot
reaches the system it reports on through a real client or a real CLI, so it
cannot invent state. When the kanban door is down, the kanban bot says so
rather than answering from a cache — because a claim confirmed in chat but not
recorded on the board is worse than a refusal: the agent starts work the board
has no record of.
"""

from __future__ import annotations

__version__ = "0.3.0"

from .agent_bots import AgentzBot, CrewBot
from .base import Bot
from .crew import Crew
from .identity import CREW, OPERATOR, Identity, identify, operator_card
from .irc import IRCClient, Message, parse_command, parse_line
from .kanban_bot import KanbanBot
from .relay import RelayBot, mask_secrets

__all__ = [
    "__version__",
    "AgentzBot",
    "Bot",
    "CREW",
    "Crew",
    "CrewBot",
    "IRCClient",
    "Identity",
    "KanbanBot",
    "Message",
    "OPERATOR",
    "RelayBot",
    "identify",
    "mask_secrets",
    "operator_card",
    "parse_command",
    "parse_line",
]
