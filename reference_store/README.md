# 00_reference_store — BUILD MANIFEST (first build of hypo-map-1)

Green-lit 2026-09-08 by Jayson. The MALIC braid's shared reference substrate
("the fountain"). Everything the rings collide over and exchange lives here and
accretes across server life so no ring ever starts blank and one failure on
ring 1 is teachable reference material on ring 3 in the same beat.

## What it replaces

The braid harness (`/root/notebooks/research/malic_harness/braid.py`) keeps
lessons only in a process-lifetime in-memory `BraidLedger.lessons` dict. That
ledger dies at process exit — the braid forgets between runs. 00_reference_store
is the persistent form of that same lesson ledger: same content hash, same
Lesson payload, but append-only on disk.

## Location

    /opt/mem20/reference_store/
        __init__.py       public surface (ReferenceStore, RefLesson, RefIndex…)
        store.py          core: content-addressed blobs + provenance + chain head
        index.py          scalar/metadata + inverted-index search
        braid.py          FountainLedger: drop-in BraidLedger adapter for the harness
        cli.py            CLI: stats / proof / push / search / get / snapshot / sweep
        demo_braid.py     end-to-end integration demo (runs real harness twice)
        test_store.py     unit suite (10 tests)
        data/             runtime store (git-ignored)

## Data model

The unit is a **RefLesson** — identical payload to the harness `Lesson`:

| field       | meaning                                              |
|-------------|------------------------------------------------------|
| category    | parse / retry / schema / auth                         |
| kind        | failure \| success                                    |
| text        | e.g. "category-parse pitfall-encoding"                |
| origin_ring | ring where the lesson was born                        |
| energy      | braid energy at write (decays per hop)                |
| hops        | hop count (HOP_MAX = 5 bound)                         |
| confidence  | confidence of the lesson                              |
| ts          | timestamp                                             |
| cid         | content address == harness `diff_id` (byte-identical) |
| ref_id      | record id (uuid)                                      |
| prior_head  | chain link to prior store head (append-only)          |
| provenance  | ordered RefHop list: origin/push/pull hops per ring    |

**Content addressing** is byte-identical to the harness `content_hash`:

    cid = sha256("category|kind|text").hexdigest()[:16]

No namespace prefix — 00 is the *persistent form of the same ledger*, so the
fountain dedupes against what the in-memory ledger already produced (verified
in the demo: harness `lessons_registry=24` == fountain `unique_cids=24`).

## Invariants

1. **Append-only** — no overwrite/delete of committed blobs. Re-push of the
   same content is a *dedupe*: it appends a provenance hop, never rewrites the
   blob (blob content asserted immutable in tests).
2. **Chain head** — each commit links `prior_head`; head persisted atomically
   (`head.json` via `os.replace`). `proof()` re-derives the chain by re-scanning
   the ledger and compares — append-only forgery shows as invalid.
3. **Dedupe by content address** — `unique_cids` counts one per content.
4. **Provenance** — every origin/push/pull hop recorded per actor+ring, so ring
   consumption is auditable mid-collision.
5. **Reentrant-safe** — `RLock` so push (which holds the lock) can nest
   `_append_ledger_line` (which re-enters the same lock).

## API

    store = ReferenceStore("/opt/mem20/reference_store/data")

    store.push(category, kind, text, origin_ring, actor, ring,
               energy, hops, confidence, ts)
        -> {"status": "committed"|"dedupe", "cid", "ref_id", "ts"}

    store.pull(cids, actor, ring) -> List[RefLesson]   # records pull hops
    store.get(cid)                -> RefLesson | None
    store.search(needle, category, kind, origin_ring, min_confidence, limit)
        -> List[RefLesson]                             # lexical + scalar filters
    store.snapshot(ring)          -> RefSnapshot       # per-ring knowledge view
    store.proof()                 -> {head, computed_head, count, valid}
    store.stats()                 -> {records, unique_cids, by_kind, by_category,
                                      origin_rings, head, proof_valid}

### Harness integration (`FountainLedger`)

Drop-in `BraidLedger` replacement: `write_back(lesson) -> bool` (dedupe flag),
persists every lesson to the fountain with provenance, seeds seen-set from the
fountain on init so rings never start blank.

## Verification (ran 2026-09-08)

* Unit: `python3 -m unittest reference_store.test_store` → **10/10 OK**
  (content addressing, harness diff_id byte-alignment, dedupe, append-only
  immutability, pull provenance, search filters, per-ring snapshot, chain proof,
  cross-instance persistence).
* Integration (`demo_braid.py`): real harness, seed=7, run twice against the
  same fountain.
  * fountain records = 24, unique cids = 24, by kind 12/12, categories 6 each,
    origin rings all four, chain proof valid.
  * cross-ring teaching confirmed: ring_d pulls teachable refs that originated
    in ring_a, in the same store lifetime.
* CLI: `stats`, `push`, `search`, get/snapshot/sweep exercised.

## Handoff to remaining phases

* malic.json "remaining scope (2) fountain ingestion" is wired: rings push/pull
  mid-collision via `FountainLedger`. Promotion to live-ring operation belongs
  to AGS-OS (phase 02), where 300 mem20agentz natives drive the rings.
* Per-ring knowledge snapshots (`store.snapshot`) feed the AGS training loop so
  the fountain → train → re-supply cycle can close.