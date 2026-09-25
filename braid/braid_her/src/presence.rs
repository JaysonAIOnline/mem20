//! agent presence — who is actually IN this braid (door3, D3.4).
//!
//! Presence is surfaced from the ledger itself, never from configuration:
//! an identity is "present" only if it signed nodes whose audit strands
//! VERIFY. This keeps presence grounded the same way world facts are —
//! a tampered ledger cannot conjure a phantom agent.

use std::collections::BTreeMap;

use serde::Serialize;

use braid_core::engine::BraidEngine;

#[derive(Debug, Clone, Serialize)]
pub struct AgentPresence {
    pub identity: String,
    pub role: &'static str,
    pub node_count: usize,
    pub escalated_ops: usize,
    pub first_seen_cid: String,
    pub last_seen_cid: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct Presence {
    pub agents: Vec<AgentPresence>,
}

impl Presence {
    /// Build presence from the full verified chain (all nodes, not just the
    /// cap-gated read window — presence is structural, facts are read-gated).
    pub fn from_ledger(engine: &BraidEngine) -> Self {
        let nodes = engine.log.items_for_audit();
        let mut by_identity: BTreeMap<String, Vec<braid_core::storage::Node>> = BTreeMap::new();
        for n in &nodes {
            if !braid_core::engine::node_is_proven(n) {
                continue; // unproven nodes do not count as presence
            }
            by_identity.entry(n.signer.clone()).or_default().push(n.clone());
        }

        let agents = by_identity
            .into_iter()
            .map(|(identity, mut owned)| {
                owned.sort_by_key(|n| n.depth);
                let escalated_ops = owned
                    .iter()
                    .filter(|n| n.audit.as_ref().map(|a| a.escalation_triplet.is_some()).unwrap_or(false))
                    .count();
                AgentPresence {
                    identity: short_hex(&identity),
                    role: "write-authority",
                    node_count: owned.len(),
                    escalated_ops,
                    first_seen_cid: owned.first().map(|n| n.cid.clone()).unwrap_or_default(),
                    last_seen_cid: owned.last().map(|n| n.cid.clone()).unwrap_or_default(),
                }
            })
            .collect();

        Presence { agents }
    }
}

/// Present the identity compactly (stable prefix of the hex key).
fn short_hex(identity: &str) -> String {
    let keep = identity.len().min(12);
    let prefix: String = identity.chars().take(keep).collect();
    if identity.len() > keep {
        format!("{prefix}…")
    } else {
        prefix
    }
}