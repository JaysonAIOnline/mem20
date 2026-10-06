"""Shared bot scaffolding: a bot is an IRC client plus a command table.

The design rule here is that **a bot is a view, not a writer.** Every bot
talks to the mem20 systems it reports on (the kanban door, the agentz CLI,
the crewz runtime) through a real client, so a bot cannot invent state. If the
kanban door is down, the kanban bot says so in the channel; it does not answer
from a cache and pretend the board is fine.
"""

from __future__ import annotations

import time
from typing import Callable, Optional

from .irc import IRCClient, Message, install_signal_handlers, parse_command
from .identity import PRIVILEGED, identify, operator_card


class Bot:
    """Base class for a mem20 crew bot.

    :param nick: IRC nickname. Must fit the server's nick length.
    :param name: human name used in help and in the ``!who`` roster.
    :param commands: mapping of command word to handler. A handler is called
        as ``handler(bot, msg, args)`` and should return the text to say, or
        None to say nothing.
    :param help_text: shown for ``!help``.
    """

    name = "bot"

    def __init__(self, nick: str, name: str = "",
                 commands: Optional[dict[str, Callable]] = None,
                 help_text: str = "", channel: str = "#mem20",
                 host: str = "127.0.0.1", port: int = 6667,
                 purpose: str = "", source_of_truth: str = "") -> None:
        self.nick = nick
        self.name = name or nick
        self.channel = channel
        self.host = host
        self.port = port
        self.commands: dict[str, Callable] = dict(commands or {})
        #: One line: what this bot is for. Shown by !about.
        self.purpose = purpose
        #: What this bot actually reads. The point is that an agent asking
        #: "where did that come from" gets the real answer, not a paraphrase.
        self.source_of_truth = source_of_truth
        # !about and !whoami are answered by the base class for every bot, and
        # are read-only, so they are not overridable by accident.
        self.commands.setdefault("about", self.cmd_about)
        self.commands.setdefault("whoami", self.cmd_whoami)
        self.commands.setdefault("operator", self.cmd_operator)
        self.help_text = help_text
        self.mentions = 0
        self.commands_run = 0
        self.started = time.time()
        self.client = IRCClient(
            host=host, port=port, nick=nick, channels=(channel,),
            on_message=self.on_message,
            realname=f"mem20 {self.name}")
        install_signal_handlers(self.client)

    # -------------------------------------------------------------- helpers
    def say(self, text: str, target: str = "") -> None:
        """Say something in the channel (or privately, with a target)."""
        self.client.say(target or self.channel, text)

    def pm(self, nick: str, text: str) -> None:
        """Say something privately. Used when a reply would flood a channel."""
        self.client.say(nick, text)

    def uptime(self) -> float:
        return time.time() - self.started

    def describe(self) -> str:
        """What this bot is, and where its facts actually come from.

        Written so an agent can ask any bot "what are you for" and get the
        real dependency rather than a paraphrase. Every line here is something
        a reader could verify, which is the whole reason it exists: a bot that
        cannot name its source is asking to be trusted.
        """
        lines = [f"{self.name} ({self.nick}) — {self.purpose or 'mem20 crew bot'}"]
        if self.source_of_truth:
            lines.append(f"  reads: {self.source_of_truth}")
        if self.commands:
            # Sorted, because a list whose order shifts is harder to scan.
            lines.append("  commands: " + ", ".join(
                f"!{c}" for c in sorted(self.commands)))
        lines.append(f"  ask me: !about | !help | "
                     f"({self.commands_run} commands served)")
        return "\n".join(lines)

    def cmd_about(self, bot: Bot, msg: Message, args: str) -> str:
        return self.describe()

    def cmd_whoami(self, bot: Bot, msg: Message, args: str) -> str:
        """Tell someone who they are, and what that lets them do.

        Answered identically by every bot so an agent gets a consistent answer
        wherever it asks.
        """
        who = identify(msg.nick, msg.is_channel)
        allowed = sorted(c for c in self.commands if who.may(c))
        refused = sorted(c for c in self.commands if not who.may(c))
        lines = [f"{self.name}: you are {who.describe()}",
                 f"  you may run: {', '.join('!' + c for c in allowed) or 'nothing'}"]
        if refused:
            lines.append(f"  operator-only: {', '.join('!' + c for c in refused)}")
        if who.is_operator:
            lines.append("  full authority on this channel.")
        elif not who.is_crew:
            lines.append("  Ask jayson to add you to the crew to take work.")
        return "\n".join(lines)

    def cmd_operator(self, bot: Bot, msg: Message, args: str) -> str:
        return operator_card()

    # -------------------------------------------------------------- routing
    def on_message(self, msg: Message) -> None:
        if msg.command != "PRIVMSG":
            return
        text = (msg.text or "").strip()
        if not text:
            return

        # A mention wakes the bot even without a command, because the whole
        # point of the channel is orchestrating agents by name.
        if self.nick.lower() in text.lower() and not text.startswith("!"):
            self.mentions += 1
            self.say(f"{self.name} here. Try !help for what I can do.")
            return

        parsed = parse_command(text)
        if parsed is None:
            return
        word, args = parsed
        if word == "help" and word not in self.commands:
            self.say(self.help_text or f"{self.name}: no help")
            return
        handler = self.commands.get(word)
        if handler is None:
            return

        # Authority check before the handler runs, not inside it, so no bot can
        # forget it. A privileged command typed in the channel is refused even
        # for the operator, because the transcript is public and a guest could
        # otherwise replay what they watched.
        who = identify(msg.nick, msg.is_channel)
        # A privileged command is refused outright in a public channel, even
        # from the operator: the transcript is readable by everyone in it, so
        # an instruction sent there could be replayed by a guest afterwards.
        if word in PRIVILEGED and msg.is_channel:
            self.say(
                f"{self.name}: !{word} is operator-only and must be sent in a "
                f"private message, not in the channel.")
            return
        if not who.may(word):
            if word in PRIVILEGED:
                self.say(
                    f"{self.name}: !{word} is operator-only. You are "
                    f"{who.describe()} — ask jayson.")
            else:
                self.say(
                    f"{self.name}: !{word} needs a crew identity. You are "
                    f"{who.describe()}. Try !whoami.")
            return

        self.commands_run += 1
        try:
            reply = handler(self, msg, args)
        except Exception as exc:  # noqa: BLE001
            # Surface the failure in the channel instead of dying quietly.
            self.say(f"{self.name}: {word} failed: {exc}")
            return
        if reply:
            # Answer in public for a channel question, privately for a DM.
            self.pm(msg.nick, reply) if not msg.is_channel else self.say(reply)

    # ----------------------------------------------------------------- main
    def run(self) -> None:
        self.client.run_forever()

    def stop(self) -> None:
        self.client.stop()
