# mem20ops

Reusable operational workflows for the mem20 estate, packaged as one CLI.

> **Naming:** `mem20ops` is a deliberate, recorded exception to the estate's
> `mem20<name>z` convention (Jayson, 2026-09-24), listed in `/root/AGENTS.md`
> under the known-exceptions list. "ops" names a role over the fleet rather than
> an organ, so the `z` suffix would misname it. Do not rename.

Every command here encodes a procedure that was performed by hand at least once
during the fleet build, so the next run is a command instead of a shell session.
All commands support `--json` and return stable exit codes.

## Install

```
cd /opt/mem20/mem20ops
/root/.venv/bin/pip install -e .
```

Installing puts two commands on PATH:

- `fs-ops` — the operational workflows below
- `fs` — the fleet-wide subsystem dispatcher

Both are discoverable to `toolchest` (run `python -m toolchest refresh` to
re-inventory).

## The `fs` dispatcher

One command reaches every subsystem CLI:

```
fs                          list every subsystem and the binary behind it
fs list --json              machine-readable inventory
fs cv infer ...             runs the cv subsystem
fs corez serve ...          runs the corez subsystem
fs ops dns-audit ...        runs the fleet operations CLI
```

Subsystem names resolve loosely: `fs corez`, `fs mem20corez` and `fs-cv` all
reach the same CLI, and the child's exit code is propagated so `fs` composes in
scripts. An unknown subsystem prints the known list and exits non-zero; an
unknown option is a usage error (exit 2).

## Exit codes

| code | meaning                |
|------|------------------------|
| 0    | success                |
| 1    | operation failed       |
| 2    | usage error (argparse) |
| 3    | findings present       |
| 4    | missing credentials    |

Audit-style commands return 3 when they find something worth attention (for
example a wildcard record shadowing unlisted hosts), so they compose in CI.

## Commands

### `fs-ops cli-coverage [--timeout SECONDS]`
Audits every fleet CLI against the agreed contract: is the binary actually
installed (not merely declared), does `--help` exit 0 within a hard timeout, does
it advertise `--json`, and is its naming `fs-*` or a recorded exception. Reports
per-binary gaps and exits 3 when any gap exists. Read-only and bounded.

### `fs-ops dns-audit ZONE [--pattern REGEX]`
Inventories a Cloudflare zone: per-type counts, full record list, records
grouped by origin, email-routing record count, and wildcard detection. Exits 3
when a wildcard is present, because a wildcard silently answers every
unlisted subdomain. `--pattern` narrows the printed rows to a regex.

### `fs-ops pages-inspect [--project NAME] [--account ID] [--no-fetch]`
Lists Pages projects, or inspects one: subdomain, custom domains, deployment
history, and (unless `--no-fetch`) the live page's status, title, and headings.

### `fs-ops pages-delete PROJECT --confirm`
Deletes a Pages project and reports before/after state. Refuses to run without
`--confirm`. Always reports the remaining project list so an accidental delete is
visible immediately.

### `fs-ops stale-code PATH [PATH ...] [--match SUBSTR]`
Finds running processes that started **before** a source file was last modified.
This is the check that tells you whether a fix is actually live: an on-disk edit
does not reach a process that loaded the module earlier. Uses `ps -ww` so long
paths are never truncated.

### `fs-ops service-status UNIT`
systemd unit state, main PID, and the PID's own start time — the other half of
the stale-code question (did the unit actually restart?).

### `fs-ops verify [--repo DIR] [--lint PATH ...] [--no-tests] [--no-lint]`
Runs the test suite and lint with hard timeouts, parses real pass/fail counts,
and exits non-zero on failure. Every subprocess call is bounded; a hung test
reports exit 124 rather than blocking forever.

### `fs-ops identity-check`
Reports the store path, pinned blocks, life/voice blocks, and every memory
namespace with its owner and ACL. Parses both the legacy
`Namespace: ..., Owner: ..., ACL: {...}` metadata format and the structured
`NSMETA2` JSON format.

### `fs-ops acl-probe NAMESPACE --actor NAME [--actor NAME]`
Reports per-actor readability of a namespace. Note that the raw ledger has no
ACL layer, so this probes storage, not enforcement — the enforced path is the
MCP `memory_shared_recall` tool.

### `fs-ops lint-delta PATH [--revision REV]`
Compares ruff findings for a file against a git revision, per rule code, and
prints which findings are new versus resolved. Uses `ruff --stdin-filename` so
the baseline is analysed under the same project config as the working file;
copying a file to `/tmp` first silently applies different rules and produces a
meaningless comparison. In this repo much of the tree is staged-but-uncommitted,
so compare against the index with `--revision :` where appropriate.

## Safety properties

- Read-only by default. `pages-delete` is the only mutating command and it
  requires `--confirm`.
- Credentials come from `/opt/mem20/secrets/.env` (or the environment). Token
  values are never printed, logged, or included in any output.
- All probes run against isolated temporary stores by default, so inspecting
  never mutates the real ledger.
- Every subprocess call has a timeout.

## Tests

```
/root/.venv/bin/python -m pytest /opt/mem20/mem20ops -q
```

Network paths are tested through a fake client implementing the `CloudflareAPI`
protocol, so the suite is hermetic and does not touch Cloudflare.
