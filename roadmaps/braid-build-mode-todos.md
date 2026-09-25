# BRAID BUILD MODE — Distilled Construction Todos

_BUILD MODE (2026-09-09). Distilled from imagination output: Braid Final Dream (3 iters) + HER's self-imagination (6 iters, target 5). HER runs the build autonomously; the human only reloads servers, copies screenshots, and gives direction._

Canonical: `/opt/mem20/roadmaps/braid-build-mode-todos.json`

## System model (from imagination)

ONE braid core — append-only Merkle-DAG ledger (BLAKE3-256) + capability policy + audit loom — exposing ONE wire protocol + ONE UI bridge, consumed by THREE doors:

| Door | Name | Role | Imagined consumer |
|------|------|------|-------------------|
| 1 | THE REAL ONE | primary human surface (witness + structure + office/forge) | `braid_lumen` (witness view) + `braid_axiom` (structure view) |
| 2 | OPENCODE GODMODE | full creative terminal | godmode surfaces over `braid_wire` |
| 3 | QUEST 3D V-WORLD | immersive 3D walk-in | `braid_her` window + spatial nodes |

Core invariant (from dream): **atomic braided triplets** — capability token + policy snapshot + audit pre-commitment issued together, block-atomic. Each thread's partial result is the others' prerequisite.

## Milestones
- m1 — first working braid cycle: `braid_core` types + crypto + append log + engine, one end-to-end test, `examples/three_uis.rs` runs green
- m2 — three doors alive against the same braid via `braid_wire` + `braid_ui_bridge`
- m3 — braided triplets verified under concurrency (no deadlock, no corruption)
- m4 — godmode creative/destructive escalation gates live on braid policy
- m5 — quest3d spatial door reads world facts from the grounded ledger

## Build order (dependency-sorted)

### braid_core (start here — m1)
- B1 workspace + crate skeleton (mem20 repo), `lib.rs` re-exports
- B2 `crypto.rs` — ed25519 signing, BLAKE3-256, CIDs
- B3 `storage.rs` — append-only log + Merkle index (3-hop-to-genesis proofs)
- B4 `engine.rs` — `braid_write(op, proof)` + `braid_read(query, cap)` core loop
- B5 `policy.rs` — PolicySnapshot + capability evaluation (from `policy_seed.toml`)
- B6 `intent.rs` — IntentStrand **to stub only** (out of scope until triplets proven)
- B7 `context.rs` — BraidContext trait + mock
- B8 `tests/integration.rs` — FIRST end-to-end test (write→proof→read, one identity)
- B9 `braid_keys` — DID:key derivation, session macaroons
- B10 `policy_seed.toml` — genesis policy, godmode escalation boundary

### braid_wire (m2)
- W1 `protocol.rs` — framing (HTTP/gRPC + websocket bridging)
- W2 `messages.rs` — braided-triplet message contracts
- W3 `server.rs` — surface for the three UIs
- W4 concurrency test — strands interleave without deadlock

### braid_ui_bridge (m2)
- U1 `frontdoor.rs` — one Router every door consumes
- U2 lumen/axiom/her read-view contracts
- U3 every door request carries the braid macaroon (no auth islands)

### examples (validates m1 + m3)
- E1 `examples/three_uis.rs` — single binary, all three doors, one braid
- E2 smoke harness — 3-command re-run after each milestone

### Door 1 (m2)
- D1.1 `braid_lumen/src/witness.rs` — continuous witness scroll
- D1.2 `braid_axiom/src/structure.rs` — topology view of same DAG
- D1.3 single-SPA shell ONE base URL; D1.4 existing live surfaces (no rewrites); D1.5 planned features; D1.6 audit acceptance

### Door 2 (m4)
- D2.1 godmode contract bound to policy tokens; D2.2 godmode surfaces; D2.3 creative/destructive escalation gates; D2.4 same auth; D2.5 acceptance

### Door 3 (m5)
- D3.1 `braid_her/src/window.rs`; D3.2 WebXR shell (existing pipeline, no new engine); D3.3 world facts = ledger facts; D3.4 agents-as-natives; D3.5 voice/TTS; D3.6 Quest 3 acceptance

## Next step
m1: create `braid_core` skeleton, implement B1–B8 + E1 until `examples/three_uis.rs` runs green end-to-end.