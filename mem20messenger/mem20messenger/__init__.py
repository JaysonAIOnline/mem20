"""mem20messenger — mem20 native messenger backend.

Replacement for the messenger service: FastAPI accounts, a WebSocket bot
proxy with continuous per-chat sessions, a 24-bot roster from the mem20
profiles, and a REST chat endpoint, all on :8000. State lives under
/home/.mem20/messenger (config dir + SQLite account DB).

No legacy runtime references remain; everything talks through the mem20
substrate (get_backend / AgentCore / Profiles).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from mem20agentz import __version__ as agz_version
from mem20agentz._substrate import get_backend
from mem20agentz.profiles import Profiles

# ---------------------------------------------------------------- paths
DATA_ROOT = Path.home() / ".mem20" / "messenger"
DATA_ROOT.mkdir(parents=True, exist_ok=True)
ACCOUNTS_DB = DATA_ROOT / "accounts.db"
LEDGER_NS = "mem20messenger"

SESSION_PREFIX = "msgr:"
PAIRING = 8  # channels a token may open concurrently

BUILTIN_ROSTER = [
    "advertising", "analyst", "assistant", "betatesting", "blendie",
    "business", "ceo", "cloud", "coach", "coder", "gamemaster", "github",
    "jayson", "kickstarter", "mem20", "mem20-bot", "qamaster", "radar",
    "releasecoach", "research", "shrink", "skillresearcher", "unito",
    "webdev",
]

# ------------------------------------------------------------------ db
_conn = sqlite3.connect(str(ACCOUNTS_DB), check_same_thread=False)
_conn.execute(
    "CREATE TABLE IF NOT EXISTS accounts ("
    " username TEXT PRIMARY KEY, pwhash TEXT, created REAL)"
)
_conn.execute(
    "CREATE TABLE IF NOT EXISTS sessions ("
    " token TEXT PRIMARY KEY, username TEXT, expires REAL)"
)
_conn.commit()
_db_lock = threading.Lock()


def _hash_password(password: str, salt: Optional[str] = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(),
                                 120_000).hex()
    return f"{salt}${digest}"


def _verify_password(password: str, stored: str) -> bool:
    salt, _, digest = stored.partition("$")
    return hmac.compare_digest(_hash_password(password, salt).split("$", 1)[1],
                               digest)


def _register(username: str, password: str) -> dict:
    if not (3 <= len(username) <= 32 and re_safe(username)):
        return {"ok": False, "error": "username must be 3-32 [A-Za-z0-9._-]"}
    if len(password) < 8:
        return {"ok": False, "error": "password must be >= 8 chars"}
    with _db_lock:
        cur = _conn.execute("SELECT username FROM accounts WHERE username=?",
                            (username,))
        if cur.fetchone():
            return {"ok": False, "error": "username taken"}
        _conn.execute("INSERT INTO accounts (username,pwhash,created)"
                      " VALUES (?,?,?)",
                      (username, _hash_password(password), time.time()))
        _conn.commit()
    token = _issue_token(username)
    return {"ok": True, "username": username, "token": token}


def _login(username: str, password: str) -> dict:
    with _db_lock:
        cur = _conn.execute("SELECT pwhash FROM accounts WHERE username=?",
                            (username,))
        row = cur.fetchone()
    if not row or not _verify_password(password, row[0]):
        return {"ok": False, "error": "bad credentials"}
    return {"ok": True, "username": username, "token": _issue_token(username)}


def _issue_token(username: str) -> str:
    token = secrets.token_urlsafe(32)
    with _db_lock:
        _conn.execute("DELETE FROM sessions WHERE username=?", (username,))
        _conn.execute("INSERT INTO sessions (token,username,expires)"
                      " VALUES (?,?,?)",
                      (token, username, time.time() + 30 * 86400))
        _conn.commit()
    return token


def _user_for_token(token: str) -> Optional[str]:
    if not token:
        return None
    with _db_lock:
        cur = _conn.execute(
            "SELECT username FROM sessions WHERE token=? AND expires>?",
            (token, time.time()))
        row = cur.fetchone()
    return row[0] if row else None


def re_safe(s: str) -> bool:
    return all(c.isalnum() or c in "._-" for c in s)


# ---------------------------------------------------------------- roster
def roster(backend=None) -> list[str]:
    try:
        known = Profiles(backend=backend or get_backend()).list()
    except Exception:  # noqa: BLE001
        known = []
    merged = [p for p in known if p in BUILTIN_ROSTER]
    for name in BUILTIN_ROSTER:
        if name not in merged:
            merged.append(name)
    return merged


# ---------------------------------------------------------------- agent
def _history(backend, chat_id: str, k: int = 20) -> list[dict]:
    if backend is None:
        return []
    try:
        msgs = backend.session_messages(LEDGER_NS, SESSION_PREFIX + chat_id,
                                        k=k)
    except Exception:  # noqa: BLE001
        return []
    out = []
    for m in msgs:
        content = m.get("content", "") or ""
        direction, _, rest = content.partition(":")
        if direction not in ("in", "out") or not rest:
            continue
        text = rest.partition(" ")[2] or rest
        role = "user" if direction == "in" else "assistant"
        out.append({"role": role, "content": text})
        if len(out) >= k:
            break
    return out[-k:]


class _Proxy:
    """One AgentCore per (bot, chat) with a stable msgr:<chat> transcript."""

    def __init__(self, backend=None):
        self._b = backend or get_backend()
        self._cores: dict[tuple[str, str], object] = {}
        self._lock = threading.Lock()

    def _core(self, bot: str, chat_id: str):
        from mem20agentz.agentz import AgentCore
        return AgentCore(backend=self._b, profile=bot, model=None,
                         approvals="auto", toolsets=("skills",),
                         history=_history(self._b,
                                          f"{bot}:{chat_id}"))

    def chat(self, bot: str, chat_id: str, message: str) -> str:
        if bot not in roster(self._b):
            raise ValueError(f"unknown bot '{bot}'")
        key = (bot, chat_id)
        with self._lock:
            if key not in self._cores:
                self._cores[key] = self._core(bot, chat_id)
            core = self._cores[key]
        try:
            result = core.run(message)
        except Exception as exc:  # noqa: BLE001
            return f"[messenger] error: {exc}"
        reply = result.text or "[messenger] no reply produced"
        if result.blocked:
            reply = "[messenger] run blocked by approvals"
        self._ledger(bot, chat_id, message, reply)
        return reply

    def _ledger(self, bot: str, chat_id: str, message: str, reply: str) -> None:
        sid = f"{SESSION_PREFIX}{bot}:{chat_id}"
        try:
            self._b.session_append(LEDGER_NS, sid, "user", f"in:{sid} {message}")
            self._b.session_append(LEDGER_NS, sid, "assistant",
                                   f"out:{sid} {reply}")
        except Exception:  # noqa: BLE001
            pass

    def close(self) -> None:
        self._cores.clear()


# ------------------------------------------------------------ app + api
app = FastAPI(title="mem20 messenger", version="1.0.0")
proxy = _Proxy()


class _Creds(BaseModel):
    username: str
    password: str


class _Chat(BaseModel):
    bot: str
    message: str
    chat_id: str = ""


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    bots = roster()
    rows = "".join(
        f"<li><strong>{b}</strong> - {_esc(_identity(b))}</li>"
        for b in bots)
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>mem20 messenger</title>
<style>
 body{{font-family:system-ui,sans-serif;margin:2rem;background:#0f1115;color:#e6e6e6}}
 h1{{font-size:1.3rem}} section{{margin:1.5rem 0}}
 h2{{font-size:1rem;color:#9aa4b1;border-bottom:1px solid #262b33;padding-bottom:.25rem}}
 ul{{padding-left:1.2rem}} li{{margin:.15rem 0}}
 code{{background:#1b1f27;padding:.05rem .4rem;border-radius:4px}}
</style></head><body>
<h1>mem20 messenger</h1>
<p>service <code>mem20messenger</code> &middot; agentz <code>{_esc(agz_version)}</code>
&middot; roster {len(bots)} bots &middot; state <code>{_esc(str(DATA_ROOT))}</code></p>
<section><h2>roster</h2><ul>{rows}</ul></section>
<section><h2>api</h2><ul>
<li><code>POST /api/register</code> (username,password) &rarr; token</li>
<li><code>POST /api/login</code> &rarr; token</li>
<li><code>GET /api/roster</code> (Bearer token)</li>
<li><code>POST /api/chat</code> (bot,message,chat_id) (Bearer token)</li>
<li><code>WS /ws/&lt;bot&gt;?token=&lt;tok&gt;</code> (Bearer token)</li>
</ul></section>
<section><h2>health</h2><p><code>/api/health</code></p></section>
</body></html>"""


