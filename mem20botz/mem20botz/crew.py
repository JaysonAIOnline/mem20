"""The mem20botz daemon: all five crew bots in one supervised process.

Why one process rather than four units:

* The channel is the product. If three of four bots are up, the channel is
  half broken in a way nobody notices until a claim goes unanswered. One unit
  means one restart, one status, one place to look.
* One IRC connection per bot, one process: four systemd units and four
  reconnect loops would multiply the failure modes for no benefit.

The trade is explicit: a crash in one bot takes the others down with it. That
is the right trade at this size, and the unit's ``Restart=on-failure`` plus the
per-bot reconnect backoff keeps the outage short. If the crew grows enough that
this hurts, the fix is per-bot units, not a shared process.

Each bot is started in its own thread and given its own IRCClient, so a
blocking read in one cannot stall another. A bot whose command handler raises
is reported in the channel and that bot keeps serving.
"""

from __future__ import annotations

import threading
import time
from typing import Optional

from .agent_bots import AgentzBot, CrewBot
from .base import Bot
from .kanban_bot import KanbanBot
from .orchestrator_bots import ORCHESTRATOR_BOTS
from .relay import RelayBot


class Crew:
    """Starts and supervises the bots."""

    def __init__(self, channel: str = "#mem20", host: str = "127.0.0.1",
                 port: int = 6667, board: str = "Fleet HQ",
                 advertise_every: int = 60,
                 start_relay: bool = True) -> None:
        self.channel = channel
        self.host = host
        self.port = port
        self.advertise_every = max(15, advertise_every)
        self.threads: list[threading.Thread] = []
        # Held with its concrete type: the advertise timer is specific to the
        # kanban bot, and typing it as Bot would hide that from the checker.
        self.kanban = KanbanBot(nick="kanban", board=board, channel=channel,
                                host=host, port=port)
        self.bots: list[Bot] = [
            self.kanban,
            AgentzBot(nick="agentz", channel=channel, host=host, port=port),
            CrewBot(nick="crewbot", channel=channel, host=host, port=port),
        ]
        # One bot per orchestrator runtime, so an agent in the channel can ask
        # what each runtime can actually do instead of guessing.
        self.bots.extend(cls(nick=cls.domain, channel=channel, host=host,
                             port=port) for cls in ORCHESTRATOR_BOTS)
        if start_relay:
            self.bots.append(RelayBot(nick="relay", channel=channel,
                                      host=host, port=port))
        self._stop = threading.Event()

    @staticmethod
    def bot_classes() -> tuple[type, ...]:
        """Every bot class the crew starts, in order.

        Exposed so `mem20botz bots` can list the crew without opening a socket
        and without keeping its own copy of this list. A hand-maintained list
        here drifted once already and reported four bots while the daemon ran
        nine.
        """
        return (KanbanBot, AgentzBot, CrewBot, *ORCHESTRATOR_BOTS, RelayBot)

    # ------------------------------------------------------------- lifecycle
    def start(self) -> None:
        for bot in self.bots:
            t = threading.Thread(target=bot.run, name=f"bot-{bot.name}",
                                 daemon=True)
            t.start()
            self.threads.append(t)
        threading.Thread(target=self._advertise_loop, name="advertise",
                         daemon=True).start()
        self._announce()

    def _announce(self) -> None:
        time.sleep(1.0)  # let registration settle before speaking
        who = ", ".join(b.nick for b in self.bots)
        self.kanban.say(
            f"mem20 crew online in {self.channel}: {who}. "
            f"!help for commands, !jobs to see work.")

    def _advertise_loop(self) -> None:
        """Surface new unclaimed work on a timer.

        This is what makes the board self-advertising: a card added through the
        REST API or the CLI shows up in the channel without anyone asking.
        """
        while not self._stop.wait(self.advertise_every):
            try:
                line = self.kanban.advertise()
            except Exception:  # noqa: BLE001
                continue
            if line:
                try:
                    self.kanban.say(line)
                except Exception:  # noqa: BLE001
                    pass

    def stop(self, *_args) -> None:
        self._stop.set()
        for bot in self.bots:
            try:
                bot.stop()
            except Exception:  # noqa: BLE001
                pass

    def join(self, timeout: Optional[float] = None) -> None:
        for t in self.threads:
            t.join(timeout=timeout)

    def run(self) -> None:
        self.start()
        try:
            while not self._stop.is_set():
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()
            self.join(timeout=5)
