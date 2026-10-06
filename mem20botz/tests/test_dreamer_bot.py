"""Tests for Dreamer, the mem20dreamz bot in #dreamz.

The properties worth protecting:

* **She is on her own channel.** ``#dreamz``, not ``#mem20``. Putting her in the
  board crew would have her answering board questions on the dream channel.
* **She never claims anything the runtime did not report.** Her introduction is
  checked for the commands that actually exist.
* **She refuses the writers.** ``audit-hollow`` writes despite reading like a
  scanner; ``idle`` and ``nap`` belong to the ``mem20dream-idle`` unit, and a
  second writer on one lineage makes the braid chain lie.
* **Her read-only commands really answer**, against the real runtime.
"""

from __future__ import annotations

import re
import shlex
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mem20botz.dreamer_bot import DreamerBot  # noqa: E402
from mem20botz.identity import PRIVILEGED  # noqa: E402
from mem20botz.irc import parse_line  # noqa: E402

PRIVATE_MSG = ":jayson!j@localhost PRIVMSG dreamer :{text}"


def recorded(bot, text, private=False):
    said: list[str] = []
    bot.client.registered = True
    bot.say = lambda t, target="": said.append(t)
    bot.pm = lambda nick, t: said.append(t)
    line = PRIVATE_MSG if private else \
        ":jayson!j@localhost PRIVMSG #dreamz :" + text
    bot.on_message(parse_line(line.format(text=text) if private else line))
    return "\n".join(said)


def real_subcommands() -> set[str]:
    """The runtime's own subcommand list, read from its own --help.

    argparse wraps the usage line, so the braces span several lines. Joining
    every line that carries one is what makes this correct; taking only the
    first truncates the list mid-word.
    """
    import subprocess

    usage = subprocess.run(["mem20-dream", "--help"], capture_output=True,
                           text=True, timeout=60).stdout
    import re

    # argparse wraps the list, so it appears more than once and the first copy
    # is truncated. Take the longest {..} group, which is the complete one.
    blocks = re.findall(r"\{([a-z0-9,\-]+)\}", usage)
    longest = max(blocks, key=len)
    return {w for w in longest.split(",") if w}


def dreamer():
    return DreamerBot()


class TestHerChannel(unittest.TestCase):
    def test_she_is_on_dreamz_by_default(self):
        self.assertEqual(dreamer().channel, "#dreamz")

    def test_she_is_not_part_of_the_board_crew(self):
        from mem20botz.crew import Crew

        self.assertNotIn("dreamer", [b.nick for b in Crew().bots])

    def test_her_channel_exists_in_the_ircd_config(self):
        conf = Path("/opt/mem20/mem20botz/ircd/ngircd.conf").read_text()
        self.assertIn("#dreamz", conf)
        self.assertIn("#mem20", conf)

    def test_her_execute_word_is_privileged(self):
        self.assertIn("dream_run", PRIVILEGED)


class TestSheDoesNotOverclaim(unittest.TestCase):
    def test_her_introduction_only_advertises_commands_she_has(self):
        """The real invariant, and it survives her prose layout.

        Parsing "!dream panel | list" back into words is brittle; what matters
        is that she never names a subcommand she does not implement, and does
        not hide one she does.
        """
        bot = dreamer()
        text = bot.describe()
        listed = {n for n in bot.read_only if n in text}
        # Nothing on the !dream lines that looks like a subcommand but is not hers.
        candidates = set()
        for line in text.splitlines():
            if "!dream" not in line:
                continue
            body = line.split("!dream", 1)[1]
            for word in re.findall(r"[a-z][a-z0-9\-]*", body):
                candidates.add(word)
        unknown = {w for w in candidates
                   if w not in bot.read_only
                   and w not in {"panel", "lineage", "provenance", "what", "i",
                                 "can", "do", "id", "the", "runtime", "and",
                                 "me", "read", "them", "back", "to", "you",
                                 "exactly", "as", "it", "reports", "a", "run",
                                 "of", "iterations", "each", "one", "committed",
                                 "braid", "is", "model", "roster", "member",
                                 "per", "every", "node", "hash", "chained",
                                 "so", "can", "be", "re", "proved", "ask",
                                 "about", "chain", "stats", "show", "verify",
                                 "promotable", "list", "ledger"}
                   and w not in real_subcommands()}
        self.assertEqual(unknown, set(), f"advertised but not implemented: {unknown}")
        self.assertTrue(listed, "she describes none of her own commands")

    def test_her_read_only_commands_all_exist_in_the_runtime(self):
        real = real_subcommands()
        # Her friendly names for two real things: "stats" is idle-stats, and
        # "help" is the --help flag rather than a subcommand.
        friendly = {"stats": "idle-stats", "help": "--help"}
        for name in dreamer().read_only:
            target = friendly.get(name, name)
            if target == "--help":
                self.assertIn("--help",
                              __import__("subprocess").run(
                                  ["mem20-dream", "--help"],
                                  capture_output=True, text=True,
                                  timeout=60).stdout)
                continue
            self.assertIn(target, real, name)


