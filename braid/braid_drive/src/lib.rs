//! braid_drive — the m3 audit: verify braided triplets UNDER CONCURRENCY.
//!
//! m3 invariant (from the canonical plan): braided triplets verified under
//! concurrency — no deadlock, NO CORRUPTION. After heavy interleaved write
//! traffic we replay the whole ledger independently and re-verify every node:
//! CID re-derivation, prev-link closure, single-head no-fork, and each node's
//! attached audit strand (triplet signature + pre-commitment + snapshot ref).

pub mod wire;

use braid_core::engine::BraidEngine;
use braid_core::storage::{cid_from_body, Node, NodeBody};
use serde::Serialize;

/// Per-node audit result.
#[derive(Debug, Clone, Serialize)]
pub struct NodeAudit {
    pub cid: String,
    pub depth: u64,
    pub cid_rederives: bool,
    pub prev_links_to_genesis: bool,
    pub carries_audit_strand: bool,
    pub triplet_signature_ok: bool,
    pub precommitment_ok: bool,
}

/// Whole-ledger audit report (m3 acceptance evidence).
#[derive(Debug, Clone, Serialize)]
pub struct DriveAudit {
    pub node_count: usize,
    pub all_cids_rederive: bool,
    pub all_prev_links_close: bool,
    pub all_nodes_carry_audit_strand: bool,
    pub all_triplet_signatures_ok: bool,
    pub all_precommitments_ok: bool,
    pub single_head_chain: bool,
    pub clean: bool,
    pub per_node: Vec<NodeAudit>,
}

impl DriveAudit {
    pub fn clean(&self) -> bool {
        self.all_cids_rederive
            && self.all_prev_links_close
            && self.all_nodes_carry_audit_strand
            && self.all_triplet_signatures_ok
            && self.all_precommitments_ok
            && self.single_head_chain
    }
}

/// Full independent audit of an engine's ledger. `expected_snapshot_cid` is
/// the frozen policy snapshot the write path SHOULD have bound into every
/// triplet.
pub fn audit_ledger(engine: &BraidEngine, expected_snapshot_cid: &str) -> DriveAudit {
    let nodes = engine.log.items_for_audit();
    let mut per_node = Vec::with_capacity(nodes.len());
    let mut all_cids = true;
    let mut all_prev = true;
    let mut all_audit = true;
    let mut all_sig = true;
    let mut all_pre = true;

    for n in &nodes {
        let rederives = cid_rederives(n);
        let prev_ok = match &n.body.prev {
            None => true, // genesis
            Some(p) => engine.log.get(p).is_some(),
        };
        let audit_ok = n.audit.is_some();
        let sig_ok = n
            .audit
            .as_ref()
            .map(|a| a.verified(&n.signer))
            .unwrap_or(false);
        let pre_ok = n
            .audit
            .as_ref()
            .map(|a| {
                // A node may bind TWO snapshots (m4 godmode escalation): the
                // PRIMARY triplet points at the ESCALATION snapshot, while the
                // base (escalation_triplet) points at the expected/genesis
                // snapshot. Both triplets share ONE pre-commitment, so the
                // seal holds if either triplet references the expected
                // snapshot (plain write) or the node is a valid escalation.
                let primary_ok = a.triplet.policy_snapshot == expected_snapshot_cid
                    && precommitment_holds(n, &a.triplet.audit_precommit);
                let escalated_ok = a
                    .escalation_triplet
                    .as_ref()
                    .map(|et| {
                        et.policy_snapshot == expected_snapshot_cid
                            && precommitment_holds(n, &et.audit_precommit)
                    })
                    .unwrap_or(false);
                primary_ok || escalated_ok
            })
            .unwrap_or(false);

        all_cids &= rederives;
        all_prev &= prev_ok;
        all_audit &= audit_ok;
        all_sig &= sig_ok;
        all_pre &= pre_ok;

        per_node.push(NodeAudit {
            cid: n.cid.clone(),
            depth: n.depth,
            cid_rederives: rederives,
            prev_links_to_genesis: prev_ok,
            carries_audit_strand: audit_ok,
            triplet_signature_ok: sig_ok,
            precommitment_ok: pre_ok,
        });
    }

    // Single-head chain check: exactly one genesis, and walking from the head
    // backward reaches every node (no fork — the m3 single-writer invariant).
    let genesis_count = nodes.iter().filter(|n| n.body.prev.is_none()).count();
    let single_head_chain = genesis_count == 1 && {
        let head = engine.head();
        let mut seen = std::collections::HashSet::new();
        let mut cur = head.map(|h| h.cid.clone());
        while let Some(c) = cur {
            seen.insert(c.clone());
            cur = engine.log.get(&c).and_then(|n| n.body.prev.clone());
        }
        seen.len() == nodes.len()
    };

    DriveAudit {
        node_count: nodes.len(),
        all_cids_rederive: all_cids,
        all_prev_links_close: all_prev,
        all_nodes_carry_audit_strand: all_audit,
        all_triplet_signatures_ok: all_sig,
        all_precommitments_ok: all_pre,
        single_head_chain,
        clean: false,
        per_node,
    }
}

