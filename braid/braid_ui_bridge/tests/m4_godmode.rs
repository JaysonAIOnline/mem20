//! m4 — godmode escalation gate, live over the wire.
//!
//! The door token alone carries `read:*/write:*/invoke:*` (creative). A
//! DESTRUCTIVE op (`admin:destroy`) is REFUSED with just the door token, even
//! though the macaroon otherwise verifies — proving no single-token path to
//! godmode. It only commits when a SECOND, human-gated escalation macaroon
//! accompanies the write AND the escalation policy snapshot licenses it. The
//! resulting node carries TWO bound triplets. The wipe floor stays denied
//! even with two valid tokens.

use std::sync::{Arc, Mutex};

use braid_core::crypto::new_signing_key;
use braid_core::engine::BraidEngine;
use braid_core::policy::{policy_from_toml, PolicySnapshot};
use braid_keys::{did_key, SessionMacaroon};
use braid_ui_bridge::frontdoor::{Door, DoorRegistration, Router};
use braid_ui_bridge::handler_from;
use braid_wire::{WireOp, WireRequest};
use ed25519_dalek::{SigningKey, VerifyingKey};
use rand::rngs::OsRng;

const GENESIS: &str = r#"
name = "genesis"
version = 1

[[rules]]
allow = true
capability = "read:*:*"

[[rules]]
allow = true
capability = "write:*:*"

[[rules]]
allow = true
capability = "invoke:*:*"

[[rules]]
allow = false
capability = "admin:*:*"
"#;

const ESCALATION: &str = r#"
name = "escalation"
version = 1

[[rules]]
allow = true
capability = "admin:destroy:*"

[[rules]]
allow = true
capability = "admin:delete:*"

[[rules]]
allow = true
capability = "admin:create:*"

[[rules]]
allow = false
capability = "admin:wipe:*"
"#;

fn boot() -> (BraidEngine, String) {
    use std::sync::atomic::{AtomicU64, Ordering};
    static SEQ: AtomicU64 = AtomicU64::new(0);
    let seq = SEQ.fetch_add(1, Ordering::Relaxed);
    let path = format!("/tmp/opencode/braid-m4-{}-{seq}.jsonl", std::process::id());
    let _ = std::fs::remove_file(&path);
    let sk = new_signing_key();
    let engine_id = braid_core::crypto::pub_key_hex(&VerifyingKey::from(&sk));
    let mut engine = BraidEngine::new(&path, sk).expect("engine boots");

    let genesis = PolicySnapshot {
        cid: "snap-genesis".into(),
        signer: engine_id.clone(),
        signature: String::new(),
        policy: policy_from_toml(GENESIS).expect("genesis"),
    };
    let esc = PolicySnapshot {
        cid: "snap-escalation".into(),
        signer: engine_id.clone(),
        signature: String::new(),
        policy: policy_from_toml(ESCALATION).expect("escalation"),
    };
    engine.register_snapshot(genesis);
    engine.register_snapshot(esc);
    (engine, engine_id)
}

