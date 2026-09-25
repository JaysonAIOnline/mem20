"""Import agent transcripts as sessions (mem20agentz sub-phase 2.10).

`import_agent` ingests a Claude Code / Codex transcript (JSONL or a JSON
list/object) and persists it as a normal mem20agentz session — `session_add`
for the container, then one `session_append` per message — so imported
conversations show up in `sessions list`, survive `backup export`, and are
searchable in the ledger exactly like native ones.

Shapes understood (kind auto-detected otherwise):
  * Claude Code: JSONL lines `{"type": "user|assistant", "message":
    {"content": "<text>" | [{"type":"text","text":...}]}}`.
  * Codex / generic: JSON list (or object with `messages`) of
    `{"role": "user|assistant", "content": "<text>"}`.
"""

from __future__ import annotations

import json
import pathlib
import secrets
from typing import Optional

from .profiles import namespace_for

MAX_ENTRIES = 5000


def _kv_lines(text: str) -> list[dict]:
    lines = []
    for raw in text.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            lines.append(json.loads(raw))
        except ValueError:
            break
    return lines or ([] if text.strip() else [])


def _claude_shape(entry: dict) -> Optional[tuple[str, str]]:
    if "type" not in entry or "message" not in entry:
        return None
    kind, message = entry.get("type"), entry.get("message")
    if kind not in ("user", "assistant", "system"):
        return None
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, list):
            bits = [str(part.get("text", "")) for part in content
                    if isinstance(part, dict)]
            content = "\n".join(bits)
        return kind, str(content or "")
    return kind, str(message or "")


def _codex_shape(entry: dict) -> Optional[tuple[str, str]]:
    role, content = entry.get("role"), entry.get("content")
    if role not in ("user", "assistant", "system"):
        return None
    if isinstance(content, list):
        bits = [str(part.get("text", "")) for part in content
                if isinstance(part, dict)]
        content = "\n".join(bits)
    return role, str(content or "")


def _norm_role(role: str) -> str:
    return "assistant" if role == "system" else role


def _detect(entries: list[dict]) -> str:
    for entry in entries:
        if _claude_shape(entry) is not None:
            return "claude"
        if _codex_shape(entry) is not None:
            return "codex"
    return "claude"


def import_agent(backend, path: str, profile: str = "mem20",
                 kind: str = "auto",
                 session_id: Optional[str] = None) -> dict:
    p = pathlib.Path(path)
    if not p.exists():
        return {"ok": False, "error": f"no such transcript: {path}"}
    raw = p.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except ValueError:
        entries = _kv_lines(raw)
    else:
        if isinstance(data, dict):
            data = data.get("messages", data.get("entries", [data]))
        entries = data if isinstance(data, list) else []
    picked = kind if kind != "auto" else _detect(entries)
    prepared = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if picked == "codex":
            pair = _codex_shape(entry)
        else:
            pair = _claude_shape(entry)
        if pair is None:
            continue
        role, text = pair
        if not text.strip():
            continue
        prepared.append({"role": _norm_role(role), "text": text.strip()})
        if len(prepared) >= MAX_ENTRIES:
            break
    if not prepared:
        return {"ok": False, "error": "no importable messages found",
                "kind": picked, "entries": 0}
    sid = session_id or f"im-{secrets.token_hex(4)}"
    backend.namespace_ensure(namespace=namespace_for(profile))
    backend.session_add(profile=profile, session_id=sid,
                        title=f"imported:{picked}:{p.stem}")
    count = 0
    for msg in prepared:
        backend.session_append(profile=profile, session_id=sid,
                               role=msg["role"], text=msg["text"])
        count += 1
    return {"ok": True, "kind": picked, "session_id": sid,
            "profile": profile, "entries": count}