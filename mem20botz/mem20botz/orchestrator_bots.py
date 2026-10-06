"""One IRC bot per mem20 orchestrator runtime.

Why these exist
---------------
mem20 has several orchestrators — crewz, orcaz, langz, kimiz, googlez and the
agentz SDK — and until now only crewz was reachable from the channel. An agent
that can see the board but cannot ask what the runtimes can do has to guess, and
guessing is what the rest of this system exists to prevent.

Each bot is a **view, not a writer**, like every other bot in the crew. It shells
out to the real runtime and reports what came back, including its errors. It
imports nothing from the runtimes, so it cannot drift from them.

Two rules shape every bot here
------------------------------

**Read-only in the channel, execution in a DM.** A command that *runs* a
workflow is registered under a ``<domain>_run`` word that is in
:data:`~mem20botz.identity.PRIVILEGED`, so the base class refuses it in public
and only the operator can send it privately. Read-only commands stay open to
crew, because listing agents or checking health changes nothing.

**Never start a server.** ``serve`` blocks forever. A bot that runs it wedges its
own command handler and the channel stops getting answers, so every bot here
refuses ``serve`` outright rather than trusting a timeout to save it. The same
reason ``mem20path`` excludes ``mem20-metrics``.

Every subcommand below was executed against the real runtime before being wired
up. A command is only here if it actually answered.
"""

from __future__ import annotations

import shlex
import sys
from typing import Callable, ClassVar, Optional

from .agent_bots import condense, run_cli
from .base import Bot
from .irc import Message

#: Interpreter used for the ``-m`` invocations.
PYTHON = sys.executable

#: Bounded on purpose. A read-only query should answer in seconds; anything
#: slower is a hung runtime and saying so beats blocking the channel.
QUERY_TIMEOUT = 30

#: Execution is slower than a query but still bounded.
RUN_TIMEOUT = 180

#: Subcommands that block forever. Refused by every bot, always.
BLOCKING = frozenset({"serve", "daemon", "watch", "shell"})


class RuntimeBot(Bot):
    """Base for a bot that fronts one orchestrator runtime over IRC.

    Subclasses declare their read-only subcommands in :attr:`read_only` and
    override :meth:`build_run_argv` for the operator-only execute path. Nothing
    else needs overriding.
    """

    #: The runtime's display name, used in help and !about.
    runtime = ""

    #: The command word this bot answers to, e.g. ``adk`` for ``!adk``.
    domain = ""

    #: argv prefix. Either a console script, or the interpreter plus ``-m``.
    argv: tuple[str, ...] = ()

    #: One-line description of what this runtime is for.
    summary = ""

    #: subcommand -> (human help, argv builder taking the argument string).
    #: Subclasses set this as a plain class attribute. The empty default is
    #: deliberate: a bot with nothing safe to expose must still be able to
    #: answer, rather than raising when someone asks it what it does.
    read_only: ClassVar[dict] = {}

    def __init__(self, nick: str = "", channel: str = "#mem20",
                 host: str = "127.0.0.1", port: int = 6667) -> None:
        self.nick = nick or self.domain
        run_word = f"{self.domain}_run"
        super().__init__(
            nick=self.nick,
            name=self.nick,
            channel=channel,
            host=host,
            port=port,
            purpose=f"chat access to the {self.runtime} runtime — {self.summary}",
            source_of_truth=(f"`{' '.join(self.argv)}` (the real "
                             f"{self.runtime} runtime), shelled out live; this "
                             f"bot imports nothing from it, so the channel "
                             f"shows the runtime's actual answer"),
            commands={
                self.domain: self.cmd_query,
                run_word: self.cmd_run,
            },
            help_text=self._help_text(run_word),
        )

    # ------------------------------------------------------------- plumbing
    def _help_text(self, run_word: str) -> str:
        lines = [f"{self.nick}: !{self.domain} — {self.summary}",
                 f"  !{self.domain} <{' | '.join(sorted(self.read_only))}>"]
        lines.append(f"  !{run_word} … — execute (operator DM only)")
        lines.append("  !about for what this bot reads")
        return "\n".join(lines)

    def _query_help(self) -> str:
        run_word = f"!{self.domain}_run"
        if not self.read_only:
            return (f"{self.nick}: {self.runtime} has no read-only command "
                    f"safe for the channel. Execution is {run_word}, "
                    f"operator DM only.")
        rows = "\n".join(f"  {name:<10} {help_text}"
                         for name, (help_text, _) in sorted(self.read_only.items()))
        # The execute path is named here too, so someone who typed the bare
        # domain word learns it exists before wondering why it is not listed.
        return (f"{self.nick}: {self.runtime} — {self.summary}\n{rows}\n"
                f"  execute: {run_word} (operator DM only)")

    def _invoke(self, argv: list[str], timeout: int) -> str:
        code, out = run_cli(argv, timeout=timeout)
        if code == 127:
            return f"{self.nick}: {' '.join(argv[:2])} is not runnable here."
        if code == 124:
            return f"{self.nick}: {self.runtime} did not answer in {timeout}s."
        if code != 0:
            return f"{self.nick}: {self.runtime} exited {code} — {condense(out, 4)}"
        return condense(out) if out.strip() else f"{self.nick}: {self.runtime} said nothing."

    def _refuse_blocking(self, argv: list[str]) -> Optional[str]:
        """Refuse anything that would block forever, before running it."""
        for token in argv:
            if token in BLOCKING:
                return (f"{self.nick}: refusing to run {token!r} — it blocks "
                        f"forever and would wedge this bot. Run it in a "
                        f"terminal instead.")
        return None

    # ------------------------------------------------------------- commands
    def cmd_query(self, bot: Bot, msg: Message, args: str) -> str:
        parts = shlex.split(args) if args.strip() else []
        if not parts:
            return self._query_help()
        name, rest = parts[0], " ".join(parts[1:])
        entry = self.read_only.get(name)
        if entry is None:
            known = ", ".join(sorted(self.read_only)) or "none"
            return (f"{self.nick}: no read-only command {name!r}. "
                    f"Available: {known}. Use !{self.domain} for help.")
        _, build = entry
        argv = [*self.argv, *build(rest)]
        refusal = self._refuse_blocking(argv)
        if refusal:
            return refusal
        return self._invoke(argv, QUERY_TIMEOUT)

    def cmd_run(self, bot: Bot, msg: Message, args: str) -> str:
        parts = shlex.split(args) if args.strip() else []
        if not parts:
            return f"{self.nick}: !{self.domain}_run <args> — what to execute?"
        argv = self.build_run_argv(parts)
        if argv is None:
            return f"{self.nick}: that is not a runnable invocation."
        refusal = self._refuse_blocking(argv)
        if refusal:
            return refusal
        return self._invoke(argv, RUN_TIMEOUT)

    def build_run_argv(self, parts: list[str]) -> Optional[list[str]]:
        """argv for an execute request. Subclasses that support it override."""
        return None


