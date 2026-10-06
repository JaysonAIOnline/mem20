"""Tests for the per-orchestrator IRC bots.

The properties that matter:

* **Command words are unique across the whole crew.** Every bot sees every
  message and dispatches on its own table, so two bots sharing a command word
  means typing it produces two contradictory answers. That is not hypothetical:
  ``!status`` was defined by both agentz and kanban until this suite existed.
* **Execution is operator-only.** Anything that runs a workflow lives under a
  ``<domain>_run`` word that must appear in ``PRIVILEGED``.
* **Nothing that blocks forever is ever run.** ``serve`` would wedge the bot's
  handler and the channel would stop getting answers.
* **A read-only command really answers.** Asserted against the real runtimes,
  because a mocked runtime only proves the mock agrees with itself.
"""

from __future__ import annotations

import shlex
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mem20botz.crew import Crew  # noqa: E402
from mem20botz.identity import CREW, PRIVILEGED, identify  # noqa: E402
from mem20botz.irc import parse_line  # noqa: E402
from mem20botz.orchestrator_bots import (  # noqa: E402
    ORCHESTRATOR_BOTS,
    AdkBot,
    GraphBot,
    OrcaBot,
    RuntimeBot,
    SdkBot,
    SwarmBot,
)

CHANNEL_MSG = ":jayson!j@localhost PRIVMSG #mem20 :{text}"
PRIVATE_MSG = ":jayson!j@localhost PRIVMSG agentz :{text}"


def recorded(bot, text, private=False):
    """Feed one message to a bot and capture what it would say."""
    line = PRIVATE_MSG if private else CHANNEL_MSG
    said: list[str] = []
    bot.client.registered = True
    bot.say = lambda t, target="": said.append(t)
    bot.pm = lambda nick, t: said.append(t)
    bot.on_message(parse_line(line.format(text=text)))
    return "\n".join(said)


def built(nick):
    """A bot that does not open a socket, for argv-building tests."""
    return {
        "orca": OrcaBot(nick="orca"),
        "graph": GraphBot(nick="graph"),
        "swarm": SwarmBot(nick="swarm"),
        "adk": AdkBot(nick="adk"),
        "sdk": SdkBot(nick="sdk"),
    }[nick]


class TestNoTwoBotsShareACommandWord(unittest.TestCase):
    """The !status collision, guarded."""

    #: about/whoami/operator are answered by the base class for every bot on
    #: purpose, so they are the one legitimate overlap. Everything else must be
    #: unique or typing it produces two contradictory answers.
    UNIVERSAL = {"about", "whoami", "operator"}

    def test_command_words_are_unique_across_the_whole_crew(self):
        owner: dict[str, str] = {}
        clashes = []
        for bot in Crew(start_relay=True).bots:
            for word in bot.commands:
                if word in self.UNIVERSAL:
                    continue
                if word in owner:
                    clashes.append(f"{word!r}: {owner[word]} and {bot.nick}")
                owner[word] = bot.nick
        self.assertEqual(clashes, [], "ambiguous command words: " + "; ".join(clashes))

    def test_the_five_orchestrator_domains_are_all_distinct(self):
        domains = [cls.domain for cls in ORCHESTRATOR_BOTS]
        self.assertEqual(len(domains), len(set(domains)))
        self.assertEqual(sorted(domains), ["adk", "graph", "orca", "sdk", "swarm"])


class TestExecutionIsOperatorOnly(unittest.TestCase):
    def test_every_run_word_is_privileged(self):
        for cls in ORCHESTRATOR_BOTS:
            self.assertIn(f"{cls.domain}_run", PRIVILEGED, cls.domain)

    def test_no_orchestrator_run_word_is_usable_in_the_channel(self):
        for cls in ORCHESTRATOR_BOTS:
            out = recorded(built(cls.domain), f"!{cls.domain}_run thing.yaml")
            self.assertIn("operator-only", out, cls.domain)
            self.assertNotIn("exited", out, cls.domain)

    def test_a_read_only_command_is_not_refused(self):
        """Read-only stays open to crew, otherwise the bots are pointless."""
        out = recorded(built("orca"), "!orca types")
        self.assertNotIn("operator-only", out)


class TestBlockingCommandsAreRefused(unittest.TestCase):
    """Two gates, and the first one is the base class.

    In the channel the operator-only gate refuses before the handler is even
    reached. The blocking gate is the second line of defence, and it has to hold
    on the path where the handler *does* run: an operator DM.
    """

    def test_channel_refuses_before_the_handler_runs(self):
        for word in ("serve", "daemon", "watch", "shell"):
            out = recorded(built("graph"), f"!graph_run {word}")
            self.assertIn("operator-only", out, word)

    def test_serve_is_refused_even_in_an_operator_dm(self):
        """This is the real test: only a DM reaches cmd_run at all."""
        for word in ("serve", "daemon", "watch", "shell"):
            out = recorded(built("graph"), f"!graph_run {word}", private=True)
            self.assertIn("refusing to run", out, word)

    def test_a_run_the_operator_did_ask_for_is_allowed_through(self):
        """The gate must refuse only blocking commands, not everything."""
        out = recorded(built("orca"), "!orca_run flow.yaml", private=True)
        self.assertNotIn("refusing to run", out)


