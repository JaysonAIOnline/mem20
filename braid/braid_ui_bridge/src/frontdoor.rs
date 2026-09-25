//! U1 — the single Frontdoor Router every door consumes.
//!
//! The bridge owns the engine + the registered doors; the router is the SOLE
//! entry point the wire server calls. It verifies the macaroon, scopes the
//! capability, enforces the op-vs-token check, then dispatches to the engine
//! and shapes the reply as that door's view (lumen/axiom/her). No UI code
//! talks to the engine directly — every door IS this router.

use std::sync::{Arc, Mutex};

use braid_core::engine::BraidEngine;
use braid_core::policy::PolicySnapshot;
use braid_wire::{WireOp, WireRequest, WireResponse};

use crate::api::{AxiomView, HerWindowView, LumenView};
use crate::auth::{may_use, scope_of, verify_macaroon};

/// The three doors. door2/godmode has the widest scope; door1 lumen is small
/// and scoped; door3/her is the conversation window.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Door {
    Lumen,
    Axiom,
    Mem,
}

impl Door {
    pub fn label(&self) -> &'static str {
        match self {
            Door::Lumen => "door1",
            Door::Axiom => "door2",
            Door::Mem => "door3",
        }
    }
}

/// One registered door: its DID (root identity for macaroon verification),
/// the location string bound in its macaroons, and which view it reads.
#[derive(Debug, Clone)]
pub struct DoorRegistration {
    pub door: Door,
    pub did: String,
    pub location: String,
}

/// Full router. Thread-safe: the engine is the single write authority
/// (serialized writes), reads can proceed while a write waits only through
/// the same mutex — matching the "one substrate" invariant.
pub struct Router {
    engine: Arc<Mutex<BraidEngine>>,
    doors: Vec<DoorRegistration>,
    default_snapshot: String,
    /// m4: the escalation gate. `escalation_did` is the HUMAN root identity
    /// the second macaroon must verify against; `escalation_snapshot` is the
    /// frozen policy snapshot that licenses destructive ops. Both are
    /// optional — a bridge that never registers them has NO godmode gate.
    escalation: Option<(String, String)>,
    /// m11 (D3.5): the audio strand — the kokoro TTS client that renders the
    /// spine into speech. Optional: a bridge without a client has NO audio
    /// surface (it denies honestly, it never fabricates a track).
    tts: Option<braid_sonic::tts::TtsClient>,
    /// m13: per-door VIEW POSITIONS — the last composed depth (number of
    /// committed nodes) each door's view has been built against. Updated on
    /// every view composition (read/world/get/prove/policy/registry/audio/
    /// intent/tail/inspect); never reaches ahead of what that door did read.
    views: std::sync::Mutex<std::collections::HashMap<Door, u64>>,
}

impl Router {
    /// `snapshot_cid` is the frozen policy snapshot applied to every write;
    /// `beliefs` snapshot is the same registered snapshot re-born, but the
    /// router only ever evaluates via the engine (single authority).
    pub fn new(
        engine: Arc<Mutex<BraidEngine>>,
        doors: Vec<DoorRegistration>,
        default_snapshot: impl Into<String>,
    ) -> Self {
        Router {
            engine,
            doors,
            default_snapshot: default_snapshot.into(),
            escalation: None,
            tts: None,
            views: std::sync::Mutex::new(std::collections::HashMap::new()),
        }
    }

    /// Enable the godmode gate: the HUMAN DID that must co-sign destructive
    /// writes, and the escalation policy snapshot the engine has already
    /// registered. Without this call, `admin:*` ops are unreachable.
    pub fn with_escalation(mut self, human_did: impl Into<String>, escalation_snapshot: impl Into<String>) -> Self {
        self.escalation = Some((human_did.into(), escalation_snapshot.into()));
        self
    }

    /// Arm the audio strand (m11, D3.5): the kokoro TTS client that renders
    /// committed nodes into spoken resonance. Without this call `WireOp::Audio`
    /// denies honestly.
    pub fn with_tts(mut self, tts: braid_sonic::tts::TtsClient) -> Self {
        self.tts = Some(tts);
        self
    }