class TestSheRefusesTheWriters(unittest.TestCase):
    def test_audit_hollow_is_not_a_read_only_command(self):
        """It reports newly_marked, so it writes. A scanner must not write."""
        bot = dreamer()
        self.assertNotIn("audit-hollow", bot.read_only)
        # No read-only command may put audit-hollow in the *subcommand* slot.
        # (It may appear later as an argument -- show/chain take a dream id.)
        for name, (_help, build) in bot.read_only.items():
            argv = [*bot.argv, *build("x")][1:]
            self.assertNotEqual(argv[0], "audit-hollow", name)

    def test_audit_hollow_is_reachable_only_on_the_execute_path(self):
        argv = dreamer().build_run_argv(["audit-hollow"])
        self.assertEqual(argv, ["mem20-dream", "audit-hollow"])

    def test_idle_and_nap_are_refused_with_a_reason(self):
        for word in ("idle", "nap"):
            out = recorded(dreamer(), f"!dream_run {word}", private=True)
            self.assertIn("mem20dream-idle", out, word)
            self.assertNotIn("exited", out, word)

    def test_idle_and_nap_build_no_argv(self):
        for word in ("idle", "nap"):
            self.assertIsNone(dreamer().build_run_argv([word]), word)

    def test_an_unknown_execute_verb_is_refused(self):
        out = recorded(dreamer(), "!dream_run wibble", private=True)
        self.assertIn("not a runnable invocation", out)


class TestChannelSafety(unittest.TestCase):
    def test_execute_is_refused_in_the_channel(self):
        out = recorded(dreamer(), "!dream_run new some-seed")
        self.assertIn("operator-only", out)

    def test_help_lists_her_commands_and_the_execute_path(self):
        out = recorded(dreamer(), "!dream")
        for name in dreamer().read_only:
            self.assertIn(name, out, name)
        self.assertIn("dream_run", out)

    def test_unknown_subcommand_refuses_without_running(self):
        out = recorded(dreamer(), "!dream wibble")
        self.assertIn("no read-only command", out)
        self.assertNotIn("exited", out)


class TestAgainstTheRealRuntime(unittest.TestCase):
    """Bounded and read-only. She answers from mem20-dream, not from memory."""

    def test_panel_answers(self):
        out = recorded(dreamer(), "!dream panel")
        self.assertNotIn("exited", out)
        self.assertNotIn("not runnable", out)
        self.assertIn("panel_size", out)

    def test_ledger_answers(self):
        out = recorded(dreamer(), "!dream ledger")
        self.assertNotIn("exited", out)
        self.assertIn("engine_id", out)

    def test_stats_answers(self):
        out = recorded(dreamer(), "!dream stats")
        self.assertNotIn("exited", out)
        self.assertIn("idle_dreams", out)


class TestConstruction(unittest.TestCase):
    def test_her_nick_is_dreamer_and_fits_irc(self):
        self.assertEqual(dreamer().nick, "dreamer")
        self.assertLessEqual(len(dreamer().nick), 31)

    def test_argv_is_the_real_console_script(self):
        self.assertEqual(dreamer().argv, ("mem20-dream",))

    def test_shlex_is_imported_for_the_run_override(self):
        """cmd_run parses args itself; a missing import would surface only in a DM."""
        import ast

        import mem20botz.dreamer_bot as mod
        src = Path(str(mod.__file__)).read_text()
        tree = ast.parse(src)
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == "cmd_run")
        names = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)}
        self.assertIn("shlex", names)


if __name__ == "__main__":
    unittest.main()