# mem20AIonbordz

Generate verified onboarding packs for newly-hired mem20 agents.

A new agent arriving on this box needs the same thing a new employee needs: a
hire guide, a map of the building, the rules, and instructions for making
himself persistent. This generates all of it — **from probes of the actual
host**, not from a hardcoded document.

That distinction is the whole point. An onboarding guide is only useful if it is
true. The recurring failure on this box is a confident claim about the
environment that turns out to be wrong (Unity "isn't installed" when it is, on a
licence path nobody remembered). Every path, command, port and subsystem in a
generated pack is read off this machine at generation time and stamped with the
time it was verified.

## Install

```bash
/root/.venv/bin/pip install -e . --no-deps
```

## Use

```bash
mem20aionbordz new "Fledge Alpha"          # generate a pack
mem20aionbordz verify <pack-dir>           # re-check every claim, report drift
mem20aionbordz pin <pack-dir>              # prepare pinned-block delivery
mem20aionbordz list                        # show generated packs
```

`new` accepts `--role`, `--mission`, `--capability` (repeatable), `--value`
(repeatable), `--voice` and `--out`.

Python invocation works identically:

```bash
python -m mem20AIonbordz new "Fledge Alpha"
```

## What it writes

Six files into `~/mem20-onboarding/<agent-slug>/` by default:

| File | Contents |
|---|---|
| `HIRE-GUIDE.md` | identity, role, mission, voice, first-session checklist |
| `ORIENTATION.md` | verified paths, commands with versions, listening ports attributed to owning units, systemd units |
| `GOVERNANCE.md` | the standing rules, each with the reason it exists |
| `SELF-MODEL.md` | the exact self-model calls and maintenance cadence |
| `FIND-ME.txt` | the one file to read first, and where everything is |
| `onboarding.json` | every recorded claim beside its verification time |

`pin` additionally writes `PIN-REQUESTS.json`.

## Ports carry their owner

The orientation table attributes every listening port to its owning systemd unit
by reading `/proc/<pid>/cgroup`, and merges IPv4 and IPv6 binds of the same port
into one row. This exists because a new agent taking a port that belongs to a
service it does not own causes an outage. Where a unit cannot be attributed the
row says **unattributed — verify before use** rather than guessing.

## Drift detection

`verify` re-probes every recorded fact and reports what no longer matches,
exiting non-zero when it finds any. Two deliberate choices:

- **Ports and unit states are reported but never counted as drift.** They change
  by design; a verifier that fails on them is useless.
- **Verify never rewrites the pack.** A verifier that edits what it inspects is
  the failure mode the governance rules forbid.

## Pinned-block delivery

`pin` writes the exact `mem20_memory_pin_block` calls needed to make the hire
guide and governance loadable at session start, immune to pruning — the same
mechanism that carries `pickle-voice` and `spacebunny-life`.

It writes them as **requests, not applied**, and says so. Those tools are exposed
to the agent running the onboarding, not to a standalone Python process, so
applying them is a deliberate handoff rather than something the script pretends
to do.

## Tests

```bash
cd /opt/mem20/mem20AIonbordz && /root/.venv/bin/python -m pytest tests -q
```

40 tests, all passing as of the last run. Bounded by design: no network, no
unbounded loops, no real sleeps. Tests that touch the host only read it.

Two regressions are locked by explicit tests: volatile port/unit facts are never
counted as drift, and `verify` never mutates the pack it inspects.

## Crosscheck note

Built after confirming no existing subsystem covers this. `mem20apprenticeshipruntimez`
(RM-036) teaches *humans* through guided execution while agents learn from
corrections — a runtime, not a pack generator. Sitemap search for "onboarding"
returns only unrelated organs.

Naming note: the distribution is `mem20aionbordz` (lowercase) while the import
package is `mem20AIonbordz`, matching the name as requested. Python handles the
mixed case fine; the lowercase distribution name keeps tooling and case-sensitive
filesystems happy.