/// M3 "no corruption" witness — re-derived CID must equal the stored CID.
fn cid_rederives(n: &Node) -> bool {
    let rebuilt = cid_from_body(&NodeBody {
        prev: n.body.prev.clone(),
        op: n.body.op.clone(),
        target: n.body.target.clone(),
        payload: n.body.payload.clone(),
    });
    rebuilt == n.cid
}

/// Re-derive the audit pre-commitment for a node and compare with the value
/// the write path bound at commit time. The pre-commitment is
/// hash(cid(body)) computed BEFORE the append; it must still equal the hash
/// of the post-commit CID — that is the tamper-evident seal.
fn precommitment_holds(node: &Node, bound_precommit: &str) -> bool {
    let body = NodeBody {
        prev: node.body.prev.clone(),
        op: node.body.op.clone(),
        target: node.body.target.clone(),
        payload: node.body.payload.clone(),
    };
    let recomputed = braid_core::crypto::hex(&braid_core::crypto::hash(cid_from_body(&body).as_bytes()));
    recomputed == bound_precommit
}

#[cfg(test)]
mod tests {
    use super::*;
    use braid_core::crypto::new_signing_key;
    use braid_core::engine::BraidEngine;
    use braid_core::policy::{policy_from_toml, PolicySnapshot};
    use braid_core::Capability;

    const TEST_SEED: &str = r#"
name = "genesis-test"
version = 1
default_deny = true

[[rules]]
allow = true
capability = "write:note:*"
"#;

    fn fresh(snapshot_id: &str) -> BraidEngine {
        let path = format!("/tmp/opencode/braid-drive-audit-{}.jsonl", std::process::id());
        let _ = std::fs::remove_file(&path);
        let sk = new_signing_key();
        let signer = braid_core::crypto::pub_key_hex(&ed25519_dalek::VerifyingKey::from(&sk));
        let mut engine = BraidEngine::new(&path, sk).unwrap();
        engine.register_snapshot(PolicySnapshot {
            cid: snapshot_id.into(),
            signer,
            signature: String::new(),
            policy: policy_from_toml(TEST_SEED).unwrap(),
        });
        engine
    }

    #[test]
    fn single_clean_chain_audits_clean() {
        let mut engine = fresh("snap-a");
        let cap = Capability::parse("write:note:*");
        for i in 0..3 {
            let r = engine
                .write(&cap, "snap-a", "write:note", "note", serde_json::json!({"i": i}))
                .unwrap();
            assert!(r.precommit_verified, "precommit must verify on clean write");
        }
        let report = audit_ledger(&engine, "snap-a");
        assert_eq!(report.node_count, 3);
        assert!(report.clean(), "clean chain must audit clean");
    }

    #[test]
    fn tampered_node_is_detected() {
        let mut engine = fresh("snap-a");
        let cap = Capability::parse("write:note:*");
        let mut cids = Vec::new();
        for i in 0..3 {
            let r = engine
                .write(&cap, "snap-a", "write:note", "note", serde_json::json!({"i": i}))
                .unwrap();
            cids.push(r.cid);
        }
        // corrupt one node's payload in the in-memory log (the audit must catch it)
        {
            let mut login = engine.log;
            let target = login.nodes.get_mut(&cids[1]).unwrap();
            target.body.payload = serde_json::json!({"i": 999, "corrupted": true});
            engine.log = login;
        }
        let report = audit_ledger(&engine, "snap-a");
        assert!(!report.clean(), "tampered node must fail the audit");
        assert!(!report.all_cids_rederive);
    }
}