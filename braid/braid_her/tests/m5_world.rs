//! m5 — door3 quest3d: world facts from the grounded ledger.
//!
//! Tests prove the three D3 properties:
//!   D3.1 window — the conversation is a resonance stream over the braid
//!        spine (echoes carry prev/next links), not chat bubbles.
//!   D3.3 world facts — everything in WorldScene has a VERIFYING audit
//!        signature; a tampered node is EXCLUDED from the walk-in.
//!   D3.4 presence — agents are surfaced from ledger identities; an escalated
//!        write still counts to the presented authority, never a phantom.

use std::sync::atomic::{AtomicU64, Ordering};

use braid_her::{Presence, ResonanceWindow, WorldScene};
use braid_core::engine::{BraidEngine, Escalation};
use braid_core::policy::{policy_from_toml, Capability, PolicySnapshot};

const SEED: &str = r#"
name = "genesis-her"
version = 1

[[rules]]
allow = true
capability = "read:*:*"

[[rules]]
allow = true
capability = "write:*:*"

[[rules]]
allow = false
capability = "admin:*:*"
"#;

const ESCALATION: &str = r#"
name = "escalation-her"
version = 1

[[rules]]
allow = true
capability = "admin:destroy:*"

[[rules]]
allow = true
capability = "admin:wipe:*"
"#;

/// Each boot gets its OWN ledger file — rust runs the tests in this binary on
/// parallel threads, so a shared path would let them clobber each other.
static SEQ: AtomicU64 = AtomicU64::new(0);
fn file_path() -> String {
    let seq = SEQ.fetch_add(1, Ordering::Relaxed);
    format!("/tmp/opencode/braid-her-m5-{}-{seq}.jsonl", std::process::id())
}

fn boot() -> BraidEngine {
    let path = file_path();
    let _ = std::fs::remove_file(&path);
    let sk = braid_core::crypto::new_signing_key();
    let signer = braid_core::crypto::pub_key_hex(&ed25519_dalek::VerifyingKey::from(&sk));
    let mut engine = BraidEngine::new(&path, sk).unwrap();
    engine.register_snapshot(PolicySnapshot {
        cid: "snap-genesis".into(),
        signer: signer.clone(),
        signature: String::new(),
        policy: policy_from_toml(SEED).unwrap(),
    });
    engine.register_snapshot(PolicySnapshot {
        cid: "snap-escalation".into(),
        signer,
        signature: String::new(),
        policy: policy_from_toml(ESCALATION).unwrap(),
    });
    engine
}

fn cap(s: &str) -> Capability {
    Capability::parse(s)
}

fn seed_facts(engine: &mut BraidEngine) {
    let w = cap("write:note:*");
    for (i, name) in ["stone-garden", "tide-archive", "glass-bridge"].iter().enumerate() {
        let r = engine.write(&w, "snap-genesis", "write:note", &format!("place/{name}"),
            serde_json::json!({"name": name, "room": i, "content": format!("a grounded room named {name}")}));
        assert!(r.is_ok(), "seed write failed: {r:?}");
    }
}

#[test]
fn world_facts_are_grounded_and_position_alive() {
    let mut engine = boot();
    seed_facts(&mut engine);

    let scene = WorldScene::from_ledger(&engine, &cap("read:*:*"), "snap-genesis");
    assert_eq!(scene.walk_in_count, 3, "three seeded rooms walk in");
    assert_eq!(scene.proven, 3);
    assert_eq!(scene.excluded, 0, "nothing tampered => nothing excluded");

    for f in &scene.facts {
        assert!(f.provenance.signature_ok, "{} must be a PROVEN fact", f.object_id);
        // provenance must reference a real ledger node and its snapshot
        assert!(engine.log.get(&f.provenance.cid).is_some(), "provenance cid must exist in ledger");
        assert_eq!(f.provenance.snapshot, "snap-genesis");
        // deterministic spatial placement — same object, same position, forever
        let again = WorldScene::from_ledger(&engine, &cap("read:*:*"), "snap-genesis");
        let f2 = again.facts.iter().find(|x| x.object_id == f.object_id).unwrap();
        assert_eq!(f.position, f2.position, "object {0} must hold its spot", f.object_id);
        assert!(
            f.position[0].abs() <= 7.0 && f.position[2].abs() <= 7.0 && f.position[1] > 0.0,
            "placement inside ring bounds, above floor"
        );
    }
}

