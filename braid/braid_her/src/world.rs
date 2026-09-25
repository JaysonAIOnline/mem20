//! world facts — the spatial walk-in's payload (door3, quest3d).
//!
//! A fact is ONLY a fact when its attached audit strand verifies. Every
//! `WorldNode` ships with its provenance (ledger CID + capability + snapshot
//! + signer + signature_ok), so the walk-in walks on PROVEN facts: if a node
//!   was tampered with, it cannot enter the scene. Positions are
//!   deterministic from the object id — an object keeps its spot in space
//!   across every visit.

use serde::Serialize;

use braid_core::engine::BraidEngine;
use braid_core::policy::Capability;
use braid_core::storage::Node;

/// The on-chain proof that a world fact is grounded. `signature_ok` is the
/// verifier's live answer — the door never trusts it, it computes it.
#[derive(Debug, Clone, Serialize)]
pub struct FactProvenance {
    pub cid: String,
    pub capability: String,
    pub snapshot: String,
    pub signer: String,
    pub signature_ok: bool,
}

/// One positionable object in the walk-in. `position` is a deterministic
/// spatial placement; `provenance` is the reason this object is allowed in
/// the world at all.
#[derive(Debug, Clone, Serialize)]
pub struct WorldNode {
    pub object_id: String,
    pub target: String,
    pub kind: String,
    pub label: String,
    pub position: [f64; 3],
    pub payload: serde_json::Value,
    pub provenance: FactProvenance,
}

impl WorldNode {
    fn proven(node: &Node) -> Self {
        let audit = node.audit.as_ref().expect("fact gate ensures audit");
        let kind = node.body.op.rsplit(':').next().unwrap_or(&node.body.op).to_string();
        let object_id = format!("{kind}:{}", &node.cid[..node.cid.len().min(10)]);
        WorldNode {
            object_id: object_id.clone(),
            target: node.body.target.clone(),
            kind,
            label: label_for(node),
            position: spatial_position(&object_id),
            payload: node.body.payload.clone(),
            provenance: FactProvenance {
                cid: node.cid.clone(),
                capability: audit.triplet.capability.clone(),
                snapshot: audit.triplet.policy_snapshot.clone(),
                signer: node.signer.clone(),
                signature_ok: audit.verified(&node.signer),
            },
        }
    }
}

/// Every committed node, the whole scene.
#[derive(Debug, Clone, Serialize)]
pub struct WorldScene {
    pub walk_in_count: usize,
    pub proven: usize,
    pub excluded: usize,
    pub facts: Vec<WorldNode>,
}

impl WorldScene {
    /// Derive a scene from a cap-gated `braid_read`. Only PROVEN nodes
    /// (audit verifies AND precommitment still binds the content) become
    /// facts; every other node is counted as excluded (tampered, unsigned,
    /// or audit-less — not allowed into the world).
    pub fn from_nodes(nodes: &[Node]) -> Self {
        let mut facts = Vec::new();
        let mut excluded = 0usize;
        for n in nodes {
            if !braid_core::engine::node_is_proven(n) {
                excluded += 1;
                continue;
            }
            facts.push(WorldNode::proven(n));
        }
        let walk_in_count = facts.len();
        WorldScene { walk_in_count, proven: facts.len(), excluded, facts }
    }

    /// The spatial contract D3.3: braid_read returns world-state. Reads go
    /// through `braid_read` (cap-gated, snapshot-frozen), never a raw log
    /// walk — one read authority for every door.
    pub fn from_ledger(engine: &BraidEngine, cap: &Capability, snapshot_cid: &str) -> Self {
        let nodes = engine.read(cap, snapshot_cid, None).unwrap_or_default();
        Self::from_nodes(&nodes)
    }
}

/// Short, stable, human-usable label from the node's content.
fn label_for(node: &Node) -> String {
    let raw = node
        .body
        .payload
        .get("name")
        .and_then(serde_json::Value::as_str)
        .or_else(|| node.body.payload.get("content").and_then(serde_json::Value::as_str))
        .unwrap_or(&node.body.target);
    raw.chars().take(80).collect()
}

/// A deterministic pseudo-random float in [0,1) from a byte string.
fn hash01(bytes: &[u8]) -> f64 {
    let h = braid_core::crypto::hash(bytes);
    let mut a = [0u8; 8];
    a.copy_from_slice(&h[..8]);
    (u64::from_le_bytes(a) as f64) / (u64::MAX as f64)
}

/// Golden-angle ring placement: an object's spot depends ONLY on its id, so
/// re-entry places every object in the SAME position (stable spatial walk-in).
fn spatial_position(object_id: &str) -> [f64; 3] {
    let mut theta_bytes = object_id.as_bytes().to_vec();
    theta_bytes.push(0xA7);
    let mut y_bytes = object_id.as_bytes().to_vec();
    y_bytes.push(0xB3);
    let t = 2.0 * std::f64::consts::PI * hash01(&theta_bytes);
    let r = 1.5 + 5.5 * hash01(object_id.as_bytes());
    let y = 0.4 + 1.1 * hash01(&y_bytes);
    [r * t.cos(), y, r * t.sin()]
}