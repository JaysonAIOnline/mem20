//! window — HER's resonance window (door3, D3.1).
//!
//! The window is NOT chat bubbles: every line is a braid node and every
//! message "resonates from" the braid node that preceded it (its prev link).
//! The thread IS the relationship — the spine of the ledger, not an author
//! model bolted on top of it.

use serde::Serialize;

use braid_core::engine::BraidEngine;
use braid_core::policy::Capability;
use braid_core::storage::Node;

/// One strand of the resonance: a committed node and the node it echoes.
#[derive(Debug, Clone, Serialize)]
pub struct Echo {
    pub cid: String,
    pub depth: u64,
    pub resonates_from: Option<String>,
    pub op: String,
    pub target: String,
}

/// door3's window — an ordered resonance stream over the braid spine.
#[derive(Debug, Clone, Serialize)]
pub struct ResonanceWindow {
    pub door: &'static str,
    pub kind: &'static str,
    pub last_cid: Option<String>,
    pub echoes: Vec<Echo>,
}

impl ResonanceWindow {
    /// Build the window from a cap-gated read (one read authority). Each
    /// echo carries the braid parent it resonates from.
    pub fn of(nodes: &[Node]) -> Self {
        let mut v: Vec<Echo> = nodes
            .iter()
            .map(|n| Echo {
                cid: n.cid.clone(),
                depth: n.depth,
                resonates_from: n.body.prev.clone(),
                op: n.body.op.clone(),
                target: n.body.target.clone(),
            })
            .collect();
        v.sort_by_key(|e| e.depth);
        let last_cid = v.last().map(|e| e.cid.clone());
        ResonanceWindow {
            door: "door3",
            kind: "resonance",
            last_cid,
            echoes: v,
        }
    }

    /// Read through braid_read, then resonate.
    pub fn from_ledger(engine: &BraidEngine, cap: &Capability, snapshot_cid: &str) -> Self {
        let nodes = engine.read(cap, snapshot_cid, None).unwrap_or_default();
        Self::of(&nodes)
    }
}