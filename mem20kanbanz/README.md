# mem20kanbanz

**The one true mem20 kanban.** Typed client, read-only inspector, and
non-destructive migrator for the `mem20-kanban` door.

## Why this exists

The estate had **four** kanban implementations and **two** SQLite files:

| # | Implementation | Surface | Store |
|---|---|---|---|
| 1 | `mem20-kanban.service` (`kanban-mcp/web-server`) | REST + web UI on `:8221` | `kanban_3.db` |
| 2 | `kanban-mcp/mcp-server` | MCP tools over stdio | `kanban_3.db` (second writer) |
| 3 | `mem20agentz/mem20agentz/kanban.py` | Python client | reads the door |
| 4 | `kanban-server/server.js` | ad-hoc Node tool | `~/.kanban/kanban.db` (**orphan**) |

Four paths, two stores, and a real board — *Fleet HQ*, 16 tasks — that existed
only in the orphan file and was invisible to every other tool. That is the
drift this package closes.

After the merge, `mem20-kanban` wins every conflict:

* **One store.** `kanban_3.db`, owned by the `mem20-kanban.service` unit.
* **One writer.** Everything goes through the door's REST API. Nothing in
  mem20 issues an `INSERT` against that database.
* **One Python door.** This package. `mem20agentz/kanban.py` is a client of
  the same door, so both agree by construction.

## The door is authoritative

`mem20kanbanz` **never opens the kanban database.** It is an HTTP client with
a bounded timeout. An unreachable door raises `DoorError` rather than
returning an empty list, because a caller that believes it filed a task when
it did not is exactly the failure this merge exists to prevent.

```
$ mem20kanbanz health
{"door": "http://localhost:8221", "healthy": true}
```

## Commands

```sh
mem20kanbanz health                       # is the door up?
mem20kanbanz boards                       # board names
mem20kanbanz show <board>                 # columns + cards
mem20kanbanz jobs <board> [--unclaimed]   # open work
mem20kanbanz add <board> <title> [--content] [--assignee] [--tags] [--column]
mem20kanbanz claim <board> <task> <agent> [--column in_progress] [--force]
mem20kanbanz release <board> <task>
mem20kanbanz done <board> <task> [--reason] [--column]
mem20kanbanz inspect <foreign.db>         # read-only
mem20kanbanz migrate <foreign.db> [--dry-run] [--as SRC=DOOR]
```

`--json` on any command gives machine-readable output. Exit codes: `0` success,
`1` door/IO error or findings, `2` usage error — so it composes in CI.

## The claim / done lifecycle

This is the part the IRC bots drive, and it is deliberately strict.

```sh
mem20kanbanz add dev "fix the flaky test"     # a job appears
mem20kanbanz claim dev <id> crewbot           # crewbot takes it
mem20kanbanz done dev <id> --reason "green"   # crewbot reports it finished
```

* **The assignee is written before the move**, so a card is never sitting in
  the working column owned by nobody.
* **A claim on someone else's card is refused** unless `--force`. Silently
  stealing work is how two agents end up duplicating a task.
* **`done` resolves the board's own done column** from its `isDoneColumn` flag
  rather than a hardcoded name, because the boards on this box disagree
  (`done`, `Done`, `Review`).
* **`done` refuses on a board with no done column** instead of guessing.
* **`release`** drops the assignee and returns the card to the queue, so an
  agent that dies mid-job does not strand it.

## Migration does not touch the source

The data-integrity standing rule says detection must never rewrite what a human
authored. A migration is detection with teeth, so it holds to the same rule:

* The source is opened with SQLite's `file:...?mode=ro` URI. SQLite itself
  refuses the open if the file is missing or unreadable.
* Every write goes through the door REST API, so the door's invariants (WIP
  limits, landing column, positions) still hold.
* The report carries the source SHA-256 **before and after**, and
  `migrate` exits non-zero if they differ.
* Re-running a migration is idempotent: a card already present in the same
  column is skipped and reported in `skipped`, so a retry cannot duplicate
  every task.

```sh
$ mem20kanbanz inspect /root/.kanban/kanban.db
{"source": "...", "source_unchanged": true, "boards": ["Fleet HQ"],
 "columns": 5, "cards": 16, "skipped": [], "errors": []}
```

## What was added to the door

Merging exposed a real gap: a bot that claims a job had nowhere to record the
assignee. The door gained `PATCH /api/tasks/:taskId/metadata`, which **merges**
a patch into the JSON metadata blob:

* merge, not replace — recording an assignee never erases tags set at creation
* a key mapped to `null` is removed, which is how `release` works
* a non-object patch is **rejected**, so metadata stays a dict for every reader
* content and position are untouched

## Tests

```sh
cd /opt/mem20/mem20kanbanz && /root/.venv/bin/python -m pytest tests -q
```

47 tests. The door is exercised against a **real HTTP server** on an ephemeral
loopback port with a temporary SQLite file, because the whole point of this
package is the wire contract — a mocked door would only prove the mock agrees
with itself. No test can reach the live door on `:8221` or the production
database.

## Managed by

`mem20-kanban.service` (the door) and, for the IRC crew on top of it,
`mem20botz`.