#[test]
fn two_token_escalation_commits_with_double_triplet_over_wire() {
    // Door2 (godmode): creative caps only via session macaroon.
    let door_sk = SigningKey::generate(&mut OsRng);
    let door_did = did_key(&VerifyingKey::from(&door_sk));
    let door_token = SessionMacaroon::issue("door2", "hero-door", &["write:*:*", "invoke:*:*", "read:*:*"], &door_sk);

    // Human gate: a SEPARATE root identity signs the escalation macaroon.
    let human_sk = SigningKey::generate(&mut OsRng);
    let human_did = did_key(&VerifyingKey::from(&human_sk));
    let human_token = SessionMacaroon::issue("human-escalation", "alice", &["admin:destroy:*"], &human_sk);

    let (engine, engine_id) = boot();
    let router = Router::new(
        Arc::new(Mutex::new(engine)),
        vec![DoorRegistration { door: Door::Axiom, did: door_did.clone(), location: "door2".into() }],
        "snap-genesis",
    )
    .with_escalation(human_did, "snap-escalation");
    let _ = engine_id;

    // Creative write with the single godmode token — allowed.
    let creative = WireRequest::new(
        "test",
        door_token.clone(),
        WireOp::Write { snapshot: String::new(), op: "write:note".into(), target: "note".into(), payload: serde_json::json!({"content": "create"}) },
    );
    let handler = handler_from(Arc::new(router));
    let r_creative = handler(creative);
    assert!(r_creative.ok, "creative single-token write must pass: {:?}", r_creative.error);
    assert_eq!(r_creative.data["escalated"], false, "creative op is not escalated");

    // Destructive write with ONLY the door token — REFUSED by the gate
    // (escalation macaroon absent). No single-token admin path.
    let destructive_alone = WireRequest::new(
        "test",
        door_token.clone(),
        WireOp::Write { snapshot: String::new(), op: "admin:destroy".into(), target: "zone-a".into(), payload: serde_json::json!({"reason": "test"}) },
    );
    let r_denied = handler(destructive_alone);
    assert!(!r_denied.ok, "single-token destructive must be denied");
    assert!(
        r_denied.error.as_deref().unwrap_or("").contains("human-gated"),
        "denial must name the escalation requirement: {:?}",
        r_denied.error
    );

    // Destructive write WITH the second human token — commits, escalated=true.
    let mut escalated_req = WireRequest::new(
        "test",
        door_token.clone(),
        WireOp::Write { snapshot: String::new(), op: "admin:destroy".into(), target: "zone-a".into(), payload: serde_json::json!({"reason": "authorized-zone"}) },
    );
    escalated_req.escalation = Some(human_token.clone());
    let r_escalated = handler(escalated_req);
    assert!(r_escalated.ok, "two-token destructive must commit: {:?}", r_escalated.error);
    assert_eq!(r_escalated.data["escalated"], true, "destructive op is escalated");
    assert!(r_escalated.triplet.is_some(), "response echoes the braided triplet");
    let esc_cid = r_escalated.data["cid"].as_str().unwrap().to_string();

    // Wipe floor: still denied even with both tokens (policy keeps admin:wipe).
    let mut wipe_req = WireRequest::new(
        "test",
        door_token.clone(),
        WireOp::Write { snapshot: String::new(), op: "admin:wipe".into(), target: "*".into(), payload: serde_json::json!({"nuclear": true}) },
    );
    wipe_req.escalation = Some(human_token.clone());
    let r_wipe = handler(wipe_req);
    assert!(!r_wipe.ok, "nuclear wipe stays denied even with two tokens: {:?}", r_wipe.error);

    // Confirm the escalated node carries the double triplet on-chain.
    let get_req = WireRequest::new(
        "test",
        door_token.clone(),
        WireOp::Get { snapshot: "snap-genesis".into(), cid: esc_cid.clone() },
    );
    let r_get = handler(get_req);
    assert!(r_get.ok, "get escalated node: {:?}", r_get.error);
    let strand = &r_get.data["audit"];
    assert_eq!(strand["escalation_triplet"]["capability"], "write:*:*", "base triplet recorded");
    assert_eq!(strand["triplet"]["capability"], "admin:destroy:*", "escalation triplet is primary");
    assert_eq!(strand["escalation_triplet"]["policy_snapshot"], "snap-genesis");
    assert_eq!(strand["triplet"]["policy_snapshot"], "snap-escalation");
    println!("m4 GREEN — two-token escalation commits double-triplet node; single-token admin + nuclear wipe both refused.");
}

#[test]
fn escalation_refused_without_registered_gate() {
    let door_sk = SigningKey::generate(&mut OsRng);
    let door_did = did_key(&VerifyingKey::from(&door_sk));
    let door_token = SessionMacaroon::issue("door2", "hero-door", &["write:*:*"], &door_sk);
    let human_sk = SigningKey::generate(&mut OsRng);
    let _human_did = did_key(&VerifyingKey::from(&human_sk)); // no gate registered — DID intentionally never wired
    let human_token = SessionMacaroon::issue("human-escalation", "alice", &["admin:destroy:*"], &human_sk);

    let (engine, _) = boot();
    // NOTE: no .with_escalation() — bridge intentionally has no godmode gate.
    let router = Router::new(
        Arc::new(Mutex::new(engine)),
        vec![DoorRegistration { door: Door::Axiom, did: door_did, location: "door2".into() }],
        "snap-genesis",
    );
    let handler = handler_from(Arc::new(router));

    let mut req = WireRequest::new(
        "test",
        door_token,
        WireOp::Write { snapshot: String::new(), op: "admin:destroy".into(), target: "x".into(), payload: serde_json::json!({}) },
    );
    req.escalation = Some(human_token);
    let r = handler(req);
    assert!(!r.ok, "no escalation gate => destructive unreachable");
    assert!(r.error.as_deref().unwrap_or("").contains("no escalation gate"), "{:?}", r.error);
    println!("m4 GREEN — no registered gate => admin surface fully unreachable.");
}