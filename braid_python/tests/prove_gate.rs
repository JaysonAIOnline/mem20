//! The Python-facing `prove()` must be the real provenance gate, not just a
//! content-hash check.
//!
//! Regression test for a real gap: `PyBraidEngine::prove` called
//! `BraidLog::verify`, which only re-derives the CID from the body. That means a
//! node whose signature had been forged, replaced or stripped would still report
//! as "proven" to every Python caller - including the dream engine's durability
//! checks and braid_bridge. braid_her, braid_ui_bridge and intent.rs already used
//! the stronger `node_is_proven` (signature AND precommitment), so Python was the
//! odd one out and the weakest.
//!
//! These tests pin the difference: tampering with content, with the signature, or
//! with the precommitment must each be caught, and an untouched node must pass.

use braid_core::crypto;
use braid_core::engine::{AuditStrand, node_is_proven};
use braid_core::storage::{BraidLog, Node, NodeBody, cid_from_body};

/// A signed node with a valid CID and a valid signature, as a real commit makes.
fn signed_node(prev: Option<String>, op: &str, payload: serde_json::Value) -> Node {
    let (body, mut node) = Node::new(prev, op, "test:target", payload.clone(), "signer-hex");
    let signer = crypto::new_signing_key();
    let mut audit = AuditStrand {
        triplet: braid_core::engine::BraidedTriplet {
            capability: "agent:write:*".into(),
            policy_snapshot: "snap-genesis-1".into(),
            audit_precommit: crypto::hex(&crypto::hash(body_cid(&body).as_bytes())),
            policy_signer: "policy-signer".into(),
        },
        signed_by: crypto::pub_key_hex(&signer.verifying_key()),
        signature: String::new(),
        escalation_triplet: None,
    };
    let bind = audit.signed_payload().unwrap();
    audit.signature = crypto::hex(&crypto::sign(&signer, &bind));
    node.signer = audit.signed_by.clone();
    node.audit = Some(audit);
    node
}

fn body_cid(body: &NodeBody) -> String {
    cid_from_body(body)
}

fn tmp_log(tag: &str) -> String {
    let path = format!("/tmp/opencode/braid-prove-{}-{}.jsonl", tag, std::process::id());
    let _ = std::fs::remove_file(&path);
    path
}

#[test]
fn an_untouched_node_is_proven() {
    let path = tmp_log("clean");
    let mut log = BraidLog::open(&path).unwrap();
    let node = signed_node(None, "write:fact", serde_json::json!({"n": 1}));
    let (cid, _) = log.append(node);
    let stored = log.get(&cid).unwrap().clone();
    assert!(node_is_proven(&stored), "an honest node must be proven");
    let _ = std::fs::remove_file(&path);
}

#[test]
fn a_forged_signature_is_not_proven_even_though_the_cid_is_correct() {
    // This is the gap: content hash valid, provenance invalid.
    let path = tmp_log("forged-sig");
    let mut log = BraidLog::open(&path).unwrap();
    let node = signed_node(None, "write:fact", serde_json::json!({"n": 1}));
    let (cid, _) = log.append(node);
    let mut stored = log.get(&cid).unwrap().clone();

    // Replace the signature with a valid-format but wrong one. The CID is
    // untouched, so the old content-only check would still pass this.
    let mut bytes = [0u8; 64];
    bytes[0] = 0x42;
    stored.audit.as_mut().unwrap().signature = crypto::hex(&bytes);

    assert!(log.verify(&stored.cid), "the content hash is still correct...");
    assert!(
        !node_is_proven(&stored),
        "...but a forged signature must not be reported as proven"
    );
    let _ = std::fs::remove_file(&path);
}

#[test]
fn a_stripped_audit_strand_is_not_proven() {
    let path = tmp_log("no-audit");
    let mut log = BraidLog::open(&path).unwrap();
    let node = signed_node(None, "write:fact", serde_json::json!({"n": 1}));
    let (cid, _) = log.append(node);
    let mut stored = log.get(&cid).unwrap().clone();
    stored.audit = None;
    assert!(log.verify(&stored.cid), "content hash still correct");
    assert!(!node_is_proven(&stored), "no audit strand means not proven");
    let _ = std::fs::remove_file(&path);
}

#[test]
fn a_broken_precommitment_is_not_proven() {
    let path = tmp_log("bad-precommit");
    let mut log = BraidLog::open(&path).unwrap();
    let node = signed_node(None, "write:fact", serde_json::json!({"n": 1}));
    let (cid, _) = log.append(node);
    let mut stored = log.get(&cid).unwrap().clone();
    stored
        .audit
        .as_mut()
        .unwrap()
        .triplet
        .audit_precommit = "00".repeat(32);
    assert!(log.verify(&stored.cid), "content hash still correct");
    assert!(
        !node_is_proven(&stored),
        "a precommitment that no longer binds the CID must not be proven"
    );
    let _ = std::fs::remove_file(&path);
}

#[test]
fn tampered_content_is_caught_by_both_checks() {
    let path = tmp_log("tampered-content");
    let mut log = BraidLog::open(&path).unwrap();
    let node = signed_node(None, "write:fact", serde_json::json!({"n": 1}));
    let (cid, _) = log.append(node);
    let mut stored = log.get(&cid).unwrap().clone();
    stored.body.payload = serde_json::json!({"n": 999});
    assert_ne!(
        cid_from_body(&stored.body),
        stored.cid,
        "content hash must catch this"
    );
    assert!(!node_is_proven(&stored));
    let _ = std::fs::remove_file(&path);
}
