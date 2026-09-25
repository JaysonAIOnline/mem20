//! FIRST END-TO-END braid test: write -> proof -> read under ONE identity.
//!
//! Exercises the full m1 invariant: a single signer's writes form a Merkle-DAG
//! whose every node binds (capability token + policy snapshot + audit
//! pre-commitment), proofs walk back to genesis, and reads are capability
//! gated by the same policy that admitted the writes.

use std::sync::Arc;

use braid_core::context::{BraidContext, MockContext};
use braid_core::crypto::new_signing_key;
use braid_core::engine::BraidEngine;
use braid_core::policy::{policy_from_toml, PolicySnapshot};

const POLICY_SEED: &str = r#"
name = "genesis"
version = 1

[[rules]]
allow = true
capability = "read:timeline:*"

[[rules]]
allow = true
capability = "write:note:*"
"#;

fn tmp_path(tag: &str) -> String {
    let pid = std::process::id();
    format!("/tmp/opencode/braid-e2e-{pid}-{tag}.jsonl")
}

#[test]
fn single_identity_write_proof_read() {
    let path = tmp_path("m1");
    let _ = std::fs::remove_file(&path);

    let sk = new_signing_key();
    let mut engine = BraidEngine::new(&path, sk).expect("engine boots");
    let engine_id = engine.id_hex();

    // Policy seed -> snapshot, and the engine signs nothing yet (snapshots are
    // registration data). Register it so writes/reads can reference it.
    let policy = policy_from_toml(POLICY_SEED).expect("parse seed");
    let snapshot = PolicySnapshot {
        cid: "snap-genesis-v1".into(),
        signer: engine_id.clone(),
        signature: String::new(),
        policy,
    };
    engine.register_snapshot(snapshot);

    // --- braid_write: three notes as one identity ---
    let cap_read = braid_core::Capability::new("read", "timeline", "*");
    let cap_write = braid_core::Capability::new("write", "note", "*");

    let r1 = engine.write(
        &cap_write,
        "snap-genesis-v1",
        "write:note",
        "note",
        serde_json::json!({ "content": "genesis note", "order": 0 }),
    ).expect("write 1 ok");
    assert!(r1.ok);
    assert_eq!(r1.depth, 0);
    assert!(r1.precommit_verified, "pre-commitment must bind to final node");

    let r2 = engine.write(
        &cap_write,
        "snap-genesis-v1",
        "write:note",
        "note",
        serde_json::json!({ "content": "second note", "order": 1 }),
    ).expect("write 2 ok");
    assert!(r2.ok);
    assert_eq!(r2.depth, 1);
    assert!(r2.precommit_verified);

    let r3 = engine.write(
        &cap_write,
        "snap-genesis-v1",
        "write:note",
        "note",
        serde_json::json!({ "content": "third note", "order": 2 }),
    ).expect("write 3 ok");
    assert!(r3.ok);
    assert_eq!(r3.depth, 2);

    // --- proof: spine from head to genesis is 3 hops ---
    let head = engine.head().expect("head exists");
    let proof = engine.proof(&head.cid);
    assert_eq!(proof.len(), 3, "3 nodes: genesis->middle->head");

    // Each node carries the audit strand (triplet bound at commit).
    assert!(head.audit.is_some(), "head must carry audit strand");
    assert_eq!(head.audit.as_ref().unwrap().triplet.capability, "write:note:*");

    // Content addressing integrity of every node.
    assert!(engine.verify_node(&r1.cid));
    assert!(engine.verify_node(&r2.cid));
    assert!(engine.verify_node(&r3.cid));

    // --- braid_read: capability-gated read casts the full timeline ---
    let all = engine.read(&cap_read, "snap-genesis-v1", None).expect("read survives");
    assert_eq!(all.len(), 3, "read returns all 3 committed notes");
    let first = all.first().unwrap();
    assert_eq!(first.signer, engine_id, "identity matches the writer");
    assert_eq!(first.body.payload["order"], serde_json::json!(0));

    // Denied read: a raw capability not in the policy must be refused.
    let cap_admin = braid_core::Capability::new("admin", "*", "*");
    let denied = engine.read(&cap_admin, "snap-genesis-v1", None);
    assert!(denied.is_err(), "admin read must be denied by default_deny");

    // --- context mock wires in and can watch the audit ---
    let ctx = Arc::new(MockContext::new("her"));
    for n in engine.log.items_for_audit() {
        ctx.audit_note(&n.cid, "committed to braid");
    }
    ctx.audit_note(&head.cid, "head observed by witness door");

    let _ = std::fs::remove_file(&path);
    let _ = ctx;
}

#[test]
fn reopen_preserves_dag() {
    let path = tmp_path("reopen");
    let _ = std::fs::remove_file(&path);

    let sk = new_signing_key();
    let policy = policy_from_toml(POLICY_SEED).expect("parse seed");
    let snapshot = PolicySnapshot {
        cid: "snap-reopen".into(),
        signer: "x".into(),
        signature: String::new(),
        policy: policy.clone(),
    };
    let cap_write = braid_core::Capability::new("write", "note", "*");

    {
        let mut engine = BraidEngine::new(&path, sk).expect("boot");
        engine.register_snapshot(snapshot);
        engine.write(&cap_write, "snap-reopen", "write:note", "note",
            serde_json::json!({"n": 1})).unwrap();
        engine.write(&cap_write, "snap-reopen", "write:note", "note",
            serde_json::json!({"n": 2})).unwrap();
    }

    // Reopen the SAME log on disk with a fresh identity; DAG must persist.
    let sk2 = new_signing_key();
    let mut engine = BraidEngine::new(&path, sk2).expect("reopen");
    engine.register_snapshot(PolicySnapshot {
        cid: "snap-reopen".into(),
        signer: "x".into(),
        signature: String::new(),
        policy,
    });
    assert_eq!(engine.log.len(), 2);
    assert!(engine.verify_node(&engine.head().unwrap().cid));

    let _ = std::fs::remove_file(&path);
}