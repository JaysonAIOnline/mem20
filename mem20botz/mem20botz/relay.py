"""The relay: what happens in #mem20 lands in mem20 memory.

An IRC channel people and agents can read is also a channel they cannot
search. The relay closes that loop by storing a bounded, redacted digest of
each message into mem20's memory, so "what did we decide in the channel last
Tuesday" is answerable by the memory system rather than by scrolling a log.

Three rules, all of them consequences of the data-integrity standing rule:

* **Detection never mutates the source.** The transcript on the IRC server is
  untouched. The relay only *reads* messages and *writes* new memory rows.
* **The relay is a reader.** It never speaks as a bot, never issues commands,
  and never claims work. It is not a participant; it is a scribe.
* **Storage is bounded and redacted at the output layer.** Only channel
  messages are stored, capped in length, and secret-shaped text is masked
  before it is written — masking happens on the value being stored, never by
  rewriting what a human typed into the channel itself.

If mem20 is unavailable, the relay says so once and keeps reading the channel.
Losing the scribe must never take the crew offline.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Optional

from .base import Bot
from .irc import Message

#: Longer messages are truncated before storage. A pasted log is noise, and an
#: unbounded write into memory is a memory leak with a chat trigger.
MAX_STORE_CHARS = 400
#: How many relay notices to send before giving up on telling the channel it
#: is offline. A bot that says "I am broken" on every line is worse than one
#: that says it once.
MAX_WARNINGS = 1

#: Secret-shaped text is masked on the way into memory. These are deliberately
#: broad: a false positive costs a masked string, a false negative writes a
#: credential into a searchable store.
SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
)


def mask_secrets(text: str) -> str:
    """Mask secret-shaped substrings in a copy of the text.

    Returns a new string. The caller's original is never modified, which is
    what keeps this an output-layer operation rather than a rewrite of what a
    human authored.
    """
    out = text
    for pat in SECRET_PATTERNS:
        out = pat.sub(lambda m: _mask(m.group(0)), out)
    return out


def _mask(token: str) -> str:
    if "@" in token and "." in token and " " not in token:
        # An email address: keep enough to recognise, mask the local part.
        local, _, domain = token.partition("@")
        return f"{local[:1]}***@{domain}"
    if len(token) <= 8:
        return "***"
    return f"{token[:4]}…{token[-2:]}({len(token)})"


class RelayBot(Bot):
    """Stores a redacted digest of the channel into mem20 memory.

    :param store: callable taking ``(content, category, tags)`` and returning
        whatever the memory layer returns. Injectable so the relay can be
        tested without a live memory system, and so a different memory backend
        is a constructor argument rather than an edit.
    :param memory: the mem20 memory module. Optional; when absent the relay
        reports that memory is unreachable and keeps reading.
    """

    name = "relay"

    def __init__(self, nick: str = "relay", channel: str = "#mem20",
                 host: str = "127.0.0.1", port: int = 6667,
                 store: Optional[Callable[..., object]] = None) -> None:
        self._store = store
        #: False = not yet resolved, None = resolution failed. Distinguished
        #: so a missing memory system is not re-imported on every message.
        self._resolved: Any = False
        self.stored = 0
        self.masked = 0
        self.failures = 0
        self.warned = 0
        super().__init__(
            nick=nick, name="relay", channel=channel, host=host, port=port,
            purpose=("the scribe — stores a redacted digest of the channel "
                     "into mem20 memory so the conversation is searchable "
                     "afterwards"),
            source_of_truth=("mem20 memory (a reader only: it never speaks, "
                             "never claims work, and never rewrites the "
                             "channel transcript — secret-shaped text is "
                             "masked on the value being stored)"),
            commands={"relaystatus": self.cmd_status},
            help_text="relay: !relaystatus — channel digest → mem20 memory",
        )

    # ------------------------------------------------------------- storage
    #: The real mem20 memory entry point. Resolved once, lazily, because
    #: importing it at module load would make the relay unusable (and its
    #: tests unrunnable) outside the estate.
    def _store_fn(self) -> Optional[Callable[..., object]]:
        if self._store is not None:
            return self._store
        if self._resolved is not False:
            return self._resolved
        try:
            import memory_engine.memory as mem  # type: ignore
            self._resolved = getattr(mem, "remember", None)
        except Exception:  # noqa: BLE001
            self._resolved = None
        return self._resolved

    def record(self, nick: str, text: str) -> bool:
        """Store one message. Returns True when it actually landed.

        Never raises: a memory failure is a scribe problem, not a channel
        problem, and must not stop the relay from reading the next line.
        """
        body = (text or "").strip()[:MAX_STORE_CHARS]
        if not body:
            return False
        safe = mask_secrets(body)
        if safe != body:
            self.masked += 1
        content = f"[#mem20] {nick}: {safe}"
        fn = self._store_fn()
        if fn is None:
            self.failures += 1
            self._warn_once()
            return False
        try:
            fn(topic="irc:mem20", content=content,
               tags=["irc", "#mem20", "crew-chat"])
        except TypeError:
            # Tolerate a simpler signature rather than losing the line.
            try:
                fn(content)
            except Exception:  # noqa: BLE001
                self.failures += 1
                self._warn_once()
                return False
        except Exception:  # noqa: BLE001
            self.failures += 1
            self._warn_once()
            return False
        self.stored += 1
        return True

    def _warn_once(self) -> None:
        if self.warned >= MAX_WARNINGS:
            return
        self.warned += 1
        # Announcing the failure must not itself raise. `record` is called
        # from the message path, so an exception here would propagate into the
        # IRC read loop and take the scribe down while it is already broken.
        try:
            self.say("relay: mem20 memory is unreachable — the channel still "
                     "works, I just cannot scribe. !relaystatus for detail.")
        except Exception:  # noqa: BLE001
            pass

    # -------------------------------------------------------------- routing
    def on_message(self, msg: Message) -> None:
        """Scribe the message, then let normal command routing run."""
        if msg.command == "PRIVMSG" and msg.is_channel:
            # Skip this bot's own output, or the relay would transcribe
            # itself and amplify every message into a loop.
            if msg.nick.lower() != self.nick.lower():
                self.record(msg.nick, msg.text)
        super().on_message(msg)

    def cmd_status(self, bot: Bot, msg: Message, args: str) -> str:
        health = "connected" if self._store_fn() else "memory UNREACHABLE"
        return (f"relay: {health} | stored {self.stored} | masked {self.masked} "
                f"| failures {self.failures} | uptime {int(self.uptime())}s")
