//! braid_wire message contracts.
//!
//! The wire carries ONE envelope type for every op a door can issue. Reads and
//! writes travel in the same shape so a single bridge/router handles them
//! uniformly; the braided triplet (cap token + policy snapshot + audit
//! pre-commitment) is bound at the ENGINE on write, and echoed on responses as
//! evidence.

use serde::{Deserialize, Serialize};

use braid_core::engine::BraidedTriplet;

/// Wire protocol version marker.
pub const WIRE_VERSION: &str = "braid/1";

/// Everything on the wire is one of these.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum WireOp {
    /// braid_write — commit a new node (op/payload form).
    Write {
        snapshot: String,
        op: String,
        target: String,
        payload: serde_json::Value,
    },
    /// braid_read — capability-gated read of committed nodes.
    Read {
        snapshot: String,
        #[serde(default)]
        op_filter: Option<String>,
    },
    /// Read a single node by CID (witness driver).
    Get {
        snapshot: String,
        cid: String,
    },
    /// Prove a node: return its Merkle spine back to genesis.
    Prove { cid: String },
    /// door3 quest3d — braid_read returning world-state to spatial nodes.
    /// The response is a spatial `WorldScene` (proven facts with positions)
    /// + ledger presence + the resonance window.
    World { snapshot: String },
    /// door3 quest3d (m9) — commit a SPATIAL FACT into the ONE ledger through
    /// the same braided-triplet path as every write. `op` is the capability the
    /// door token must grant (creative: `write:world`); `target` names the
    /// object / world region. The committed node is an ordinary braid node, so
    /// the walk-in derives it as a PROVEN fact (deterministic position) and the
    /// resonance window threads it onto the spine. The response echoes the
    /// freshly composed WorldScene + window + presence. Destructive spatial
    /// ops (admin:* target) take the same human-gated escalation path.
    Spatial {
        snapshot: String,
        op: String,
        target: String,
        payload: serde_json::Value,
    },
    /// Bare health/status probe used by the smoke harness.
    Health,
    /// braid_policy — the REAL tool-policy surface (eval tasks, tool-policy
    /// console). `cap == None` returns the full serialized `PolicySnapshot`
    /// (rule list); `cap == Some` returns a real `evaluate_str` verdict for
    /// that capability under the registered snapshot. Same frozen authority
    /// the engine binds into every write triplet.
    Policy {
        snapshot: String,
        #[serde(default)]
        cap: Option<String>,
    },
    /// braid_registry — the REAL door/identity registry (control-center / ipam
    /// parity / local daemon): registered doors (label + location), the
    /// default snapshot, and whether the human escalation gate is armed.
    Registry,
    /// door3 quest3d (m11, D3.5) — SPOKEN RESONANCE: render the last `depth`
    /// proven nodes of the SAME snapshot as one backbone audio stream ("audio
    /// echoes of the braid spine"). Read-gated exactly like every read: the
    /// spine only speaks what the token could already read. The response
    /// carries the real WAV (base64) + per-segment provenance; the kokoro
    /// TTS container is the only synthesis engine — if it is unreachable the
    /// op DENIES honestly, it never fabricates a track.
    Audio { snapshot: String, depth: u64 },
    /// door3 (m12) — the INTENT STRAND: the ledger's open desires, derived
    /// from committed `write:intent` nodes. Read-gated exactly like every
    /// read. An intent is OPEN until a later committed, PROVEN node references
    /// it via `payload.fulfills == <intent cid>` — then it is RESOLVED, with
    /// the fulfilling node's cid/depth/op as on-chain provenance. No
    /// speculative execution: a desire and its fulfillment are both ordinary
    /// braided nodes on the ONE ledger.
    Intent { snapshot: String },
    /// m13 — the TERMINAL DOOR's unified TAIL: the last `limit` committed
    /// nodes of the ONE ledger as a real, read-gated view (exactly like every
    /// read). `since_cid` advances the cursor — the tail streams from just
    /// AFTER that committed node, so a terminal can re-issue with the newest
    /// cid it has seen to `--follow`. `limit == 0` uses the bridge's default
    /// window. Returns the ledger head + depth and each node's prev link, so a
    /// replay is exactly the committed chain.
    Tail {
        snapshot: String,
        #[serde(default)]
        since_cid: Option<String>,
        #[serde(default)]
        limit: u64,
    },
    /// m13 — the TERMINAL DOOR's unified READ VIEW: the single-head invariant
    /// (real heads/forks computed off the log), the current head cid + depth,
    /// every registered door's view position, and the frozen snapshot. Read-
    /// gated exactly like every read — the view only reports what the token
    /// could already read.
    Inspect,
}

/// Request envelope: capability token (macaroon) + op. The macaroon carries
/// the DID + session caveats (the capability) — no second auth island.
///
/// m4 escalation: `escalation` carries the SECOND, human-gated macaroon for
/// ops the door token alone cannot grant (godmode destructive). BOTH tokens
/// must verify; the engine glues both triplets into the committed node.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WireRequest {
    pub version: String,
    pub transport: String,
    pub macaroon: braid_keys::SessionMacaroon,
    #[serde(default)]
    pub escalation: Option<braid_keys::SessionMacaroon>,
    pub op: WireOp,
}

impl WireRequest {
    pub fn new(transport: &str, macaroon: braid_keys::SessionMacaroon, op: WireOp) -> Self {
        Self {
            version: WIRE_VERSION.into(),
            transport: transport.into(),
            macaroon,
            escalation: None,
            op,
        }
    }
}

/// Response envelope. Every write echoes the braided triad bound at commit.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WireResponse {
    pub ok: bool,
    pub error: Option<String>,
    pub data: serde_json::Value,
    pub triplet: Option<BraidedTriplet>,
}

impl WireResponse {
    pub fn ok(data: serde_json::Value, triplet: Option<BraidedTriplet>) -> Self {
        Self {
            ok: true,
            error: None,
            data,
            triplet,
        }
    }

    pub fn err<E: std::fmt::Display>(e: E) -> Self {
        Self {
            ok: false,
            error: Some(e.to_string()),
            data: serde_json::Value::Null,
            triplet: None,
        }
    }
}