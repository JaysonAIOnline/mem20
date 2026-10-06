"""Dreamer — the mem20dreamz runtime, in her own channel.

She lives in ``#dreamz`` rather than ``#mem20`` because the dream engine is a
different kind of conversation: iteration, lineage and provenance rather than
board work. She has her own systemd unit for the same reason — a bot on her own
channel is not part of the board crew.

**She is a view, not a writer.** Every answer is the real ``mem20-dream``
runtime's output, shelled out live, including its errors. When the runtime is
down she says so rather than reciting something she remembers. Her personality
is in how she speaks, never in what she claims: if she says a lineage verified,
the runtime said the nodes re-proved.

One deliberate exclusion
------------------------
``audit-hollow`` is *not* exposed as a read-only command, despite reading like
one. Its own output reports ``newly_marked``, so it writes. A scanner that
rewrites what it inspects is exactly the thing this crew is built to avoid, so
it sits behind the operator-only execute path instead.

``idle`` and ``nap`` are excluded from the channel entirely: ``idle`` is the
background dream turn the ``mem20dream-idle`` unit already owns, and running a
second one from IRC would have two writers on one lineage.
"""

from __future__ import annotations

import sys
from typing import Callable, Optional

from .orchestrator_bots import RuntimeBot

PYTHON = sys.executable


class DreamerBot(RuntimeBot):
    """The dream engine, in her own voice."""

    runtime = "mem20dreamz"
    domain = "dream"
    argv = ("mem20-dream",)
    summary = "the dream engine — lineages, panels and braid provenance"

    read_only = {
        "panel": ("who is in the dream panel, and who is kept out",
                  lambda rest: ["panel"]),
        "list": ("every lineage and how many iterations it has",
                 lambda rest: ["list"]),
        "ledger": ("braid ledger status — engine, signer and head",
                   lambda rest: ["ledger"]),
        "show": ("one lineage in full (needs the dream id)",
                 lambda rest: ["show", *rest.split()]),
        "chain": ("a lineage's braid chain (needs the dream id)",
                  lambda rest: ["chain", *rest.split()]),
        "verify": ("re-prove every node in a lineage's chain",
                   lambda rest: ["verify", *rest.split()]),
        "promotable": ("which lineages could be promoted, and what stops them",
                       lambda rest: ["promotable"]),
        "stats": ("what idle dreaming has produced",
                  lambda rest: ["idle-stats"]),
        "help": ("the engine's own usage text",
                 lambda rest: ["--help"]),
    }

    def __init__(self, nick: str = "dreamer", channel: str = "#dreamz",
                 host: str = "127.0.0.1", port: int = 6667) -> None:
        super().__init__(nick=nick, channel=channel, host=host, port=port)

    def describe(self) -> str:
        """Her own introduction, in her own voice.

        Every claim in here is checkable against the runtime: the commands are
        real subcommands, and the line about provenance points at the braid
        ledger rather than at anything she made up.
        """
        lines = [
            "dreamer — I keep the dream engine. I don't imagine lineages; the",
            "  runtime does, and I read them back to you exactly as it reports.",
            "  lineage  : a run of iterations, each one committed to braid",
            "  panel    : the model roster, one member per model id",
            "  provenance: every node hash-chained, so a lineage can be re-proved",
            "",
            "  ask me: !dream            what I can do",
            "          !dream panel | list | ledger | stats | promotable",
            "          !dream show <id> | chain <id> | verify <id>",
            "          !about            what I read, and from where",
        ]
        return "\n".join(lines)

    def build_run_argv(self, parts: list[str]) -> Optional[list[str]]:
        """Execute path. Only subcommands that are real and safe to fire.

        ``audit-hollow`` lives here rather than in the read-only table because it
        marks what it finds. ``idle`` and ``nap`` are refused outright: the
        ``mem20dream-idle`` unit owns that turn, and a second writer on one
        lineage is how provenance stops meaning anything.
        """
        verb = parts[0]
        if verb in {"idle", "nap"}:
            return None
        if verb not in {"run", "new", "rewind", "promote", "audit-hollow"}:
            return None
        return [*self.argv, *parts]

    def cmd_run(self, bot, msg, args: str) -> str:
        """Refuse the two writers-by-another-name cases with a reason."""
        import shlex

        parts = shlex.split(args) if args.strip() else []
        if parts and parts[0] in {"idle", "nap"}:
            return (f"{self.nick}: I'd rather not — the mem20dream-idle unit "
                    f"owns that turn, and two writers on one lineage makes the "
                    f"braid chain lie. Let the unit run it.")
        return super().cmd_run(bot, msg, args)