# --------------------------------------------------------------------- orcaz
class OrcaBot(RuntimeBot):
    """Deterministic OrKa-style workflow runner."""

    runtime = "mem20orcaz"
    domain = "orca"
    argv = ("mem20orcaz",)
    summary = "deterministic YAML workflow runner"

    def __init__(self, nick: str = "orca", **kw) -> None:
        super().__init__(nick=nick, **kw)

    read_only: ClassVar[dict] = {
        "types": ("list every agent/node type the runtime knows",
                  lambda rest: ["--list-types"]),
        "version": ("print the runtime version",
                    lambda rest: ["--version"]),
    }

    def build_run_argv(self, parts: list[str]) -> Optional[list[str]]:
        if not parts[0].endswith((".yaml", ".yml")):
            return None
        return [*self.argv, parts[0], "--outputs", *parts[1:]]


# --------------------------------------------------------------------- langz
class GraphBot(RuntimeBot):
    """Stateful LangGraph-style graphs: loops, fan-out, interrupts."""

    runtime = "mem20langz"
    domain = "graph"
    argv = (PYTHON, "-m", "mem20langz")
    summary = "stateful graphs — loop, fanout, interrupt"

    def __init__(self, nick: str = "graph", **kw) -> None:
        super().__init__(nick=nick, **kw)

    read_only: ClassVar[dict] = {
        "help": ("the runtime's own usage text",
                 lambda rest: ["--help"]),
        "commands": ("every langz subcommand",
                     lambda rest: ["--help"]),
    }

    def build_run_argv(self, parts: list[str]) -> Optional[list[str]]:
        # serve is filtered out by _refuse_blocking.
        return [*self.argv, *parts]


# --------------------------------------------------------------------- kimiz
class SwarmBot(RuntimeBot):
    """Kimi-style parallel sub-agent fan-out with rate-limit awareness."""

    runtime = "mem20kimiz"
    domain = "swarm"
    argv = (PYTHON, "-m", "mem20kimiz")
    summary = "parallel sub-agent fan-out"

    def __init__(self, nick: str = "swarm", **kw) -> None:
        super().__init__(nick=nick, **kw)

    read_only: ClassVar[dict] = {
        "help": ("the runtime's own usage text — items and template are "
                "both required to run",
                 lambda rest: ["--help"]),
    }

    def build_run_argv(self, parts: list[str]) -> Optional[list[str]]:
        # kimiz requires --items and --template; anything else is not runnable.
        if "--items" not in parts or "--template" not in parts:
            return None
        return [*self.argv, *parts]


# ------------------------------------------------------------------- googlez
class AdkBot(RuntimeBot):
    """Google ADK-style agents on a local model endpoint."""

    runtime = "mem20googlez"
    domain = "adk"
    argv = (PYTHON, "-m", "mem20googlez")
    summary = "ADK agents on the local model endpoint"

    def __init__(self, nick: str = "adk", **kw) -> None:
        super().__init__(nick=nick, **kw)

    read_only: ClassVar[dict] = {
        "agents": ("list registered agents", lambda rest: ["agents"]),
        "health": ("check the resolved model endpoint",
                   lambda rest: ["health"]),
    }

    def build_run_argv(self, parts: list[str]) -> Optional[list[str]]:
        return [*self.argv, "run", *parts]


# -------------------------------------------------------------- agentz SDK
class SdkBot(RuntimeBot):
    """The OpenAI Agents SDK port: Agent, Runner, Tools, Handoffs."""

    runtime = "mem20agentz_sdk"
    domain = "sdk"
    argv = (PYTHON, "-m", "mem20agentz_sdk")
    summary = "the agents SDK — Agent, Runner, Tools, Handoffs"

    def __init__(self, nick: str = "sdk", **kw) -> None:
        super().__init__(nick=nick, **kw)

    read_only: ClassVar[dict] = {
        "help": ("the runtime's own usage text", lambda rest: ["--help"]),
    }

    def build_run_argv(self, parts: list[str]) -> Optional[list[str]]:
        if not parts:
            return None
        return [*self.argv, *parts]


#: Every orchestrator bot, in the order the crew should start them.
ORCHESTRATOR_BOTS = (OrcaBot, GraphBot, SwarmBot, AdkBot, SdkBot)