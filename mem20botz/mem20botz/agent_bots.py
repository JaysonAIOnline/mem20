"""The agentz and crew bots: chat access to the mem20 agent runtimes.

Both bots are thin. They shell out to the real CLIs — `mem20agentz` and
`python -m mem20crewz` — and report what came back. That is deliberate:

* A bot that imported the runtime could drift from it, and a crew bot whose
  idea of the agent roster differs from the agentz CLI's is a lie told to
  whoever is reading the channel.
* Shelling out means the channel shows the runtime's real answer, including
  its errors.

Both are bounded. A subprocess gets an explicit timeout, because a wedged
agent runtime must not wedge the IRC read loop and take the channel's
bot offline. And output is truncated before it reaches a channel, because an
unbounded `logs` dump would flood every reader.
"""

from __future__ import annotations

import shlex
import subprocess
from typing import Optional

from .base import Bot
from .irc import Message

#: A CLI that hangs must not hang the IRC loop.
CMD_TIMEOUT = 25
#: A channel line is a sentence, not a log file.
MAX_REPLY_LINES = 20
MAX_LINE_CHARS = 300
PYTHON = "/root/.venv/bin/python"


def run_cli(argv: list[str], timeout: int = CMD_TIMEOUT) -> tuple[int, str]:
    """Run a command, return ``(returncode, output)``.

    Never raises for a non-zero exit: a failing CLI is information the channel
    should see, not an exception that kills the bot. A timeout is reported the
    same way, because from the channel's point of view both are "the runtime
    did not answer".
    """
    try:
        proc = subprocess.run(argv, capture_output=True, text=True,
                              timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout}s"
    except OSError as exc:
        return 127, f"could not run: {exc}"
    out = (proc.stdout or "").strip() or (proc.stderr or "").strip()
    return proc.returncode, out


def condense(text: str, limit: int = MAX_REPLY_LINES) -> str:
    """Trim CLI output to something a channel can absorb."""
    lines = [ln[:MAX_LINE_CHARS] for ln in text.splitlines() if ln.strip()]
    if not lines:
        return "(no output)"
    if len(lines) > limit:
        head = lines[:limit]
        head.append(f"… and {len(lines) - limit} more lines")
        return "\n".join(head)
    return "\n".join(lines)


