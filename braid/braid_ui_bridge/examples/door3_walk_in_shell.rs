//! m6 — door3 walk-in SHELL, live: the spatial scene is a reachable URL.
//!
//! The ONE bridge now also serves the walk-in: open the printed URL in a
//! browser and the grounded ledger walks in — every object is a PROVEN node
//! (position + provenance), the resonance window threads the braid spine, and
//! agents surface from ledger identities. The page itself is keyless; the
//! read token that powers `/world` lives on the bridge.
//!
//! Run: cargo run -p braid_ui_bridge --example door3_walk_in_shell

use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;

use braid_core::crypto::new_signing_key;
use braid_core::engine::BraidEngine;
use braid_core::policy::{policy_from_toml, PolicySnapshot};
use braid_keys::{did_key, SessionMacaroon};
use braid_ui_bridge::frontdoor::{Door, DoorRegistration, Router};
use braid_ui_bridge::{door3_shell, handler_from};
use braid_wire::{http_get_raw, http_post_raw, BraidWireServer, WireOp, WireRequest};
use ed25519_dalek::{SigningKey, VerifyingKey};
use rand::rngs::OsRng;

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
    let path = format!("/tmp/opencode/braid-m6-shell-example-{}.jsonl", std::process::id());
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
        signer: engine_id,
        signature: String::new(),
        policy: policy_from_toml(ESCALATION).expect("escalation"),
    });

    let door_sk = SigningKey::generate(&mut OsRng);
    let door_did = did_key(&VerifyingKey::from(&door_sk));
    let human_sk = SigningKey::generate(&mut OsRng);
    let human_did = did_key(&VerifyingKey::from(&human_sk));

    let router = Arc::new(Router::new(
        Arc::new(Mutex::new(engine)),
        vec![DoorRegistration { door: Door::Mem, did: door_did, location: "door3".into() }],
        "snap-genesis",
    )
    .with_escalation(human_did, "snap-escalation"));

    let handler = handler_from(router.clone());
    let write_token = mac("door3", &door_sk, &["write:note:*"]);
    let read_token = mac("door3", &door_sk, &["read:*:*"]);
    let human_token = mac("human-escalation", &human_sk, &["admin:destroy:*"]);

    let server = BraidWireServer::new("127.0.0.1:8087", handler)
        .expect("bind 8087")
        .with_shell(door3_shell(read_token));
    thread::spawn(move || {
        let _ = server.run();
    });
    thread::sleep(Duration::from_millis(150));

    let post = |req: &WireRequest| {
        let body = serde_json::to_string(req).unwrap();
        http_post_raw("127.0.0.1:8087", "/v1/op", &body).unwrap_or_else(braid_wire::WireResponse::err)
    };

    for (room, name) in ["stone-garden", "tide-archive", "glass-bridge", "sky-well"].iter().enumerate() {
        let write = WireRequest::new("http", write_token.clone(), WireOp::Write {
            snapshot: String::new(),
            op: "write:note".into(),
            target: format!("place/{name}"),
            payload: serde_json::json!({"name": name, "room": room, "content": format!("a grounded room named {name}")}),
        });
        assert!(post(&write).ok, "seed write failed");
    }
    let mut decommission = WireRequest::new("http", write_token.clone(), WireOp::Write {
        snapshot: String::new(),
        op: "admin:destroy".into(),
        target: "place/tide-archive".into(),
        payload: serde_json::json!({"reason": "decommissioned by gate"}),
    });
    assert!(!post(&decommission).ok, "single-token destroy denied");
    decommission.escalation = Some(human_token.clone());
    let esc = post(&decommission);
    assert!(esc.ok, "two-token destroy failed: {:?}", esc.error);

    // prove the shell surface over real HTTP, in the terminal
    let (page_status, page) = http_get_raw("127.0.0.1:8087", "/").expect("GET /");
    assert_eq!(page_status, 200);
    assert!(page.to_lowercase().contains("text/html"));
    let (world_status, world_raw) = http_get_raw("127.0.0.1:8087", "/world").expect("GET /world");
    assert_eq!(world_status, 200);
    let world: braid_wire::WireResponse =
        serde_json::from_str(world_raw.split("\r\n\r\n").nth(1).unwrap()).expect("world json");
    assert!(world.ok, "world error: {:?}", world.error);

    let facts = world.data["world"]["facts"].as_array().unwrap();
    let proven = facts
        .iter()
        .filter(|f| f["provenance"]["signature_ok"].as_bool().unwrap_or(false))
        .count();
    let agents = world.data["presence"]["agents"].as_array().unwrap();
    let echoes = world.data["window"]["echoes"].as_array().unwrap();

    println!(
        "m6 GREEN — door3 walk-in shell served by the ONE bridge\n  \
         page    : http://127.0.0.1:8087/  (keyless; open in a browser)\n  \
         world   : http://127.0.0.1:8087/world ({} proven, {} excluded)\n  \
         walk-in : {} spatial objects at deterministic positions\n  \
         window  : {} echoes threading the braid spine\n  \
         agents  : {} from ledger identities ({} escalated op)\n  \
         wire    : POST /v1/op unchanged — every door uses the same surface.",
        proven,
        world.data["excluded"].as_u64().unwrap_or(0),
        facts.len(),
        echoes.len(),
        agents.len(),
        agents.iter().map(|a| a["escalated_ops"].as_u64().unwrap_or(0)).sum::<u64>(),
    );

    loop {
        thread::sleep(Duration::from_secs(3600));
    }
}