class TestHelpAndSelfDescription(unittest.TestCase):
    def test_bare_domain_word_lists_its_read_only_commands(self):
        for cls in ORCHESTRATOR_BOTS:
            bot = built(cls.domain)
            out = recorded(bot, f"!{cls.domain}")
            self.assertIn(cls.runtime, out, cls.domain)
            for name in cls.read_only:
                self.assertIn(name, out, f"{cls.domain}/{name}")

    def test_help_names_the_operator_only_execute_path(self):
        for cls in ORCHESTRATOR_BOTS:
            out = recorded(built(cls.domain), f"!{cls.domain}")
            self.assertIn(f"!{cls.domain}_run", out, cls.domain)

    def test_every_bot_describes_itself_and_names_its_source(self):
        for cls in ORCHESTRATOR_BOTS:
            d = built(cls.domain).describe()
            self.assertIn(cls.domain, d)
            self.assertIn("reads:", d, cls.domain)
            self.assertIn(cls.runtime, d, cls.domain)

    def test_unknown_subcommand_refuses_without_running_anything(self):
        out = recorded(built("orca"), "!orca definitely-not-a-command")
        self.assertIn("no read-only command", out)
        self.assertNotIn("exited", out)

    def test_run_without_args_asks_what_to_execute(self):
        out = recorded(built("orca"), "!orca_run", private=True)
        self.assertIn("what to execute", out)


class TestArgvBuilding(unittest.TestCase):
    """What each bot would actually execute, checked without executing it."""

    def test_orca_read_only_types(self):
        _, build = OrcaBot.read_only["types"]
        self.assertEqual(build(""), ["--list-types"])

    def test_orca_run_requires_a_yaml(self):
        bot = built("orca")
        self.assertIsNone(bot.build_run_argv(["notes.txt"]))
        self.assertEqual(bot.build_run_argv(["flow.yaml"])[-2:],
                         ["flow.yaml", "--outputs"])

    def test_swarm_run_requires_items_and_template(self):
        bot = built("swarm")
        # kimiz's real shape is --items ITEMS --template TEMPLATE, both flags.
        self.assertIsNone(bot.build_run_argv(["a,b"]))
        self.assertIsNone(bot.build_run_argv(["--items", "a,b"]))
        argv = bot.build_run_argv(["--items", "a,b", "--template", "t.md"])
        self.assertEqual(argv[-4:], ["--items", "a,b", "--template", "t.md"])

    def test_adk_run_targets_the_run_subcommand(self):
        argv = built("adk").build_run_argv(["chat"])
        self.assertEqual(argv[-3:], ["mem20googlez", "run", "chat"])


class TestAgainstTheRealRuntimes(unittest.TestCase):
    """Bounded, read-only, and real. A mocked runtime proves nothing."""

    def test_orca_types_answers_from_the_real_runtime(self):
        out = recorded(built("orca"), "!orca types")
        self.assertNotIn("exited", out)
        self.assertNotIn("is not runnable", out)
        self.assertIn("router", out)  # a real type from the real runtime

    def test_adk_agents_answers_from_the_real_runtime(self):
        out = recorded(built("adk"), "!adk agents")
        self.assertNotIn("exited", out)
        self.assertIn("agents", out.lower())

    def test_adk_health_answers_from_the_real_runtime(self):
        out = recorded(built("adk"), "!adk health")
        self.assertNotIn("exited", out)
        self.assertTrue(out.strip())


class TestIdentity(unittest.TestCase):
    def test_every_orchestrator_nick_is_crew(self):
        for cls in ORCHESTRATOR_BOTS:
            self.assertIn(cls.domain, CREW)
            self.assertTrue(identify(cls.domain).is_crew, cls.domain)

    def test_orchestrator_nicks_are_not_privileged_by_nick(self):
        """Being crew must not imply operator."""
        for cls in ORCHESTRATOR_BOTS:
            self.assertFalse(identify(cls.domain).is_operator, cls.domain)


class TestBotConstruction(unittest.TestCase):
    def test_each_bot_uses_its_domain_as_the_nick(self):
        for cls in ORCHESTRATOR_BOTS:
            self.assertEqual(cls().nick, cls.domain)

    def test_nicks_fit_the_irc_limit(self):
        for cls in ORCHESTRATOR_BOTS:
            self.assertLessEqual(len(cls().nick), 31)

    def test_every_bot_declares_a_real_argv_prefix(self):
        for cls in ORCHESTRATOR_BOTS:
            self.assertTrue(cls.argv, cls.domain)
            self.assertTrue(cls.summary, cls.domain)

    def test_a_bot_with_no_read_only_commands_still_explains_itself(self):
        class Empty(RuntimeBot):
            runtime, domain, summary = "mem20empty", "empty", "nothing to see"
            argv = ("mem20empty",)

        out = recorded(Empty(nick="empty"), "!empty")
        self.assertIn("no read-only command", out)

    def test_help_text_is_built_for_every_bot(self):
        for cls in ORCHESTRATOR_BOTS:
            self.assertIn(f"!{cls.domain}_run", cls().help_text, cls.domain)


if __name__ == "__main__":
    unittest.main()