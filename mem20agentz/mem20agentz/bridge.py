"""Bridge harness — transport-neutral messaging (sub-phase 2.5).

A `Transport` is any object with:
    send(chat_id: str, text: str) -> None
    poll(timeout: float) -> Message | None      # blocks up to timeout
    start() / stop() -> None

`Bridge` wraps a transport with pairing, one agent worker per chat, and
ledger logging. Real adapters live in `mem20agentz/bridges/`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional, Protocol

from .config import config_dir


class TransportError(RuntimeError):
    """Base error for transport failures (auth, unreachable, malformed)."""


class AuthError(TransportError):
    """Raised when a transport cannot authenticate/provision."""


@dataclass
class Message:
    chat_id: str
    text: str
    sender: str = ""
    platform: str = "unknown"
    ts: float = 0.0
    media: list[str] = field(default_factory=list)

    @property
    def has_media(self) -> bool:
        return bool(self.media)


class Transport(Protocol):
    def send(self, chat_id: str, text: str) -> None: ...
    def poll(self, timeout: float) -> Optional[Message]: ...

    def start(self) -> None:
        """Optional lifecycle hook."""

    def stop(self) -> None:
        """Optional lifecycle hook."""


PAIRS_FILE = "pairs.json"

# Circuit breaker: when the transport (e.g. Telegram) can't be reached — say the
# internet is down — banging poll() every interval forever just floods logs and
# the ledger. After this many consecutive poll errors we trip the breaker and
# stop trying except for one slow re-probe per TRIED_RETRY_INTERVAL_S. A single
# successful poll resets the breaker.
MAX_CONSECUTIVE_ERRORS = 3
TRIP_RETRY_INTERVAL_S = 1200.0  # re-probe once every 20 minutes while tripped


class Bridge:
    def __init__(self, name: str, transport: Transport,
                 agent_factory=None, ledger=None,
                 root=None, require_pairing: bool = True,
                 session_prefix: str = "chat:") -> None:
        self.name = name
        self.transport = transport
        self.agent_factory = agent_factory  # callable(chat_id) -> AgentCore
        self.ledger = ledger
        self.root = root or config_dir() / "gateway"
        self.require_pairing = require_pairing
        # must match build_agent_factory's session_prefix so the transcript
        # written here is exactly the transcript the resume weaver reads.
        self.session_prefix = session_prefix
        self._stop = False
        self._consecutive_errors = 0
        self._tripped = False

    # ------------------------------------------------------------ pairing
    def pairs(self) -> list[str]:
        return sorted(self._load_pairs().get(self.name, []))

    def pair(self, chat_id: str) -> list[str]:
        pairs = self._load_pairs()
        item = pairs.setdefault(self.name, [])
        if chat_id not in item:
            item.append(chat_id)
        self._save_pairs(pairs)
        return item

    def unpair(self, chat_id: str) -> bool:
        pairs = self._load_pairs()
        item = pairs.get(self.name, [])
        if chat_id not in item:
            return False
        item.remove(chat_id)
        self._save_pairs(pairs)
        return True

    def _is_paired(self, chat_id: str) -> bool:
        if not self.require_pairing:
            return True
        return chat_id in self._load_pairs().get(self.name, [])

    # ------------------------------------------------------------ lifecycle
    def send(self, chat_id: str, text: str) -> None:
        self.transport.send(chat_id, text)
        self._log("out", chat_id, text)

    def run(self, interval_s: float = 0.5) -> None:
        """Blocking poll loop for this bridge."""
        try:
            self.transport.start()
        except Exception:  # noqa: BLE001
            pass
        self._stop = False
        while not self._stop:
            if self._tripped:
                # Circuit is open during an outage: sleep through it, then take
                # one slow re-probe. No per-attempt logging while tripped.
                time.sleep(TRIP_RETRY_INTERVAL_S)
            try:
                msg = self.transport.poll(interval_s)
            except Exception as exc:  # noqa: BLE001
                self._consecutive_errors += 1
                if not self._tripped:
                    if self._consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                        self._tripped = True
                        self._log(
                            "breaker_tripped",
                            "",
                            f"{self._consecutive_errors} consecutive poll errors; "
                            f"pausing retries for {TRIP_RETRY_INTERVAL_S:.0f}s",
                        )
                    else:
                        self._log("poll_error", "", str(exc))
                if self._tripped:
                    continue
                time.sleep(interval_s)
                continue
            if self._consecutive_errors:
                # Transport is back — reset the breaker so the next outage
                # counts from zero.
                self._consecutive_errors = 0
                self._tripped = False
            if msg is None:
                continue
            msg.platform = self.name
            self._log("in", msg.chat_id, msg.text)
            if not self._is_paired(msg.chat_id):
                self._log("ignored", msg.chat_id, "chat not paired")
                continue
            try:
                reply = self.handle(msg)
                if reply:
                    self.send(msg.chat_id, reply)
            except Exception as exc:  # noqa: BLE001
                self._log("error", msg.chat_id, str(exc))

    def stop(self) -> None:
        self._stop = True
        try:
            self.transport.stop()
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------ dispatch
    def handle(self, msg: Message) -> str:
        if self.agent_factory is None:
            return "[gateway] no agent configured"
        core = self.agent_factory(msg.chat_id)
        text = msg.text
        if msg.has_media:
            text = f"{text} [media: {len(msg.media)} attachment(s)]"
        result = core.run(text)
        if result.blocked:
            return "[gateway] run blocked by approvals"
        if not result.text:
            return "[gateway] no reply produced"
        return result.text

    # ------------------------------------------------------------ helpers
    def _log(self, direction: str, chat_id: str, text: str) -> None:
        # Poll failures are transient transport noise, not durable session
        # content. Route them to stderr only — writing every retry to the
        # memory ledger poisoned recall with thousands of identical rows.
        if direction in ("poll_error", "error", "breaker_tripped") and self.ledger is not None:
            import sys
            print(f"[gateway:{self.name}] {direction}:{chat_id} {str(text)[:200]}",
                  file=sys.stderr)
            return
        if self.ledger is None:
            return
        try:
            self.ledger.session_append(
                "gateway", f"{self.session_prefix}{chat_id}", "system",
                f"{direction}:{chat_id} {str(text)[:400]}")
        except Exception as exc:  # noqa: BLE001
            import sys
            print(f"[gateway:{self.name}] ledger write failed: {exc}",
                  file=sys.stderr)

    def _load_pairs(self) -> dict:
        path = self.root / PAIRS_FILE
        import json
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return {}

    def _save_pairs(self, data: dict) -> None:
        import json
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / PAIRS_FILE).write_text(
            json.dumps(data, indent=2), encoding="utf-8")