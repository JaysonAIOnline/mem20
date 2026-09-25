"""Loopback bridge — self-delivery transport (phase-02 acceptance).

A real, account-free adapter that proves the full gateway turnstile end to
end: a message entered with `gateway loopback-deliver <chat> <text>` is
consumed by the daemon's poll loop, handled by the per-chat agent, and the
reply is transmitted to `<chat>.out`, where `gateway loopback-recv <chat>`
collects it. State lives in `<root>/loopback/*.{in,out}` jsonl files so any
process can inject or collect while the daemon runs (the same cross-process
pattern the daemon already uses for pairing).
"""

from __future__ import annotations

import json
import pathlib
import time
from typing import Optional

from ..bridge import Message
from ..config import config_dir

INBOX_SUFFIX = ".in"
OUTBOX_SUFFIX = ".out"


class LoopbackTransport:
    def __init__(self, root: Optional[pathlib.Path] = None,
                 poll_interval: float = 0.1) -> None:
        self.root = pathlib.Path(root) if root is not None \
            else config_dir() / "gateway" / "loopback"
        self.root.mkdir(parents=True, exist_ok=True)
        self._interval = poll_interval
        self._stopped = False

    # ------------------------------------------------------- injection
    def deliver(self, chat_id: str, text: str) -> dict:
        """Enter a message into the bridge queue (peer-of-gateway side)."""
        with self._path(chat_id, INBOX_SUFFIX).open("a",
                                                     encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": time.time(), "text": text}) + "\n")
        return {"ok": True, "chat_id": chat_id, "text": text}

    # --------------------------------------------------------- transport
    def send(self, chat_id: str, text: str) -> None:
        with self._path(chat_id, OUTBOX_SUFFIX).open("a",
                                                      encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": time.time(), "text": text}) + "\n")

    def poll(self, timeout: float) -> Optional[Message]:
        """Return the oldest queued message across any chat's inbox, else
        None after `timeout` seconds. The daemon runs one poll loop."""
        deadline = time.monotonic() + max(timeout, 0.0)
        while time.monotonic() < deadline and not self._stopped:
            msg = self._pop_one()
            if msg is not None:
                return msg
            time.sleep(self._interval)
        return None

    def collect(self, chat_id: str) -> list[dict]:
        """Read and clear the outbox for a chat (what the gateway sent)."""
        path = self._path(chat_id, OUTBOX_SUFFIX)
        if not path.exists():
            return []
        try:
            rows = []
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
            path.write_text("", encoding="utf-8")
            return rows
        except OSError:
            return []

    # ------------------------------------------------------------ helpers
    def _path(self, chat_id: str, suffix: str) -> pathlib.Path:
        safe = chat_id.replace("/", "_").replace("..", ".")
        return self.root / f"{safe}{suffix}"

    def _pop_one(self) -> Optional[Message]:
        for inbox in self.root.glob("*" + INBOX_SUFFIX):
            chat_id = inbox.name[: -len(INBOX_SUFFIX)]
            try:
                lines = inbox.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            if not lines or not lines[0].strip():
                continue
            rest = "\n".join(lines[1:])
            inbox.write_text(rest, encoding="utf-8")
            try:
                payload = json.loads(lines[0])
            except ValueError:
                continue
            return Message(chat_id=chat_id, text=payload.get("text", ""),
                           sender="loopback", platform="loopback",
                           ts=payload.get("ts") or 0.0)
        return None

    # --------------------------------------------------------- lifecycle
    def start(self) -> None:
        self._stopped = False

    def stop(self) -> None:
        self._stopped = True