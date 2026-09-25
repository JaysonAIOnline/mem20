//! m4 — the godmode escalation gate, LIVE over one wire.
//!
//! door2 (godmode) holds a single creative token (`write:*:*`). A destructive
//! `admin:destroy` op is REFUSED with only that token — the door cannot mint
//! destructive power. The human's SECOND macaroon upgrades it, and the
//! committed node carries TWO braided triplets. After the wire run, the drive
//! crate re-verifies the WHOLE ledger — the escalated node is provable, not
//! just relocatable. Nuclear wipe stays denied even with both tokens.
//!
//! Run: cargo run -p braid_ui_bridge --example godmode_gate_over_wire

use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;

use braid_core::crypto::new_signing_key;
use braid_core::engine::BraidEngine;
use braid_core::policy::{policy_from_toml, PolicySnapshot};
use braid_keys::{did_key, SessionMacaroon};
use braid_wire::{http_post_raw, BraidWireServer, WireOp, WireRequest, WireResponse};
use ed25519_dalek::{SigningKey, VerifyingKey};
use rand::rngs::OsRng;

use braid_ui_bridge::frontdoor::{Door, DoorRegistration, Router};
use braid_ui_bridge::handler_from;

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

fn mac(loc: &str, id: &str, caps: &[&str], sk: &SigningKey) -> SessionMacaroon {
    SessionMacaroon::issue(loc, id, caps, sk)
}

fn main() {
    // --- single write authority ---
    let path = format!("/tmp/opencode/braid-m4-example-{}.jsonl", std::process::id());
    let _ = std::fs::remove_file(&path);
    let sk = new_signing_key();
    let engine_id = braid_core::crypto::pub_key_hex(&VerifyingKey::from(&sk));
    let mut engine = BraidEngine::new(&path, sk).expect("engine boots");
    engine.register_snapshot(PolicySnapshot {
        cid: "snap-genesis".into(),
        signer: engine_id.clone(),
        signature: String::new(),
        policy: policy_from_toml(GENESIS).expect("genesis"),
    });
    engine.register_snapshot(PolicySnapshot {
        cid: "snap-escalation".into(),
        signer: engine_id.clone(),
        signature: String::new(),
        policy: policy_from_toml(ESCALATION).expect("escalation"),
    });

    // --- identities ---
    let door_sk = SigningKey::generate(&mut OsRng);
    let door_did = did_key(&VerifyingKey::from(&door_sk));
    let door_token = mac("door2", "hero-door", &["write:*:*", "invoke:*:*", "read:*:*"], &door_sk);
    let human_sk = SigningKey::generate(&mut OsRng);
    let human_did = did_key(&VerifyingKey::from(&human_sk));
    let human_token = mac("human-escalation", "alice", &["admin:destroy:*"], &human_sk);

    // --- router with the godmode gate ---
    let router_arc = Arc::new(Router::new(
        Arc::new(Mutex::new(engine)),
        vec![DoorRegistration { door: Door::Axiom, did: door_did, location: "door2".into() }],
        "snap-genesis",
    )
    .with_escalation(human_did, "snap-escalation"));

    // --- live wire ---
    let handler = handler_from(router_arc.clone());
    let server = BraidWireServer::new("127.0.0.1:0", handler).expect("bind");
    let addr = server.local_addr();
    thread::spawn(move || {
        let _ = server.run();
    });
    thread::sleep(Duration::from_millis(150));

    let post = |req: &WireRequest| {
        let body = serde_json::to_string(req).unwrap();
        http_post_raw(&addr, "/v1/op", &body).unwrap_or_else(WireResponse::err)
    };

    let creative = WireRequest::new("http", door_token.clone(), WireOp::Write {
        snapshot: String::new(), op: "write:note".into(), target: "note".into(),
        payload: serde_json::json!({"content": "create"}),
    });
    let r_creative = post(&creative);
    assert!(r_creative.ok, "creative write failed: {:?}", r_creative.error);
    assert_eq!(r_creative.data["escalated"], false);

    let mut destructive = WireRequest::new("http", door_token.clone(), WireOp::Write {
        snapshot: String::new(), op: "admin:destroy".into(), target: "zone-a".into(),
        payload: serde_json::json!({"reason": "authorized-zone"}),
    });
    let r_denied = post(&destructive);
    assert!(!r_denied.ok, "single-token destructive must be denied");
    assert!(r_denied.error.as_deref().unwrap_or("").contains("human-gated"),
        "denial must require the human token: {:?}", r_denied.error);

    destructive.escalation = Some(human_token.clone());
    let r_escalated = post(&destructive);
    assert!(r_escalated.ok, "two-token destructive failed: {:?}", r_escalated.error);
    assert_eq!(r_escalated.data["escalated"], true);

    let mut wipe = WireRequest::new("http", door_token.clone(), WireOp::Write {
        snapshot: String::new(), op: "admin:wipe".into(), target: "*".into(),
        payload: serde_json::json!({"nuclear": true}),
    });
    wipe.escalation = Some(human_token.clone());
    let r_wipe = post(&wipe);
    assert!(!r_wipe.ok, "nuclear wipe must be denied even with two tokens: {:?}", r_wipe.error);

    // --- post-wire ledger audit: the escalated node is provable ---
    let engine_guard = router_arc.engine().lock().expect("engine");
    let report = braid_drive::audit_ledger(&engine_guard, "snap-genesis");
    drop(engine_guard);
    assert!(report.clean(), "ledger audit must be clean after escalation: {report:?}");
    assert_eq!(report.node_count, 2, "one creative + one escalated node");

    println!(
        "m4 GREEN — godmode gate live over wire\n  \
         single token write:note           : pass (escalated=false)\n  \
         single token admin:destroy        : DENIED (no human token)\n  \
         two tokens admin:destroy          : pass (escalated=true, double triplet on node)\n  \
         two tokens admin:wipe (nuclear)   : DENIED (wipe floor holds)\n  \
         post-wire audit: {} nodes, chain clean — escalated node carries two bound triplets on-chain.",
        report.node_count
    );
}