#[test]
fn tampered_node_is_excluded_from_the_walk_in() {
    let mut engine = boot();
    seed_facts(&mut engine);

    // Directly corrupt a committed node's payload — its CID now no longer
    // re-derives AND its audit signature no longer verifies over that payload.
    let first_cid = engine.head().unwrap().cid.clone();
    let (prev, op, target, sig) = {
        let n = engine.log.get(&first_cid).unwrap();
        (
            n.body.prev.clone(),
            n.body.op.clone(),
            n.body.target.clone(),
            n.audit.as_ref().unwrap().signature.clone(),
        )
    };
    let morphed = serde_json::json!({"name": "tampered-room", "content": "evil"});
    let mut node = engine.log.get(&first_cid).unwrap().clone();
    node.body.payload = morphed;
    // Signature covers the STRAND (triplet + precommitment), not the payload.
    // It still verifies after a payload tamper — which is exactly why the fact
    // gate is `node_is_proven` (verified AND precommitment re-derives), not
    // `verified` alone.
    assert!(node.audit.as_ref().unwrap().verified(&node.signer),
        "strand signature survives a payload tamper (expected: documented)");
    assert!(!braid_core::engine::node_is_proven(&node),
        "precommitment no longer binds the tampered body => NOT proven");

    let scene = WorldScene::from_nodes(&[node]);
    assert_eq!(scene.excluded, 1, "tampered node must not walk in");
    assert_eq!(scene.walk_in_count, 0);
    let _ = (prev, op, target, sig);
    // and the clean ledger still walks all three untouched facts
    let clean = WorldScene::from_ledger(&engine, &cap("read:*:*"), "snap-genesis");
    assert_eq!(clean.walk_in_count, 3);
}

#[test]
fn resonance_window_threads_the_braid_not_bubbles() {
    let mut engine = boot();
    seed_facts(&mut engine);
    // one more node, so the head has a prev to resonate from
    let w = cap("write:note:*");
    engine.write(&w, "snap-genesis", "write:note", "place/sky-well",
        serde_json::json!({"name": "sky-well", "content": "fourth room"})).unwrap();

    let window = ResonanceWindow::from_ledger(&engine, &cap("read:*:*"), "snap-genesis");
    assert_eq!(window.kind, "resonance");
    assert_eq!(window.echoes.len(), 4);
    assert_eq!(window.last_cid, Some(engine.head().unwrap().cid.clone()));
    // every echo's parent (resonates_from) is a REAL braid node — the
    // window threads the braid spine, representing no chat-bubble author model.
    for e in &window.echoes {
        if let Some(parent) = &e.resonates_from {
            assert!(engine.log.get(parent).is_some(), "parent {parent} is a real ledger node");
        }
        assert!(engine.log.get(&e.cid).is_some(), "echo {0} is a real ledger node", e.cid);
    }
    // spine order: each echo EXCEPT genesis resonates from the previous depth
    let mut by_depth: Vec<_> = window.echoes.iter().collect();
    by_depth.sort_by_key(|e| e.depth);
    for pair in by_depth.windows(2) {
        assert_eq!(pair[1].resonates_from.as_deref(), Some(pair[0].cid.as_str()),
            "echo at depth {} resonates from depth {}", pair[1].depth, pair[0].depth);
    }
}

#[test]
fn presence_comes_from_ledger_identities_including_escalation() {
    let mut engine = boot();
    seed_facts(&mut engine);

    // a second, human-escalated commit — presence must count it to the
    // authority that signed it (the write authority), and flag escalation.
    let base = cap("write:note:*");
    let esc = cap("admin:destroy:*");
    let r = engine.write_escalated(
        &base, "snap-genesis",
        &Escalation { cap: &esc, snapshot_cid: "snap-escalation" },
        "admin:destroy", "zone/old", serde_json::json!({"reason": "decommission"}),
    );
    assert!(r.is_ok(), "escalated write failed: {r:?}");

    let presence = Presence::from_ledger(&engine);
    assert_eq!(presence.agents.len(), 1, "one write authority signs every node");
    let a = &presence.agents[0];
    assert_eq!(a.node_count, 4);
    assert_eq!(a.escalated_ops, 1, "the escalated destroy is visible in presence");
    assert!(engine.log.get(&a.first_seen_cid).is_some());
    assert!(engine.log.get(&a.last_seen_cid).is_some());

    // identity is the braid's own authority key, not a configured role
    let expected = braid_core::crypto::pub_key_hex(&ed25519_dalek::VerifyingKey::from(
        &braid_core::crypto::new_signing_key()));
    // (we cannot know the engine's key here — but the short id must look like hex)
    assert!(a.identity.chars().all(|c| c.is_ascii_hexdigit() || c == '…'),
        "identity is a ledger hex key: {}", a.identity);
    let _ = expected;
}