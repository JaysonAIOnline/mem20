# mem20ocaskz

Mine opencode's own session database for the feature requests Jayson actually made,
classify them by theme, and emit a traceable index.

Read-only against the database. It never writes, moves or deletes a session.

## Why this exists

Requirements written from memory are guesses. The prompts Jayson actually typed are on
disk in `opencode.db`, and nobody had mined them. This tool does that, and every ask it
reports carries its session id, date and verbatim quote so a reviewer can confirm it by
hand.

## Measured ground truth

Verified on this box on 2026-10-03 against opencode 1.18.34:

- Database: `~/.local/share/opencode/opencode.db` (3,477,164,032 bytes)
- Schema: `session`, `message`, `part`; payloads are JSON in a `data` TEXT column
- A user prompt is `message.data.role = 'user'` joined to `part.data.type = 'text'`,
  with the body at `part.data.text`
- 4,516 user prompts across 163 sessions; 243 classified as asks in 62 sessions

### Why it reads sqlite3 directly

The `opencode db` CLI wrapper silently drops rows. The same count query returned 4,137
rows on one run and 3,478 on the next, while a direct read-only sqlite3 connection
returns a stable 4,516 across repeated runs. Wrapping that CLI would have produced a
quietly incomplete audit that still looked like a clean pass. This package opens the
database with `mode=ro` and never issues a write.

Run `mem20ocaskz verify` to re-prove both properties yourself.

## Install

```
/root/.venv/bin/pip install -e /opt/mem20/mem20ocaskz
```

Console script lands at `/root/.venv/bin/mem20ocaskz`. Also runnable as
`python -m mem20ocaskz`.

## Commands

| command | what it does |
|---|---|
| `scan` | audit and report every feature ask, with counts by kind and theme |
| `search <term>` | find asks matching a term or theme (exit 1 when nothing matches) |
| `themes` | print the theme taxonomy and its regexes, so labels are auditable |
| `index` | write the curated markdown index (refuses to write inside the opencode data dir) |
| `verify` | re-prove the prompt count is stable and the database is untouched |

Useful flags: `--db PATH` (override the database), `--json` (machine-readable on `scan`
and `search`), `--limit N` (read only the first N prompts), `--show N` / `--brief`
(control quote output on `scan`).

Exit codes: `0` clean, `1` findings or no search match, `2` error.

## Example

```
mem20ocaskz scan --brief
mem20ocaskz search "subagents"
mem20ocaskz index --out /opt/mem20/roadmaps/opencode-feature-asks.md
mem20ocaskz verify --repeat 3
```

## Classification

Each prompt is labelled with:

- **kind** — `explicit` (names opencode), `capability-question` ("can it do X"),
  `feature-request` ("add a X", "I wish", "should be able to")
- **themes** — zero or more of 15 areas (`gui-command-center`, `voice-tts-stt`,
  `subagents`, `self-model`, `model-picker`, `output-pacing`, `cross-surface-sync`,
  `fork-and-identity`, `rollback-undo`, `launcher-icon`, `plugins-extensions`,
  `auth-and-providers`, `mcp`, `capture-export`, `subsystem-web-control`)

Agent-generated and delegated text (subagent task prompts, wake-word transcripts) is
detected and **counted, never silently dropped**, so the audit can account for every
prompt it read: `prompts_total = asks + noise + unclassified`.

Themes are deliberately narrow regexes. A theme label is meant to survive a human
checking the quote. `mem20ocaskz themes` prints them all for review.

## Tests

```
cd /opt/mem20/mem20ocaskz && /root/.venv/bin/python -m pytest tests -q
```

26 tests. Each builds its own tiny SQLite database, so the suite is fast, deterministic
and never depends on the real 3.47 GB file. One integration test runs against the real
database and skips cleanly when it is absent.

## Limits, stated honestly

- Theme labels are regex heuristics. They are auditable (`themes` command) and each quote
  is shown, but they are not a semantic classifier and will produce false positives on
  short prompts — `mcp` at 51 and `self-model` at 21 are the loosest.
- The index is a point-in-time snapshot. Re-run `index` after new sessions; it is not
  live.
- Only Jayson's own prompts are mined. Asks made in another tool are invisible to it.