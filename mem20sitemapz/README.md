# mem20sitemapz

A machine-readable **sitemap of the mem20 monorepo** so an agent can find the right
subsystem without being told, plus a **quiescence poller** and a **source-only snapshotter**.

Console script: `sitemap` (also runnable as `python -m mem20sitemapz`).

## Why this exists

`/opt/mem20` holds 113 top-level entries and roughly 71k files. A new agent has no
reliable way to learn what is there. This indexes the tree into
`/opt/mem20/.sitemap/sitemap.json` (machine-readable) and `/opt/mem20/SITEMAP.md`
(human/agent-readable appendix), and makes both queryable from the shell.

## Commands

```
sitemap                      # same as: sitemap build
sitemap build                # scan tree, write .sitemap/sitemap.json + SITEMAP.md
sitemap build -v             # ... and report each outside root and what it added
sitemap build --no-extra-roots   # monorepo only, ignoring every outside root
sitemap search "secret zzz"  # ranked search over the index
sitemap show mem20ops        # full detail for one subsystem
sitemap watch ...            # wait until every target agent stops working, then snapshot
sitemap snapshot             # write a source-only zip now
sitemap verify               # check a zip for corruption and secret paths
```

Bare `sitemap` with no arguments runs `build`.

## Roots outside the monorepo

Not everything real lives under `/opt/mem20`. `/sb` (the scoreboard) is a full
tool that deliberately lives elsewhere, and an index that cannot find it is
worse than useless, because it looks complete. So `build` also indexes a list of
**extra roots** — `/sb` by default, overridable with a repeated
`--extra-root DIR` or dropped with `--no-extra-roots`.

An extra root becomes **one** entry, not a directory listing. Scanning `/sb` the
ordinary way would yield entries called "backend", "frontend" and "data", which
tells a reader nothing. Instead the whole project is one entry, named after the
package that defines it (found by looking a few levels down, since its
`pyproject.toml` is not at the root), carrying:

- its real absolute path, so nobody opens the wrong directory
- `external: true` and `external_root`, and `show` prints
  `location OUTSIDE the monorepo`
- its own README summary, keywords, entry points and version

These entries get their own **"Outside the monorepo"** table in `SITEMAP.md`
and are excluded from the organ/service/other tables, so an outside project is
never presented as though it were a mem20 subsystem. The index `totals` are
recomputed after merging, so the reported estate is the estate actually indexed.

### Measured on this box

Full-depth build of `/opt/mem20` plus `/sb`: **1.75s**, 62 subsystems (61 inside
the monorepo + `mem20scoreboardz` at `/sb`), 8,159 source files, 586,732 code
lines (1,568,329 including json/markdown).

## How search works

Tokens are ANDed across ranked fields: name, entry points, keywords, directory,
module names, description, README body, subdirectories, docs, dependencies. All
tokens must match somewhere, so multi-word queries narrow rather than widen. A
name match outranks a README mention, so `sitemap search mem20ops` ranks
`mem20ops` first.

## How the poller decides an agent has stopped

A target counts as quiescent only when **all** of these hold:

1. Its CPU time did not move during the window.
2. **No CPU was burned anywhere in its process subtree** — descendants included.
   This is the load-bearing signal: an agent blocked on a `pytest` or `git`
   subprocess shows up here, and so does work delegated to child processes.
3. No in-flight tool call exists in `opencode.db` for any session other than the
   poller's own. This catches an agent waiting on a slow model call, which burns
   no local CPU and would otherwise look idle.

Quiet must hold for `--streak` consecutive windows (`--window` seconds each,
default 20s x 3). The first window only establishes a baseline and does not
count toward the streak, because silence cannot be measured without a prior
reading. A target that exits is treated as stopped.

The poller is bounded: it always terminates at `--max-wait` (default 6h) and
exits non-zero rather than waiting forever.

## Snapshot contents

The zip is **source only**. Excluded: `.git`, caches, `__pycache__`, virtualenvs,
`node_modules`, `*.egg-info`, `secrets/`, `backups/`, plus every binary, database,
model-weight and media file. Any path containing a `secrets` directory or named
`.env*`, `*.pem`, `*.key`, `auth.json` or `credentials` is dropped and counted.

Measured on this box: 8,040 files, 164 MB raw, **28.3 MB** zipped, ~29s.
`sitemap verify` re-opens the archive, runs `testzip()`, and re-scans the entry
names for secret paths.

### Known limitation

Exclusion is **path and filename based only**. This tool does not scan file
*contents* for hardcoded credentials. Before sending the archive anywhere
sensitive, run `mem20secretz` against the extracted tree.

## Files

- `src/mem20sitemapz/policy.py` — what counts as source, what never ships
- `src/mem20sitemapz/index.py` — single-pass tree scanner
- `src/mem20sitemapz/search.py` — ranked field-weighted search
- `src/mem20sitemapz/procinfo.py` — procfs and tty inspection
- `src/mem20sitemapz/watch.py` — quiescence poller
- `src/mem20sitemapz/snapshot.py` — source-only zip writer and verifier
- `src/mem20sitemapz/report.py` — markdown appendix renderer
- `src/mem20sitemapz/cli.py` — argument parsing and command dispatch

## Tests

```
/root/.venv/bin/python -m pytest tests -q
```

22 tests, all bounded: fake process tables, a fake clock, and a synthetic sqlite
`part` table. No real sleeps, no live process dependencies.

## Rebuilding the index

Run `sitemap build` after adding or removing a subsystem. Do not hand-edit
`SITEMAP.md`; it is generated.
