//! door2 godmode shell (m8) — real creative + destructive surfaces over the
//! SAME ONE bridge, SAME auth, SAME wire.
//!
//! D2.1 — the godmode contract: "godmode" is NOT a static role. It is a
//! WIDER TOKEN SCOPE on door2 (Axiom): the door2 macaroons carry the full
//! creative set `read:*:*` / `write:*:*` / `invoke:*:*`, verified against the
//! same door2 DID + location as every other door — no second auth island.
//! Destructive `admin:*` ops are NOT in any door token; they only ever commit
//! through the second, human-gated macaroon (D2.3) when the human escalation
//! gate is armed on the bridge (D2.4).
//!
//! D2.2 — the godmode surfaces: `/console` (control-center parity via the real
//! registry), `/canvas` (creative read + creative write), `/evaluate` + real
//! policy snapshots (`WireOp::Policy`), `/daemon` (boot-time registry info),
//! `/playground` (creative writes OK single-token) and `/playground/reset`
//! (destructive — only via the escalated route, D2.3 boundary).
//!
//! m7's "planned" door1 surfaces (arena, tool-policy-console,
//! plugin-workspace, ipam) are mounted here for REAL on the same base URL.

use braid_keys::SessionMacaroon;
use braid_wire::{Shell, WireOp};

/// The D2.1 godmode token set. All three are issued to door2's identity
/// (same DID, same `door2` location) — the tokens ARE the godmode, not a
/// hardcoded bypass. `human` is signed by a SEPARATE human root identity.
#[derive(Debug, Clone)]
pub struct GodmodeTokens {
    /// door2 creative read scope: `read:*:*` (canvas / evaluate / playground /
    /// console / daemon reads).
    pub read: SessionMacaroon,
    /// door2 creative write scope: `write:*:*` (canvas / playground writes).
    /// Single-token creative ops DO commit; `admin:*` never rides here.
    pub write: SessionMacaroon,
    /// the human escalation macaroon: `admin:destroy:*`, signed by the human
    /// root identity, bound to the `human-escalation` location. Destructive
    /// ops commit ONLY when this is attached (D2.3).
    pub human: SessionMacaroon,
}

impl GodmodeTokens {
    pub fn new(read: SessionMacaroon, write: SessionMacaroon, human: SessionMacaroon) -> Self {
        Self { read, write, human }
    }
}

/// Chain the door2 godmode surfaces onto the ONE bridge shell.
///
/// Routes (all keyless; every token stays server-side):
/// - `GET  /godmode`        → the godmode SPA (keyless page)
/// - `GET  /console`        → WireOp::Registry (control-center parity)
/// - `GET  /daemon`         → WireOp::Registry (boot-time server info)
/// - `GET  /canvas`         → WireOp::Read (creative canvas, `write:note`)
/// - `POST /canvas`         → `write:note` via the door2 write token (creative)
/// - `GET  /evaluate`       → WireOp::Policy cap=None (full real rule list)
/// - `POST /evaluate`       → real policy verdict for `{ "cap": … }`
/// - `GET  /playground`     → WireOp::Read (playground creative reads)
/// - `POST /playground`     → `write:note` (creative single-token OK)
/// - `POST /playground/reset` → escalated `admin:destroy` (D2.3 boundary —
///   refuses without the human token, commits double-triplet with it)
pub fn door2_shell(shell: Shell, tokens: &GodmodeTokens, snapshot: &str) -> Shell {
    shell
        .page("/godmode", include_str!("../assets/godmode.html"))
        .op("/console", WireOp::Registry, tokens.read.clone())
        .op("/daemon", WireOp::Registry, tokens.read.clone())
        .op(
            "/canvas",
            WireOp::Read { snapshot: snapshot.into(), op_filter: Some("write:note".into()) },
            tokens.read.clone(),
        )
        .forge_op("/canvas", tokens.write.clone(), "write:note")
        .op(
            "/evaluate",
            WireOp::Policy { snapshot: snapshot.into(), cap: None },
            tokens.read.clone(),
        )
        .eval("/evaluate", tokens.read.clone(), snapshot)
        .op(
            "/playground",
            WireOp::Read { snapshot: snapshot.into(), op_filter: Some("write:note".into()) },
            tokens.read.clone(),
        )
        .forge_op("/playground", tokens.write.clone(), "write:note")
        .escalated("/playground/reset", tokens.write.clone(), tokens.human.clone(), "admin:destroy")
}

/// Mount m7's "planned" door1 surfaces as REAL routes on the same base URL
/// (D1.5 planned→live): arena, tool-policy console, plugin workspace, ipam.
///
/// Routes (all keyless; read via a bridge-held read token):
/// - `GET /arena`        → WireOp::Read (shared creative arena, no filter)
/// - `GET /tool-policy`  → WireOp::Policy cap=None (full real rule list)
/// - `POST /tool-policy` → real policy verdict for `{ "cap": … }`
/// - `GET /workspace`    → WireOp::Read (`write:plugin` workspace)
/// - `GET /ipam`         → WireOp::Registry (identity-policy-action map)
pub fn mount_planned_surfaces(
    shell: Shell,
    read_token: SessionMacaroon,
    snapshot: &str,
) -> Shell {
    shell
        .op(
            "/arena",
            WireOp::Read { snapshot: snapshot.into(), op_filter: None },
            read_token.clone(),
        )
        .op(
            "/tool-policy",
            WireOp::Policy { snapshot: snapshot.into(), cap: None },
            read_token.clone(),
        )
        .eval("/tool-policy", read_token.clone(), snapshot)
        .op(
            "/workspace",
            WireOp::Read { snapshot: snapshot.into(), op_filter: Some("write:plugin".into()) },
            read_token.clone(),
        )
        .op("/ipam", WireOp::Registry, read_token)
}