    /// Borrow the single write authority (auditors, bridges, examples). The
    /// lock MUST NOT cross a route() call — that would deadlock the wire.
    pub fn engine(&self) -> &Arc<Mutex<BraidEngine>> {
        &self.engine
    }

    /// m13: record a door's view position — the number of committed nodes its
    /// view was actually composed against (we hold the engine lock, so the
    /// seen_n is exactly the ledger at composition time). Monotonic: a door
    /// can only ever advance to what it has really read.
    fn track_view(&self, door: Door, seen_n: u64) {
        if let Ok(mut v) = self.views.lock() {
            let entry = v.entry(door).or_insert(0);
            if seen_n > *entry {
                *entry = seen_n;
            }
        }
    }

    /// Route a wire request. Called by the wire server's handler.
    pub fn route(&self, req: &WireRequest) -> WireResponse {
        // U3: EVERY request carries a macaroon; there is no anonymous path.
        // The macaroon's location identifies the door.
        let location = &req.macaroon.location;
        let reg = match self.doors.iter().find(|r| &r.location == location) {
            Some(r) => r,
            None => {
                return WireResponse::err(format!(
                    "no door registered for macaroon location `{location}` — refusing"
                ))
            }
        };

        if let Err(e) = verify_macaroon(&req.macaroon, &reg.did, &reg.location) {
            return WireResponse::err(format!(
                "auth denied on {}: {e}",
                reg.door.label()
            ));
        }

        let scope = scope_of(&req.macaroon, reg.door.label(), &reg.did);
        let cap = scope.capability.clone();

        let mut engine = match self.engine.lock() {
            Ok(e) => e,
            Err(_) => {
                return WireResponse::err("engine lock poisoned — no substrate")
            }
        };

        match &req.op {
            WireOp::Write { snapshot, op, target, payload }
            | WireOp::Spatial { snapshot, op, target, payload } => {
                let snapshot_id = if snapshot.is_empty() {
                    &self.default_snapshot
                } else {
                    snapshot
                };
                let escalated = !may_use(&scope, op);
                let res = if escalated {
                    // m4 godmode gate: the door token alone does NOT cover this
                    // destructive op. Escalation requires a SECOND, human-gated
                    // macaroon AND a registered escalation gate; otherwise the
                    // whole admin surface is unreachable.
                    let (human_did, esc_snapshot) = match &self.escalation {
                        Some(es) => (es.0.clone(), es.1.clone()),
                        None => {
                            return WireResponse::err(format!(
                                "{} scope `{cap}` lacks op `{op}` and no escalation gate is registered — denied",
                                reg.door.label()
                            ))
                        }
                    };
                    let human = match &req.escalation {
                        Some(m) => m,
                        None => {
                            return WireResponse::err(format!(
                                "{}: op `{op}` needs a second human-gated token — denied (no escalation macaroon)",
                                reg.door.label()
                            ))
                        }
                    };
                    if human.caveats.is_empty() {
                        return WireResponse::err("escalation macaroon carries no caveat — denied");
                    }
                    if let Err(e) = verify_macaroon(human, &human_did, "human-escalation") {
                        return WireResponse::err(format!(
                            "{}: escalation token failed verification — {e}",
                            reg.door.label()
                        ));
                    }
                    let esc_cap = braid_core::policy::Capability::parse(&human.caveats[0]);
                    if !esc_cap.action_grants_op(op) {
                        return WireResponse::err(format!(
                            "{}: escalation cap `{esc_cap}` does not cover op `{op}` — denied",
                            reg.door.label()
                        ));
                    }
                    let esc_snapshot = esc_snapshot.clone();
                    engine.write_escalated(
                        &cap,
                        snapshot_id,
                        &braid_core::engine::Escalation {
                            cap: &esc_cap,
                            snapshot_cid: &esc_snapshot,
                        },
                        op,
                        target,
                        payload.clone(),
                    )
                } else {
                    engine.write(&cap, snapshot_id, op, target, payload.clone())
                };
                match res {
                    Ok(receipt) => {
                        let view = match (&req.op, reg.door) {
                            // A spatial write (m9, door3 quest3d) is a braid node
                            // + a WORD FACT at once: echo the freshly composed
                            // WorldScene + resonance window + presence, so the
                            // walk-in reflects the new object immediately.
                            (WireOp::Spatial { .. }, _) => {
                                let scene = braid_her::WorldScene::from_ledger(&engine, &cap, snapshot_id);
                                let window = braid_her::ResonanceWindow::from_ledger(&engine, &cap, snapshot_id);
                                let presence = braid_her::Presence::from_ledger(&engine);
                                serde_json::json!({
                                    "kind": "spatial",
                                    "walk_in_count": scene.walk_in_count,
                                    "proven": scene.proven,
                                    "excluded": scene.excluded,
                                    "world": scene,
                                    "window": window,
                                    "presence": presence,
                                    "snapshot": snapshot_id,
                                })
                            }
                            (_, Door::Lumen) => serde_json::to_value(LumenView::of(&engine.read(&cap, snapshot_id, None).unwrap_or_default())).unwrap_or_default(),
                            (_, Door::Axiom) => serde_json::to_value(AxiomView::of(&engine.log)).unwrap_or_default(),
                            (_, Door::Mem) => serde_json::to_value(HerWindowView::of(&engine.read(&cap, snapshot_id, None).unwrap_or_default())).unwrap_or_default(),
                        };
                        let door_label = match &req.op {
                            WireOp::Spatial { .. } => "door3",
                            _ => reg.door.label(),
                        };
                        self.track_view(reg.door, engine.log.len() as u64);
                        WireResponse::ok(
                            serde_json::json!({
                                "door": door_label,
                                "cid": receipt.cid,
                                "depth": receipt.depth,
                                "proof_hops": receipt.proof_hops,
                                "precommit_verified": receipt.precommit_verified,
                                "escalated": escalated,
                                "view": view,
                            }),
                            Some(receipt.triplet),
                        )
                    }
                    Err(e) => WireResponse::err(e),
                }
            }
            WireOp::Read { snapshot, op_filter } => {
                if !may_use(&scope, "read") {
                    return WireResponse::err(format!(
                        "{} scope `{cap}` does not grant read — denied",
                        reg.door.label()
                    ));
                }
                let snapshot_id = if snapshot.is_empty() {
                    &self.default_snapshot
                } else {
                    snapshot
                };
                match engine.read(&cap, snapshot_id, op_filter.as_deref()) {
                    Ok(nodes) => {
                        let view = match reg.door {
                            Door::Lumen => serde_json::to_value(LumenView::of(&nodes)).unwrap_or_default(),
                            Door::Axiom => serde_json::to_value(AxiomView::of(&engine.log)).unwrap_or_default(),
                            Door::Mem => serde_json::to_value(HerWindowView::of(&nodes)).unwrap_or_default(),
                        };
                        self.track_view(reg.door, engine.log.len() as u64);
                        WireResponse::ok(
                            serde_json::json!({
                                "door": reg.door.label(),
                                "count": nodes.len(),
                                "view": view,
                            }),
                            None,
                        )
                    }
                    Err(e) => WireResponse::err(e),
                }
            }
            // door3 quest3d — braid_read returning world-state to spatial nodes.
            WireOp::World { snapshot } => {
                if !may_use(&scope, "read") {
                    return WireResponse::err(format!(
                        "{} scope `{cap}` does not grant read — denied",
                        reg.door.label()
                    ));
                }
                let snapshot_id = if snapshot.is_empty() {
                    &self.default_snapshot
                } else {
                    snapshot
                };
                let scene = braid_her::WorldScene::from_ledger(&engine, &cap, snapshot_id);
                let window = braid_her::ResonanceWindow::from_ledger(&engine, &cap, snapshot_id);
                let presence = braid_her::Presence::from_ledger(&engine);
                self.track_view(reg.door, engine.log.len() as u64);
                WireResponse::ok(
                    serde_json::json!({
                        "door": reg.door.label(),
                        "kind": "world",
                        "walk_in_count": scene.walk_in_count,
                        "proven": scene.proven,
                        "excluded": scene.excluded,
                        "world": scene,
                        "window": window,
                        "presence": presence,
                        "snapshot": snapshot_id,
                    }),
                    None,
                )
            }
            WireOp::Get { snapshot, cid } => {
                let snapshot_id = if snapshot.is_empty() {
                    &self.default_snapshot
                } else {
                    snapshot
                };
                match engine.get(&cap, snapshot_id, cid) {
                    Ok(Some(n)) => {
                        self.track_view(reg.door, engine.log.len() as u64);
                        WireResponse::ok(serde_json::to_value(n).unwrap_or_default(), None)
                    }
                    Ok(None) => WireResponse::err(format!("no node {cid}")),
                    Err(e) => WireResponse::err(e),
                }
            }
            WireOp::Prove { cid } => {
                let spine = engine.proof(cid);
                self.track_view(reg.door, engine.log.len() as u64);
                WireResponse::ok(
                    serde_json::json!({
                        "cid": cid,
                        "spine_hops": spine.len().saturating_sub(1),
                        "spine_to_genesis": spine,
                        "verified": engine.verify_node(cid),
                    }),
                    None,
                )
            }
            WireOp::Health => WireResponse::ok(
                serde_json::json!({"status": "ok", "doors": self.doors.len(), "engine": braid_core::VERSION}),
                None,
            ),
            // m8 tool-policy / eval surfaces: the REAL frozen policy snapshot.
            // `cap == None` → full serialized PolicySnapshot (rule list);
            // `cap == Some` → the snapshot's own verdict for that capability
            // (same frozen authority the engine binds into every write).
            WireOp::Policy { snapshot, cap } => {
                if !may_use(&scope, "read") {
                    return WireResponse::err(format!(
                        "{} scope does not grant read — denied",
                        reg.door.label()
                    ));
                }
                let snapshot_id = if snapshot.is_empty() {
                    &self.default_snapshot
                } else {
                    snapshot
                };
                let snap = match engine.snapshot(snapshot_id) {
                    Some(s) => s.clone(),
                    None => {
                        return WireResponse::err(format!("no snapshot `{snapshot_id}` registered"))
                    }
                };
                match cap {
                    Some(c) => {
                        self.track_view(reg.door, engine.log.len() as u64);
                        WireResponse::ok(
                            serde_json::json!({
                                "door": reg.door.label(),
                                "snapshot": snapshot_id,
                                "cap": c,
                                "allowed": snap.evaluate_str(c),
                                "policy": snap,
                            }),
                            None,
                        )
                    }
                    None => {
                        self.track_view(reg.door, engine.log.len() as u64);
                        WireResponse::ok(
                            serde_json::json!({
                                "door": reg.door.label(),
                                "snapshot": snapshot_id,
                                "policy": snap,
                            }),
                            None,
                        )
                    }
                }
            }
            // m8 console/daemon/ipam parity: the REAL door registry + gate state.
            WireOp::Registry => {
                if !may_use(&scope, "read") {
                    return WireResponse::err(format!(
                        "{} scope does not grant read — denied",
                        reg.door.label()
                    ));
                }
                let doors: Vec<serde_json::Value> = self
                    .doors
                    .iter()
                    .map(|d| {
                        serde_json::json!({ "door": d.door.label(), "location": d.location })
                    })
                    .collect();
                self.track_view(reg.door, engine.log.len() as u64);
                WireResponse::ok(
                    serde_json::json!({
                        "door": reg.door.label(),
                        "doors": doors,
                        "default_snapshot": self.default_snapshot,
                        "escalation_armed": self.escalation.is_some(),
                        "engine": braid_core::VERSION,
                    }),
                    None,
                )
            }
            // m11 D3.5 — SPOKEN RESONANCE: the spine speaks its last `depth`
            // proven nodes as ONE backbone audio stream. Read-gated exactly
            // like every read (the spine only speaks what the token could
            // already read). The ONLY synthesis engine is the kokoro TTS
            // container — if it is unreachable (or no client was armed) the op
            // denies honestly; it never fabricates a track.
            WireOp::Audio { snapshot, depth } => {
                if !may_use(&scope, "read") {
                    return WireResponse::err(format!(
                        "{} scope does not grant read — denied",
                        reg.door.label()
                    ));
                }
                let Some(tts) = &self.tts else {
                    return WireResponse::err(format!(
                        "{}: audio strand not armed (no kokoro TTS client registered) — denied",
                        reg.door.label()
                    ));
                };
                let snapshot_id = if snapshot.is_empty() {
                    &self.default_snapshot
                } else {
                    snapshot
                };
                let nodes = match engine.read(&cap, snapshot_id, None) {
                    Ok(nodes) => nodes,
                    Err(e) => return WireResponse::err(e),
                };
                let depth = if *depth == 0 { 8 } else { *depth as usize };
                let start = nodes.len().saturating_sub(depth);
                let to_speak = &nodes[start..];
                match braid_sonic::mix::speak_spine(tts, to_speak) {
                    Ok(spine) => {
                        self.track_view(reg.door, engine.log.len() as u64);
                        WireResponse::ok(
                            serde_json::json!({
                                "door": reg.door.label(),
                                "kind": "audio",
                                "snapshot": snapshot_id,
                                "engine": braid_core::VERSION,
                                "tts": tts.base_url,
                                "voice": spine.voice,
                                "sample_rate": spine.sample_rate,
                                "channels": spine.channels,
                                "bits_per_sample": spine.bits_per_sample,
                                "total_bytes": spine.total_bytes,
                                "total_ms": spine.total_ms,
                                "spoken": spine.segments.len(),
                                "segments": spine.segments,
                                "wav_b64": braid_wire::b64::encode(&spine.wav),
                            }),
                            None,
                        )
                    }
                    Err(e) => WireResponse::err(format!(
                        "{}: audio strand: {e}",
                        reg.door.label()
                    )),
                }
            }
            // m12 — the INTENT STRAND: the ledger's open desires / their
            // resolutions, derived from committed `write:intent` nodes. Read-
            // gated exactly like every read — the strand only shows what the
            // token could already read. A desire is OPEN until a later proven
            // node references it (`payload.fulfills`); then it is RESOLVED
            // with the fulfilling node's cid. No speculative motion anywhere.
            WireOp::Intent { snapshot } => {
                if !may_use(&scope, "read") {
                    return WireResponse::err(format!(
                        "{} scope `{cap}` does not grant read — denied",
                        reg.door.label()
                    ));
                }
                let snapshot_id = if snapshot.is_empty() {
                    &self.default_snapshot
                } else {
                    snapshot
                };
                let view = braid_core::intent::IntentStrand::from_ledger(&engine, &cap, snapshot_id);
                self.track_view(reg.door, engine.log.len() as u64);
                WireResponse::ok(
                    serde_json::json!({
                        "door": reg.door.label(),
                        "kind": "intent",
                        "snapshot": snapshot_id,
                        "submitted": view.submitted,
                        "open": view.open,
                        "resolved": view.resolved,
                        "pending_count": view.pending_count,
                        "intents": view.intents,
                    }),
                    None,
                )
            }
            // m13 — the TERMINAL DOOR's unified TAIL: the last `limit`
            // committed nodes of the ONE ledger, read-gated exactly like every
            // read. `since_cid` advances the cursor (exclusive), so a terminal
            // can --follow by re-issuing with the newest committed cid.
            WireOp::Tail { snapshot, since_cid, limit } => {
                if !may_use(&scope, "read") {
                    return WireResponse::err(format!(
                        "{} scope `{cap}` does not grant read — denied",
                        reg.door.label()
                    ));
                }
                let snapshot_id = if snapshot.is_empty() {
                    &self.default_snapshot
                } else {
                    snapshot
                };
                let nodes = match engine.read(&cap, snapshot_id, None) {
                    Ok(nodes) => nodes,
                    Err(e) => return WireResponse::err(e),
                };
                // Resolve the cursor: the window starts just AFTER `since_cid`.
                // An unknown since is an honest denial — never a silent full tail.
                let since_idx = match since_cid {
                    Some(s) => match nodes.iter().position(|n| &n.cid == s) {
                        Some(i) => Some(i + 1),
                        None => {
                            return WireResponse::err(format!(
                                "{}: `{s}` is not on this ledger — tail denied",
                                reg.door.label()
                            ))
                        }
                    },
                    None => None,
                };
                let limit_n = if *limit == 0 { 64 } else { *limit as usize };
                let since_start = since_idx.unwrap_or(0);
                let available = nodes.len().saturating_sub(since_start);
                let truncated = available > limit_n;
                let take = available.min(limit_n);
                let start = if since_cid.is_some() {
                    since_start
                } else {
                    nodes.len().saturating_sub(take)
                };
                let window = &nodes[start..start + take];
                let head = engine.head();
                self.track_view(reg.door, engine.log.len() as u64);
                WireResponse::ok(
                    serde_json::json!({
                        "door": reg.door.label(),
                        "kind": "tail",
                        "snapshot": snapshot_id,
                        "head_cid": head.map(|h| h.cid.clone()).unwrap_or_default(),
                        "head_depth": head.map(|h| h.depth).unwrap_or(0),
                        "since_cid": since_cid,
                        "limit": window.len(),
                        "truncated": truncated,
                        "nodes": window,
                    }),
                    None,
                )
            }
            // m13 — the TERMINAL DOOR's unified READ VIEW: the single-head
            // invariant computed honestly off the log (real heads = tips,
            // real forks = parents with more than one child), the current
            // head/depth, every registered door's view position, and the
            // frozen snapshot. Read-gated exactly like every read.
            WireOp::Inspect => {
                if !may_use(&scope, "read") {
                    return WireResponse::err(format!(
                        "{} scope `{cap}` does not grant read — denied",
                        reg.door.label()
                    ));
                }
                let snapshot_id = &self.default_snapshot;
                let nodes = match engine.read(&cap, snapshot_id, None) {
                    Ok(nodes) => nodes,
                    Err(e) => return WireResponse::err(e),
                };
                // Real single-head invariant: a tip is a node no other node
                // points `prev` at; a fork is a parent with more than one child.
                let mut referenced: std::collections::HashSet<&str> = std::collections::HashSet::new();
                let mut children: std::collections::HashMap<&str, usize> = std::collections::HashMap::new();
                for n in &nodes {
                    if let Some(p) = n.body.prev.as_deref() {
                        referenced.insert(p);
                        *children.entry(p).or_insert(0) += 1;
                    }
                }
                let heads = nodes.iter().filter(|n| !referenced.contains(n.cid.as_str())).count();
                let forks = children.values().filter(|&&c| c > 1).count();
                let head = engine.head();
                let doors: Vec<serde_json::Value> = self
                    .doors
                    .iter()
                    .map(|d| {
                        let pos = self
                            .views
                            .lock()
                            .map(|v| v.get(&d.door).copied().unwrap_or(0))
                            .unwrap_or(0);
                        serde_json::json!({
                            "door": d.door.label(),
                            "location": d.location,
                            "view_position": pos,
                        })
                    })
                    .collect();
                self.track_view(reg.door, engine.log.len() as u64);
                WireResponse::ok(
                    serde_json::json!({
                        "door": reg.door.label(),
                        "kind": "inspect",
                        "snapshot": snapshot_id,
                        "head_cid": head.map(|h| h.cid.clone()).unwrap_or_default(),
                        "head_depth": head.map(|h| h.depth).unwrap_or(0),
                        "nodes": nodes.len(),
                        "heads": heads,
                        "forks": forks,
                        "doors": doors,
                        "engine": braid_core::VERSION,
                    }),
                    None,
                )
            }
        }
    }
}

/// Convenience: make a Router a braid_wire Handler without extra glue.
pub fn handler_from(router: Arc<Router>) -> braid_wire::Handler {
    Arc::new(move |req: WireRequest| router.route(&req))
}

/// Syntactic sugar mirroring the m1 invariant: router is what the server owns.
pub trait DoorSocket: Send + Sync {
    fn door_count(&self) -> usize;
    fn snapshot_used(&self) -> &str;
}

impl DoorSocket for Router {
    fn door_count(&self) -> usize {
        self.doors.len()
    }
    fn snapshot_used(&self) -> &str {
        &self.default_snapshot
    }
}

/// A guard for the engine lock is NOT exposed: keep single-authority writes.
pub type EngineGuard = Arc<Mutex<BraidEngine>>;

/// Register a policy snapshot into the engine (one-time boot).
pub fn register_snapshot(engine: &mut BraidEngine, snap: PolicySnapshot) {
    engine.register_snapshot(snap);
}