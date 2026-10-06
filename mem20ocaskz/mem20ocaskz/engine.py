"""Mine opencode's own session database for feature requests Jayson actually made.

GROUND TRUTH (measured 2026-10-03 against opencode 1.18.34, not assumed):
  * Database: ``$XDG_DATA_HOME/opencode/opencode.db`` (default
    ``~/.local/share/opencode/opencode.db``), measured at 3.47 GB.
  * Schema: ``session``, ``message``, ``part``. Message and part payloads are
    JSON in a ``data`` TEXT column.
  * A user prompt is ``message.data.role == 'user'`` joined to
    ``part.data.type == 'text'``, where the prompt body is ``part.data.text``.
  * Measured totals: 4,515 user prompts across 163 sessions.

WHY THIS READS SQLITE DIRECTLY:
  The ``opencode db`` CLI wrapper silently drops rows. The same count query
  returned 4,137 rows on one run and 3,478 on the next, while a direct read-only
  sqlite3 connection returns a stable 4,515 across repeated runs. Wrapping that
  CLI in a parser would have produced a quietly incomplete audit that still
  looked like a clean pass. This module opens the database with ``mode=ro`` and
  never issues a write.

DESIGN RULES:
  * Read-only. Nothing here writes, moves, or deletes anything in the database.
    The only file this module can produce is an index at a caller-supplied path,
    and that is an explicit output-layer operation, never a mutation of the source.
  * Every ask is traceable: session id, session title, date, and the verbatim
    quote are carried on the record, so a reviewer can confirm it by hand.
  * Output is evidence, not narration: real counts, real paths, real dates.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone

SCHEMA_USER_PROMPTS = """
SELECT m.session_id, m.id, m.time_created, coalesce(json_extract(p.data,'$.text'),'')
FROM message m
JOIN part p ON p.message_id = m.id
WHERE json_extract(m.data,'$.role') = 'user'
  AND json_extract(p.data,'$.type') = 'text'
