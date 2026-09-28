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
sitemap search "secret zzz"  # ranked search over the index
sitemap show mem20ops        # full detail for one subsystem
sitemap watch ...            # wait until every target agent stops working, then snapshot
sitemap snapshot             # write a source-only zip now
sitemap verify               # check a zip for corruption and secret paths
```

Bare `sitemap` with no arguments runs `build`.

### Measured on this box

Full-depth build of `/opt/mem20`: **4.1s**, 61 subsystems, 8,067 source files,
583,654 code lines (1,556,499 including json/markdown).

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