@app.get("/api/health")
def health() -> dict:
    return {"service": "mem20messenger", "ok": True,
            "agentz": agz_version, "roster": len(roster()),
            "uptime_s": round(time.time() - _started, 1)}


@app.post("/api/register")
def register(creds: _Creds) -> JSONResponse:
    out = _register(creds.username, creds.password)
    code = 200 if out["ok"] else 400
    return JSONResponse(out, status_code=code)


@app.post("/api/login")
def login(creds: _Creds) -> JSONResponse:
    out = _login(creds.username, creds.password)
    code = 200 if out["ok"] else 401
    return JSONResponse(out, status_code=code)


@app.get("/api/roster")
def api_roster(token: str = Query("", alias="token")) -> JSONResponse:
    if not token or _user_for_token(token) is None:
        return JSONResponse({"ok": False, "error": "unauthorized"}, 401)
    return JSONResponse({"ok": True, "bots": roster()})


@app.post("/api/chat")
def api_chat(body: _Chat, token: str = Query("", alias="token")) -> JSONResponse:
    if not token or _user_for_token(token) is None:
        return JSONResponse({"ok": False, "error": "unauthorized"}, 401)
    message = (body.message or "").strip()
    if not message:
        return JSONResponse({"ok": False, "error": "message required"}, 400)
    chat_id = body.chat_id or f"c{secrets.token_hex(4)}"
    if not _chat_safe(chat_id):
        return JSONResponse({"ok": False, "error": "bad chat_id"}, 400)
    try:
        reply = proxy.chat(body.bot, chat_id, message)
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, 400)
    return JSONResponse({"ok": True, "bot": body.bot, "reply": reply,
                         "chat_id": chat_id})


