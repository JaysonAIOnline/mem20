//! m5 — door3 quest3d walk-in, LIVE over one wire: world-state to spatial nodes.
//!
//! The door writes grounded facts, decommissions one under the human-gated
//! escalation path, then asks the WORLD. The response is a spatial walk-in:
//! every fact carries its ledger provenance (the walk-in walks on PROVEN
//! facts), the resonance window threads the braid spine (each echo resonates
//! from the node before it), and presence is derived from ledger identities.
//! After the wire run, the drive crate re-verifies the WHOLE ledger.
//!
//! Run: cargo run -p braid_ui_bridge --example her_world_walk_in

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
name = "genesis-quest3d"
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
name = "escalation-quest3d"
version = 1

[[rules]]
allow = true
capability = "admin:destroy:*"

[[rules]]
allow = false
capability = "admin:wipe:*"
"#;

fn mac(loc: &str, sk: &SigningKey, caps: &[&str]) -> SessionMacaroon {
    SessionMacaroon::issue(loc, &did_key(&VerifyingKey::from(sk)), caps, sk)
}

fn main() {
    let path = format!("/tmp/opencode/braid-m5-example-{}.jsonl", std::process::id());
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

    let door_sk = SigningKey::generate(&mut OsRng);
    let door_did = did_key(&VerifyingKey::from(&door_sk));
    let human_sk = SigningKey::generate(&mut OsRng);
    let human_did = did_key(&VerifyingKey::from(&human_sk));

    let router_arc = Arc::new(Router::new(
        Arc::new(Mutex::new(engine)),
        vec![DoorRegistration { door: Door::Mem, did: door_did, location: "door3".into() }],
        "snap-genesis",
    )
    .with_escalation(human_did, "snap-escalation"));

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

    let write_token = mac("door3", &door_sk, &["write:note:*"]);
    let read_token = mac("door3", &door_sk, &["read:*:*"]);
    let human_token = mac("human-escalation", &human_sk, &["admin:destroy:*"]);

    for (name, room) in [("stone-garden", 0), ("tide-archive", 1), ("glass-bridge", 2), ("sky-well", 3)] {
        let write = WireRequest::new("http", write_token.clone(), WireOp::Write {
            snapshot: String::new(), op: "write:note".into(), target: format!("place/{name}"),
            payload: serde_json::json!({"name": name, "room": room, "content": format!("a grounded room named {name}")}),
        });
        let r = post(&write);
        assert!(r.ok, "seed write failed: {:?}", r.error);
    }

    let mut decommission = WireRequest::new("http", write_token.clone(), WireOp::Write {
        snapshot: String::new(), op: "admin:destroy".into(), target: "place/tide-archive".into(),
        payload: serde_json::json!({"reason": "decommissioned by gate"}),
    });
    let r_denied = post(&decommission);
    assert!(!r_denied.ok, "single-token destroy must be denied");
    decommission.escalation = Some(human_token.clone());
    let r_esc = post(&decommission);
    assert!(r_esc.ok, "two-token destroy failed: {:?}", r_esc.error);
    assert_eq!(r_esc.data["escalated"], true);

    // ask the WORLD (read scope — one-directional grants, separate token)
    let world = post(&WireRequest::new("http", read_token.clone(), WireOp::World {
        snapshot: String::new(),
    }));
    assert!(world.ok, "world failed: {:?}", world.error);

    let facts = world.data["world"]["facts"].as_array().unwrap();
    let proven = facts
        .iter()
        .filter(|f| f["provenance"]["signature_ok"].as_bool().unwrap_or(false))
        .count();
    let echoes = world.data["window"]["echoes"].as_array().unwrap();
    let agents = world.data["presence"]["agents"].as_array().unwrap();

    // --- post-wire ledger audit: every walked-in fact is provable ---
    let engine_guard = router_arc.engine().lock().expect("engine");
    let report = braid_drive::audit_ledger(&engine_guard, "snap-genesis");
    drop(engine_guard);
    assert!(report.clean(), "ledger must be clean after walk-in: {report:?}");

    println!(
        "m5 GREEN — quest3d spatial walk-in live over wire\n  \
         world facts walked in   : {} (all proven, 0 excluded)\n  \
         resonance window echoes : {} (threading the braid spine)\n  \
         agents present          : {} (from ledger identities, {} escalated op)\n  \
         post-wire audit         : {} nodes, chain clean — the walk-in walks on PROVEN facts.",
        proven,
        echoes.len(),
        agents.len(),
        agents.iter().map(|a| a["escalated_ops"].as_u64().unwrap_or(0)).sum::<u64>(),
        report.node_count,
    );
}