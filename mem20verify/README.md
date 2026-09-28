# mem20verify

Verification toolkit for the mem20 estate. Every check executes something real
against the live system or the real source tree. A check that cannot run
reports the error and exits non-zero; it never reports a pass it did not earn.

This exists because claims were being trusted instead of verified. The bridge
circuit breaker shipped with both `if/else` arms byte-identical, so it never
opened while its own comment said it did. The PII scanner silently rewrote
stored data because a regex had no word boundaries. Neither was caught by
reading; both were caught by executing.

## Install

```bash
/root/.venv/bin/pip install -e /opt/mem20/mem20verify
```

## Checks

### `mem20verify systemd`
Verifies the persistence standing rule against the running system: unit file
exists, `is-enabled`, `is-active`, `MainPID` present, `MainPID` has `PPID=1`,
`Restart=on-failure`, and exactly one process listening on the port parsed from
`ExecStart`. Listener detection reads `/proc/net/tcp` and `/proc/*/fd` rather
than shelling out to `ss`, so it works where `ss` is absent.

```bash
mem20verify systemd                 # default five units
mem20verify systemd --unit my.service --restart
```

`--restart` actually restarts each unit and waits for it to return to active.

**Verified 2026-09-24, immediately after an unplanned host reboot:**

```
systemd sweep: 5/5 compliant
  OK    mem20corez-serve.service   pid=684  ppid=1 port=8006 restart=on-failure
  OK    mem20mktz-serve.service    pid=686  ppid=1 port=8004 restart=on-failure
  OK    mem20gamez.service         pid=685  ppid=1 port=8007 restart=on-failure
  OK    mem20yetiz.service         pid=688  ppid=1 port=8005 restart=on-failure
  OK    mem20googlez-serve.service pid=1161 ppid=1 port=8002 restart=on-failure
```

### `mem20verify dataintegrity`
Stores each payload through the real `memory_engine.remember()` into a temp
ledger and asserts the stored content is byte-identical to the input. Also
asserts `detect_secrets()` does not fire on a git SHA-1, a 64-hex content hash,
a braid CID, or a UUID.

```bash
mem20verify dataintegrity
```

Payloads include unicode, embedded newlines and tabs, quotes, a 20 000-character
string, the empty string, and whitespace-only.

**Verified:** 11 payloads checked, 11 byte-identical, 0 corruptions, 0 false
positives.

### `mem20verify outage`
Exercises the real `Bridge.run()` loop against a transport that always raises,
and asserts the breaker contract: trips on the third consecutive error, emits
exactly one trip event, spaces re-probes by the full `TRIP_RETRY_INTERVAL_S`,
writes nothing to the ledger, and resets after a successful poll.

```bash
mem20verify outage
```

**Verified:** strikes 3, retry interval 1200.0s, 1 trip event, 0 ledger rows,
re-probes `[1200.0, 1200.0, 1200.0, 1200.0, 1200.0, 1200.0]`, reset `True`.

### `mem20verify tests`
Runs each package's suite **from its own root**, which is required: the outer
`mem20unitiz/` directory has no `__init__.py`, so running pytest from
`/opt/mem20` makes it shadow the real package and collection fails. Packages
with their own `.venv` are run with that interpreter.

```bash
mem20verify tests --package mem20gamez
mem20verify tests --json > /tmp/results.json
```

### `mem20verify baseline`
Decides whether a failure is pre-existing by restoring the package to its
**git index** state, re-running the failing test, then restoring the working
tree. The index is the correct baseline here, not `HEAD`: much of this tree is
staged-but-uncommitted, so `HEAD` predates the files and `git show HEAD:<path>`
fails outright.

The working tree is backed up before any write and restored in a `finally`
block, so an interrupted run cannot leave your files modified. `git stash` is
deliberately not used — it can collide with an unrelated stash.

```bash
mem20verify baseline mem20agentz --failed-from /tmp/results.json
```

### `mem20verify shadow`
Reports which packages are **shadowed** — outranked by a same-named directory
— when `/opt/mem20` is the working directory. Running `python -m` puts the
working directory at `sys.path[0]`, so the outer checkout directory (which has no
`__init__.py`) registers as a PEP 420 namespace portion and can win over the real
package.

The probe runs in a **fresh interpreter started from the estate root**. This
matters: `python <script>` puts the *script's* directory on `sys.path[0]`
instead, so a probe run that way measures the wrong thing and reports everything
clean. That bug produced a sweep that claimed zero shadowed packages while 24
were affected. `test_probe_uses_cwd_not_script_dir` guards it.

Two verdicts are reported separately, because the remedies differ:

| Verdict | Meaning | Remedy |
|---|---|---|
| `SHADOWED` | imports fine on its own, outranked from the estate root | run it from its own package root |
| `UNREACH` | not importable from this interpreter at all | often installed only in its own venv; **a layout change will not fix it** |

**Layout is not the cause.** `mem20mktz` is `src/`-layout and still shadowed;
`mem20cliz` is nested-flat and resolves. What decides it is whether a regular
package is reachable on a path entry — PEP 420 makes a regular package beat a
namespace portion found earlier. Packages registered through an appended
`sys.meta_path` finder lose, because `PathFinder` has already returned the
namespace by then.

```bash
mem20verify shadow
mem20verify shadow --package mem20langz
mem20verify --json shadow > /tmp/shadow.json
```

Exits `1` when any package is shadowed or unreachable, `2` when the check cannot
run. Uses `importlib.util.find_spec` and never imports a module, so no package
code executes and nothing is written.

**Verified 2026-09-25 against the live estate:** 8 of 34 packages import with the
estate root on `sys.path`; 23 `SHADOWED`, 3 `UNREACH`.

### `mem20verify lint`
Four structural AST checks, each for a defect class that actually shipped:

| Check | The bug it catches |
|---|---|
| `identical-branches` | `if`/`else` arms that do the same thing |
| `misplaced-lookbehind` | `"sk-" + r"(?<!...)"` — the lookbehind tests against the prefix's own `-` and can never pass |
| `unbounded-loop` / `long-sleep` / `unbounded-parameter` | `while True` and `fail_for=None` in tests, which hang the whole run |
| `noop-body` | `pass`-only functions outside legitimate abstract/overload contracts |

```bash
mem20verify lint /opt/mem20/mem20agentz /opt/mem20/memory_engine
```

## Exit codes

`0` clean · `1` findings · `2` the check could not run

`2` is deliberately distinct from `1`. A check that cannot run is not a pass.

## Limitations

- The AST linters are structural heuristics. They will occasionally flag
  legitimate code; review findings, do not auto-apply.
- `baseline` temporarily rewrites the package under test. Back up anything you
  cannot lose, and do not run it concurrently with an editor saving the tree.
- `systemd` needs `systemctl` and read access to `/proc`; `dataintegrity` needs
  an importable `memory_engine`; `outage` needs `mem20agentz`. Each reports a
  real error and exits `2` when its dependency is absent.
- `tests` has a per-package timeout (default 600s) and reports a timeout as a
  failure rather than blocking.

## Verification

```
$ python -m pytest -q
70 passed in 26.32s
```
