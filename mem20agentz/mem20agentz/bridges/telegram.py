"""Telegram bridge — long-poll adapter (sub-phase 2.5).

Real transport over the Bot API using httpx:
    getUpdates(offset, timeout)  -> 0..n Message objects
    sendMessage(chat_id, text)   -> None

Bootstraps the token lazily from (in order):
    MEM20AGENTZ_TELEGRAM_TOKEN env
    TELEGRAM_BOT_TOKEN env
    token= line in /root/.env
The token is never printed. Without a token, `start()` fails honestly with
TelegramAuthError.  Hermetic dry-runs wire `base_url` to a fake server.
"""

from __future__ import annotations

import os
import pathlib
import time
from typing import Optional

import httpx

from ..bridge import AuthError, Message


class TelegramAuthError(AuthError):
    pass


class TelegramTransport:
    def __init__(self, base_url: str = "https://api.telegram.org") -> None:
        self.base_url = base_url.rstrip("/")
        self.token = self._token()
        self._offset = 0
        self._client = None

    # --------------------------------------------------------- auth
    def _token(self) -> str:
        for name in ("MEM20AGENTZ_TELEGRAM_TOKEN", "TELEGRAM_BOT_TOKEN"):
            value = os.environ.get(name, "").strip()
            if value:
                return value
        env_file = pathlib.Path("/root/.env")
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("TELEGRAM_BOT_TOKEN="):
                    return line.partition("=")[2].strip().strip('"').strip("'")
        raise TelegramAuthError(
            "no telegram token (set MEM20AGENTZ_TELEGRAM_TOKEN or "
            "TELEGRAM_BOT_TOKEN in /root/.env)")

    # --------------------------------------------------------- lifecycle
    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=30)
        return self._client

    def start(self) -> None:
        # cheap liveness check: resolve the bot account name
        r = self._http().get(
            f"{self.base_url}/bot{self.token}/getMe", timeout=15)
        if r.status_code == 401:
            raise TelegramAuthError("telegram token rejected (401)")
        r.raise_for_status()
        data = r.json()
        if not data.get("ok"):
            raise TelegramAuthError(
                f"telegram getMe failed: {data.get('description')}")

    def stop(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    # --------------------------------------------------------- api
    def poll(self, timeout: float = 25.0) -> Optional[Message]:
        """Block for one update (long-poll via offset)."""
        try:
            r = self._http().post(
                f"{self.base_url}/bot{self.token}/getUpdates",
                json={"offset": self._offset, "timeout": int(timeout),
                      "allowed_updates": ["message"]},
                timeout=timeout + 10)
        except httpx.TimeoutException:
            return None
        r.raise_for_status()
        data = r.json()
        if not data.get("ok"):
            return None
        for update in data.get("result", []):
            self._offset = max(self._offset, update.get("update_id", 0) + 1)
            raw = update.get("message")
            if raw is None:
                continue
            chat_id = str(raw.get("chat", {}).get("id", ""))
            if not chat_id:
                continue
            media = []
            if raw.get("photo"):
                media.append("photo")
            if raw.get("document"):
                media.append(raw.get("document", {}).get("file_name", "file"))
            return Message(
                chat_id=chat_id,
                text=str(raw.get("text") or ""),
                sender=str(raw.get("from", {}).get("username", "")),
                platform="telegram",
                ts=raw.get("date", time.time()),
                media=media)
        return None

    def send(self, chat_id: str, text: str) -> None:
        r = self._http().post(
            f"{self.base_url}/bot{self.token}/sendMessage",
            json={"chat_id": chat_id, "text": text}, timeout=30)
        r.raise_for_status()