@app.websocket("/ws/{bot}")
async def websocket_chat(ws: WebSocket, bot: str) -> None:
    token = ws.query_params.get("token", "")
    user = _user_for_token(token)
    if not user:
        await ws.close(code=4401)
        return
    if bot not in roster():
        await ws.close(code=4404)
        return
    await ws.accept()
    chat_id = f"ws{secrets.token_hex(4)}"
    await ws.send_text(json.dumps({"type": "hello",
                                   "bot": bot, "chat_id": chat_id}))
    try:
        while True:
            raw = await ws.receive_text()
            message = (raw or "").strip()
            if not message:
                continue
            reply = await _run(bot, chat_id, message)
            await ws.send_text(json.dumps({"type": "reply", "bot": bot,
                                           "reply": reply}))
    except WebSocketDisconnect:
        return


async def _run(bot: str, chat_id: str, message: str) -> str:
    return await _run_in_thread(bot, chat_id, message)


async def _run_in_thread(bot: str, chat_id: str, message: str) -> str:
    import asyncio
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(None, proxy.chat, bot, chat_id,
                                          message)
    except ValueError as exc:
        return f"[messenger] unknown bot: {exc}"


# ---------------------------------------------------------------- helpers
def _chat_safe(raw: str) -> bool:
    return bool(raw) and len(raw) <= 64 and all(
        c.isalnum() or c in "-_." for c in raw)


def _esc(text: str) -> str:
    import html
    return html.escape(str(text))


def _identity(bot: str) -> str:
    try:
        return Profiles().ensure(bot).identity or bot
    except Exception:  # noqa: BLE001
        return bot


_started = time.time()


def run(host: str = "0.0.0.0", port: int = 8000) -> None:
    import uvicorn
    cfg = getattr(__import__("mem20agentz.config", fromlist=["load_config"]),
                  "load_config", lambda: {})()
    p = 8000
    try:
        p = int(cfg.get("messenger", {}).get("port", 8000))
    except Exception:  # noqa: BLE001
        p = 8000
    uvicorn.run(app, host=host, port=port or p, log_level="info")


if __name__ == "__main__":
    run()