class AgentzBot(Bot):
    """Chat access to the mem20 agent platform."""

    name = "agentz"

    #: command word -> (human description, argv builder)
    def __init__(self, nick: str = "agentz", channel: str = "#mem20",
                 host: str = "127.0.0.1", port: int = 6667,
                 binary: str = "mem20agentz") -> None:
        self.binary = binary
        super().__init__(
            nick=nick, name="agentz", channel=channel, host=host, port=port,
            purpose=("chat access to the mem20 agent platform — profiles, "
                     "sessions, skills, status"),
            source_of_truth=(f"the `{self.binary}` CLI, shelled out live; this "
                             f"bot imports nothing, so the channel shows the "
                             f"runtime's real answer including its errors"),
            commands={
                "profiles": self.cmd_profiles,
                "sessions": self.cmd_sessions,
                "status": self.cmd_status,
                "skills": self.cmd_skills,
                "run": self.cmd_run,
            },
            help_text=("agentz: !profiles | !sessions | !status | "
                       "!skills [query] | !run <command>"),
        )

    def _agentz(self, *args: str) -> str:
        code, out = run_cli([self.binary, *args])
        if code == 127:
            return f"agentz: the {self.binary} CLI is not on PATH here."
        if code == 124:
            return f"agentz: {self.binary} did not answer in time."
        if code != 0:
            return f"agentz: {self.binary} exited {code} — {condense(out, 4)}"
        return condense(out)

    def cmd_profiles(self, bot: Bot, msg: Message, args: str) -> str:
        return self._agentz("profiles", "list")

    def cmd_sessions(self, bot: Bot, msg: Message, args: str) -> str:
        return self._agentz("sessions", "list")

    def cmd_status(self, bot: Bot, msg: Message, args: str) -> str:
        return self._agentz("status")

    def cmd_skills(self, bot: Bot, msg: Message, args: str) -> str:
        """Search the procedural-skill catalog.

        A search term is required. The catalog is an inventory rather than a
        menu, and dumping all of it into the channel every time anyone asked
        anything was never useful.

        The term goes through ``--query`` because that is the flag
        ``mem20agentz skills catalog`` actually accepts. It used to be passed
        positionally, which made *every* search exit 2 with "unrecognized
        arguments" — so ``!skills python`` had never once worked.
        """
        parts = shlex.split(args) if args.strip() else []
        if not parts:
            return ("agentz: !skills <searchterm> — searches the procedural "
                    "skill catalog, e.g. !skills search")
        return self._agentz("skills", "catalog", "--query", " ".join(parts))

    def cmd_run(self, bot: Bot, msg: Message, args: str) -> str:
        """Pass a command straight through to the agentz CLI.

        This is a deliberate escape hatch: it is a loopback-only channel whose
        operator is on the box, and it means an agent does not need a new bot
        command for every agentz feature. The allowlist below keeps it from
        becoming arbitrary shell.
        """
        parts = shlex.split(args) if args.strip() else []
        if not parts:
            return "agentz: !run <command> — e.g. !run status"
        safe = {"status", "doctor", "config", "logs", "profiles", "sessions",
                "skills", "projects", "cron", "kanban"}
        if parts[0] not in safe:
            return (f"agentz: !run {parts[0]!r} is not allowed. "
                    f"Allowed: {', '.join(sorted(safe))}")
        return self._agentz(*parts)


class CrewBot(Bot):
    """Chat access to the mem20 crew runtime."""

    name = "crewbot"

    def __init__(self, nick: str = "crewbot", channel: str = "#mem20",
                 host: str = "127.0.0.1", port: int = 6667,
                 python: str = PYTHON) -> None:
        self.python = python
        super().__init__(
            nick=nick, name="crewbot", channel=channel, host=host, port=port,
            purpose=("chat access to the mem20 crew runtime — A2A peers and "
                     "kicking off crews from YAML"),
            source_of_truth=(f"`{self.python} -m mem20crewz` (the cleanroom "
                             f"crew runtime), shelled out live; a bot that "
                             f"imported the runtime could drift from it"),
            commands={
                "peers": self.cmd_peers,
                "crew": self.cmd_crew,
                "crewhelp": self.cmd_crewhelp,
            },
            help_text=("crewbot: !peers | !crew <agents.yaml> | "
                       "!crewhelp — cleanroom crews on mem20"),
        )

    def _crewz(self, *args: str) -> str:
        code, out = run_cli([self.python, "-m", "mem20crewz", *args])
        if code == 127:
            return f"crewbot: cannot run the crew runtime ({out})."
        if code == 124:
            return "crewbot: the crew runtime did not answer in time."
        if code != 0:
            return f"crewbot: crew runtime exited {code} — {condense(out, 4)}"
        return condense(out)

    def cmd_peers(self, bot: Bot, msg: Message, args: str) -> str:
        return self._crewz("peers")

    def cmd_crew(self, bot: Bot, msg: Message, args: str) -> str:
        """Kick off a crew from a YAML file.

        Refuses a path that does not exist rather than letting the runtime
        report a confusing error much later.
        """
        parts = shlex.split(args) if args.strip() else []
        if not parts:
            return "crewbot: !crew <agents.yaml> — which crew?"
        import pathlib
        cfg = pathlib.Path(parts[0]).expanduser()
        if not cfg.is_file():
            return f"crewbot: no such crew file: {cfg}"
        return self._crewz("run", str(cfg))

    def cmd_crewhelp(self, bot: Bot, msg: Message, args: str) -> str:
        return self._crewz("--help")
