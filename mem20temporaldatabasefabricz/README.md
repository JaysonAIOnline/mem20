# mem20temporaldatabasefabricz

Bi-temporal memory for mem20. It keeps two things apart that most memory stores
conflate:

- **valid time** — when a claim was true in the world
- **known time** — when *this system* held the belief

The difference matters the moment a fact is learned late, corrected, or
retracted. A store with only a valid axis cannot answer "what did we believe at
noon?" without answering it with today's facts, and cannot distinguish "we
believed this" from "we never knew this".

## The problem it fixes

mem20's `recall_at()` was documented as a bi-temporal query. It was not. It
filtered on a single axis, and it stripped every superseded record *before*
applying the time filter. So asking "what was true at 12:00?" about a fact
learned at 10:00 and corrected at 14:00 returned **nothing** — the pre-correction
truth was unreachable through every query path.

Reproduced, fixed, and locked down by tests in
`memory_engine/tests/test_recall_at_bitemporal.py`.

## Guarantees

- **Corrections never delete.** They close the old version's *known* interval and
  append a new version. Both remain queryable forever.
- **A correction never edits valid time.** The world did not change; only our
  belief about it did.
- **At most one belief per (subject, attribute) is open at a time.** A second
  assertion is refused; use `correct` or `retract`.
- **Half-open intervals `[start, end)`.** The instant a correction lands belongs
  to the correction, not the fact it replaced.
- **Intervals are immutable once written.** Only an interval's open end may be
  closed.
- **Total, deterministic ordering.** Equal queries give byte-identical answers.
- **Idempotent ingest.** Replaying the same ledger adds nothing.
- **Tamper-evident.** Every write appends to a hash-chained event log; `verify`
  re-derives the chain and exits non-zero on any alteration.
- **Content is never duplicated.** A version stores a `value_ref` (a memory
  record id) and a content hash — never a second copy of the text.

## The four slices

Omit an axis to mean *now*; supply one to mean *then*.

| query | slice | reads as |
|---|---|---|
| `get s` | `valid_now_known_now` | current view |
| `get s --valid-at T` | `valid_then_known_now` | what was true at T, judged against everything known today — the **as-of join** |
| `get s --known-at T` | `valid_now_known_then` | what we believed at T that is still true — "were we right?" |
| `get s --valid-at T --known-at T` | `valid_then_known_then` | the historical view |

The slice names the **question**, not the answer. An empty result is an answer,
not a different question.

## CLI

```bash
mem20temporaldatabasefabricz selftest          # prove the core claims, throwaway store
mem20temporaldatabasefabricz put svc.port value 8080 --valid-from T0 --known-at T1
mem20temporaldatabasefabricz correct svc.port value 9090 --known-at T6
mem20temporaldatabasefabricz get svc.port --valid-at T3            # as-of join
mem20temporaldatabasefabricz get svc.port --valid-at T3 --known-at T3   # historical
mem20temporaldatabasefabricz slices svc.port T3    # all four at once
mem20temporaldatabasefabricz history svc.port      # every version, nothing deleted
mem20temporaldatabasefabricz explain svc.port --valid-at T3
mem20temporaldatabasefabricz export --out state.json
mem20temporaldatabasefabricz verify                # non-zero if the chain broke
mem20temporaldatabasefabricz ingest --ledger ~/.mem20/store/ledger.jsonl
```

`--db` selects the SQLite file (default `~/.mem20/temporal/temporal.db`, override
with `MEM20_TEMPORAL_DB`). Output is JSON. Subjects match **exactly** — use the
real topic string; there is no substring matching, because a temporal store
should be precise about which fact it is answering for.

## HTTP surface

```bash
mem20temporaldatabasefabricz serve --port 8791
```

Read and query. Endpoints under `/temporal/*` answer bi-temporal questions;
`/recall/*` proxy the **existing** memory retrieval read-only. This service adds
temporal questions, it does not take over recall.

## How it composes with existing retrieval

Nothing existing was replaced. The ledger stays the single authority for
content, and intervals are *derived* from the append-only ledger that already
exists — so `remember()` and `supersede()` needed no changes and cannot be
bypassed.

```python
from mem20temporaldatabasefabricz.temporal import build_engine, temporal_filter

engine = build_engine(store, memory._load_ledger())
candidates = [r["id"] for r in memory.recall_hybrid("deploy target", k=50)]
current = temporal_filter(engine, candidates, known_at="2026-10-01T00:00:00+00:00")
```

`recall`, `recall_hybrid`, `recall_semantic`, `recall_graph` and the BM25/vector
indexes all remain live and unchanged. The temporal layer restricts and reorders
their output; it never stands in for them.

## Known limitation: conflated valid time on existing data

`memory_engine.remember()` sets `valid_from = now` when a caller supplies no
explicit event time. Every existing mem20 record therefore has
`valid_from == known_from`, so the **valid** axis cannot yet distinguish a
late-arriving fact from a fresh one. This is visible in real data: ingesting the
live ledger yields 374 versions where both axes agree on all of them.

The engine reports this rather than inferring an event time it was never given.
The fix is at the call site — pass `valid_from=` to `remember()` — not something
this package can repair after the fact. New records written with an explicit
`valid_from` are placed correctly on both axes immediately.

## What was removed

The previous version of this package was generated scaffolding: 676 lines whose
"temporal" behaviour was a hardcoded dispatch on integer ids 101–230 returning
canned dictionaries, with 98 dispatch branches and zero tests. Its README
claimed conflict-safe synchronisation, backpressure, failover and a browser
command surface. None of that was implemented, and the claims are gone along
with the code. `selftest` and the test suite are what this package can actually
do.

## Tests

```bash
cd /opt/mem20/mem20temporaldatabasefabricz
python -m pytest tests -q
```

46 tests. Deterministic: an injected clock, no sleeps, no wall-clock waits.