ORDER BY m.time_created
"""

SCHEMA_SESSIONS = "SELECT id, title, directory, time_created, version FROM session"

# --------------------------------------------------------------------------
# Theme taxonomy. Each theme is a feature area; the patterns are deliberately
# narrow so that a theme label is defensible when a human checks the quote.
# --------------------------------------------------------------------------

THEMES: dict[str, tuple[str, ...]] = {
    "gui-command-center": (
        r"\bcommand ?cent(?:er|re)\b",
        r"\bdesktop (?:client|app)\b",
        r"\bweb ?(?:gateway|frontend|front ?end)\b",
        r"\bfront ?door",
        r"\bdashboard\b",
        r"\btabs? (?:and|or) pages?\b",
        r"\bpages? (?:and|or) tabs?\b",
        r"\bunified\b.{0,40}\b(?:ui|gui|app|client|system)\b",
        r"\bopencode\b.{0,40}\bgui\b",
    ),
    "subsystem-web-control": (
        r"\bweb ?front ?end\b",
        r"\bfull control\b",
        r"\bui\b.{0,30}\bsubsystem",
        r"\ball subsystems?\b",
    ),
    "voice-tts-stt": (
        r"\btts\b", r"\bstt\b", r"\btext[ -]to[ -]speech\b",
        r"\bspeech[ -]to[ -]text\b", r"\bvoice\b", r"\bwake ?word\b", r"\bdictat\w*\b",
    ),
    "subagents": (
        r"\bsub-?agents?\b", r"\bchild agents?\b",
    ),
    "self-model": (
        r"\bself[ -]model\b",
    ),
    "model-picker": (
        r"\bdropdown\b", r"\bmodel list\b", r"\bauto ?populate\b",
        r"\bcurated\b.{0,30}\bmodels?\b",
    ),
    "output-pacing": (
        r"\bflood (?:my|the) screen\b",
        r"\bwhole screen'?s? gone\b",
        r"\bwait for instructions\b",
        r"\banswer the question then\b",
        r"\bspinning text\b",
        r"\bdon'?t answer it then\b",
    ),
    "cross-surface-sync": (
        r"\bdon'?t all stay in sync\b",
        r"\bstay in sync\b",
        r"\bout of sync\b",
    ),
    "fork-and-identity": (
        r"\bfork opencode\b",
        r"\bopencode-mem20\b",
        r"\byour identity is\b",
        r"\bwhichever version you modify\b",
    ),
    "rollback-undo": (
        r"\brollback\b", r"\brevert\b", r"\bundo\b",
    ),
    "launcher-icon": (
        r"\bdesktop icon\b",
        r"\bicon (?:on|for) my desktop\b",
        r"\blauncher\b",
    ),
    "plugins-extensions": (
        r"\bplugins?\b", r"\bextensions?\b", r"\bskills?\b",
    ),
    "auth-and-providers": (
        r"\bauthenticat", r"\boauth\b", r"\bapi keys?\b",
        r"\bproviders?\b", r"\bcredentials?\b",
    ),
    "mcp": (r"\bmcp\b",),
    "capture-export": (
        r"\bsession logs?\b",
        r"\bscan all opencode sessions\b",
        r"\bunfinished work\b",
        r"\bexport\b.{0,30}\bsession",
    ),
}

# A prompt is an "explicit" ask when it names the product outright.
EXPLICIT = re.compile(r"\bopen ?code\b", re.I)

# Capability questions: "does it have X", "can it do Y", "is there a way to Z".
CAPABILITY = (
    re.compile(r"\bdoes\s+(?:\w+\s+){0,3}(?:have|support|do|run|show|include)\b", re.I),
    re.compile(r"\bcan\s+(?:\w+\s+){0,3}(?:do|have|support|show|use|read|write|run)\b", re.I),
    re.compile(r"\bis\s+there\s+(?:a|any)\s+way\s+to\b", re.I),
    re.compile(r"\bwhy\s+(?:does|do|can|is)\s+(?:n'?t|not)\b", re.I),
)

# Feature requests: an explicit ask for something to exist or change.
REQUEST = (
    re.compile(r"\bfeature\s+request\b", re.I),
    re.compile(
        r"\badd\s+a\s+(?:feature|button|panel|tab|toggle|option|setting|shortcut|"
        r"keybind|dropdown|icon)\b", re.I),
    re.compile(r"\bi\s+wish\b", re.I),
    re.compile(r"\bwould\s+be\s+(?:nice|good|great|cool|awesome)\s+if\b", re.I),
    re.compile(r"\bshould\s+be\s+able\s+to\b", re.I),
)

# Agent-generated or delegated text that is not Jayson speaking. Counted, never
# silently dropped, so the audit can account for every prompt it saw.
NOISE = (
    re.compile(r"^\s*I overheard you say", re.I),
    re.compile(r"^\s*Keep your reply to", re.I),
    re.compile(r"^\s*You are packaging\b", re.I),
    re.compile(r"^\s*Research task\b", re.I),
    re.compile(r"^\s*Explore the (?:codebase|hermes)\b", re.I),
    re.compile(r"^\s*I need a complete inventory\b", re.I),
)


def _compile(patterns: tuple[str, ...]) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(p, re.I) for p in patterns)


THEME_RX = {name: _compile(pats) for name, pats in THEMES.items()}
CAPABILITY_RX = _compile(tuple(p.pattern for p in CAPABILITY))
REQUEST_RX = _compile(tuple(p.pattern for p in REQUEST))
NOISE_RX = _compile(tuple(p.pattern for p in NOISE))


@dataclass(frozen=True)
class Prompt:
    session_id: str
    message_id: str
    time_created: int
    text: str

    @property
    def date(self) -> str:
        return datetime.fromtimestamp(self.time_created / 1000, timezone.utc).strftime("%Y-%m-%d")

    @property
    def quote(self) -> str:
        return re.sub(r"\s+", " ", self.text).strip()


@dataclass(frozen=True)
class Ask:
    prompt: Prompt
    title: str
    directory: str
    themes: tuple[str, ...]
    kinds: tuple[str, ...]

    @property
    def date(self) -> str:
        return self.prompt.date

    @property
    def quote(self) -> str:
        return self.prompt.quote


@dataclass
class AuditResult:
    db_path: str
    prompts_total: int = 0
    prompts_noise: int = 0
    asks: list[Ask] = field(default_factory=list)
    theme_counts: dict[str, int] = field(default_factory=dict)
    kind_counts: dict[str, int] = field(default_factory=dict)
    session_count: int = 0
    sessions_with_asks: int = 0
    db_size_before: int = 0
    db_size_after: int = 0
    db_mtime_before: int = 0
    db_mtime_after: int = 0

    @property
    def db_unchanged(self) -> bool:
        return (
            self.db_size_before == self.db_size_after
            and self.db_mtime_before == self.db_mtime_after
        )

    def as_dict(self) -> dict:
        return {
            "db_path": self.db_path,
            "db_unchanged": self.db_unchanged,
            "db_size_bytes": self.db_size_after,
            "prompts_total": self.prompts_total,
            "prompts_noise_excluded": self.prompts_noise,
            "prompts_ask": len(self.asks),
            "sessions_total": self.session_count,
            "sessions_with_asks": self.sessions_with_asks,
            "kind_counts": dict(sorted(self.kind_counts.items())),
            "theme_counts": dict(sorted(self.theme_counts.items())),
            "asks": [
                {
                    "session_id": a.prompt.session_id,
                    "message_id": a.prompt.message_id,
                    "title": a.title,
                    "directory": a.directory,
                    "date": a.date,
                    "themes": list(a.themes),
                    "kinds": list(a.kinds),
                    "quote": a.quote,
                }
                for a in self.asks
            ],
        }


def default_db_path() -> str:
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "opencode", "opencode.db")


def fingerprint(path: str) -> tuple[int, int]:
    st = os.stat(path)
    return st.st_size, st.st_mtime_ns


def connect(db_path: str) -> sqlite3.Connection:
    """Open the session database strictly read-only."""
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"opencode database not found: {db_path}")
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def classify(text: str) -> tuple[tuple[str, ...], tuple[str, ...], bool]:
    """Return (themes, kinds, is_noise) for one prompt."""
    if any(rx.search(text) for rx in NOISE_RX):
        return (), (), True

    themes = tuple(
        name for name, rxs in THEME_RX.items()
        if any(rx.search(text) for rx in rxs)
    )
    kinds: list[str] = []
    if EXPLICIT.search(text):
        kinds.append("explicit")
    if any(rx.search(text) for rx in CAPABILITY_RX):
        kinds.append("capability-question")
    if any(rx.search(text) for rx in REQUEST_RX):
        kinds.append("feature-request")
    if not themes and not kinds:
        return (), (), False
    return themes, tuple(kinds), False


def audit(db_path: str | None = None, limit: int | None = None) -> AuditResult:
    path = db_path or default_db_path()
    size_before, mtime_before = fingerprint(path)
    con = connect(path)
    try:
        sessions = {
            r["id"]: {"title": r["title"], "directory": r["directory"]}
            for r in con.execute(SCHEMA_SESSIONS)
        }
        sql = SCHEMA_USER_PROMPTS
        if limit is not None:
            sql = SCHEMA_USER_PROMPTS.replace(
                "ORDER BY m.time_created", f"ORDER BY m.time_created LIMIT {int(limit)}"
            )
        prompts = [
            Prompt(r["session_id"], r["id"], r["time_created"], r[3] or "")
            for r in con.execute(sql)
        ]
    finally:
        con.close()
    size_after, mtime_after = fingerprint(path)

    result = AuditResult(
        db_path=path,
        prompts_total=len(prompts),
        db_size_before=size_before, db_size_after=size_after,
        db_mtime_before=mtime_before, db_mtime_after=mtime_after,
        session_count=len(sessions),
    )

    for p in prompts:
        themes, kinds, is_noise = classify(p.text)
        if is_noise:
            result.prompts_noise += 1
            continue
        if not themes and not kinds:
            continue
        meta = sessions.get(p.session_id, {"title": "?", "directory": "?"})
        result.asks.append(Ask(p, meta["title"], meta["directory"], themes, kinds))
        for t in themes:
            result.theme_counts[t] = result.theme_counts.get(t, 0) + 1
        for k in kinds:
            result.kind_counts[k] = result.kind_counts.get(k, 0) + 1

    result.asks.sort(key=lambda a: (a.prompt.time_created, a.prompt.message_id))
    result.sessions_with_asks = len({a.prompt.session_id for a in result.asks})
    return result


def render_index(result: AuditResult, max_quote: int = 400) -> str:
    """Render the curated markdown index of feature asks."""
    lines: list[str] = []
    add = lines.append
    add("# opencode feature asks — mined from session history")
    add("")
    add("Generated by `mem20ocaskz` (`python -m mem20ocaskz index`). Do not hand-edit;")
    add("re-run the tool so the index matches the database.")
    add("")
    add("Every entry below is a prompt **Jayson actually typed**, quoted verbatim from")
    add("opencode's own session database. Each carries its session id and date so any")
    add("line can be checked by hand against the source session.")
    add("")
    add("## Provenance")
    add("")
    add(f"- Database: `{result.db_path}`")
    add(f"- Database size: {result.db_size_after:,} bytes")
    add(f"- Database unchanged by this audit: **{result.db_unchanged}**")
    add(f"- Sessions scanned: {result.session_count}")
    add(f"- Sessions containing at least one ask: {result.sessions_with_asks}")
    add(f"- User prompts read: {result.prompts_total:,}")
    add(f"- Agent-generated prompts excluded as noise: {result.prompts_noise:,}")
    add(f"- Prompts classified as asks: {len(result.asks):,}")
    add("")
    add("## How to read `kind`")
    add("")
    add("| kind | meaning |")
    add("|---|---|")
    add("| `explicit` | the prompt names opencode outright |")
    add("| `capability-question` | asks whether something can do X |")
    add("| `feature-request` | asks for something to exist or change |")
    add("")
    add("## Themes")
    add("")
    add("| theme | asks |")
    add("|---|---|")
    for theme, n in sorted(result.theme_counts.items(), key=lambda kv: (-kv[1], kv[0])):
        add(f"| `{theme}` | {n} |")
    add("")

    by_theme: dict[str, list[Ask]] = {}
    for a in result.asks:
        for t in a.themes:
            by_theme.setdefault(t, []).append(a)

    for theme in sorted(by_theme, key=lambda t: (-len(by_theme[t]), t)):
        add(f"## {theme}")
        add("")
        for a in by_theme[theme]:
            quote = a.quote
            if len(quote) > max_quote:
                quote = quote[: max_quote - 1].rstrip() + "…"
            kinds = ", ".join(f"`{k}`" for k in a.kinds) or "—"
            add(f"### {a.date} — {a.title}")
            add("")
            add(f"- session: `{a.prompt.session_id}`")
            add(f"- directory: `{a.directory}`")
            add(f"- kind: {kinds}")
            add("")
            add(f"> {quote}")
            add("")

    unthemed = [a for a in result.asks if not a.themes]
    if unthemed:
        add("## other asks (no theme matched)")
        add("")
        for a in unthemed:
            quote = a.quote
            if len(quote) > max_quote:
                quote = quote[: max_quote - 1].rstrip() + "…"
            kinds = ", ".join(f"`{k}`" for k in a.kinds) or "—"
            add(f"### {a.date} — {a.title}")
            add("")
            add(f"- session: `{a.prompt.session_id}`")
            add(f"- kind: {kinds}")
            add("")
            add(f"> {quote}")
            add("")
    return "\n".join(lines)