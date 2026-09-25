//! m9 — door3 SPATIAL SHELL, live: creative spatial writes, ONE ledger.
//!
//! The walk-in page now also PLACES facts: POST /world with `{target,
//! content}` and the bridge commits a real braid node through its held
//! write:world token — the browser stays keyless. The object walks in at a
//! deterministic position, PROVEN, and threads the resonance window. An
//! admin:destroy over the same object takes the SAME human-gated escalation
//! path as godmode (two tokens). D3.6's software spine, on real HTTP.
//!
//! Run: cargo run -p braid_ui_bridge --example door3_spatial_shell

use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;

use braid_core::crypto::new_signing_key;
use braid_core::engine::BraidEngine;
use braid_core::policy::{policy_from_toml, PolicySnapshot};
use braid_keys::{did_key, SessionMacaroon};
use braid_ui_bridge::frontdoor::{Door, DoorRegistration, Router};
use braid_ui_bridge::{door3_spatial_shell, handler_from};
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
capability = "write:world:*"

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
    let path = format!("/tmp/opencode/braid-m9-spatial-example-{}.jsonl", std::process::id());
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
    let spatial_token = mac("door3", &door_sk, &["write:world:*"]);
    let read_token = mac("door3", &door_sk, &["read:*:*"]);
    let human_token = mac("human-escalation", &human_sk, &["admin:destroy:*"]);

    let server = BraidWireServer::new("127.0.0.1:8091", handler)
        .expect("bind 8091")
        .with_shell(door3_spatial_shell(read_token, spatial_token.clone()));
    thread::spawn(move || {
        let _ = server.run();
    });
    thread::sleep(Duration::from_millis(150));

    let post = |req: &WireRequest| {
        let body = serde_json::to_string(req).unwrap();
        http_post_raw("127.0.0.1:8091", "/v1/op", &body).unwrap_or_else(braid_wire::WireResponse::err)
    };

    // the page-facing rule: POST /world with {target, content}; the bridge
    // holds the write:world token, the browser never touches a key.
    for (i, place) in ["stone-garden", "tide-archive", "glass-bridge", "sky-well"].iter().enumerate() {
        let r = http_post_raw(
            "127.0.0.1:8091",
            "/world",
            &format!(
                r#"{{"target": "{place}", "content": "a grounded room (m9 spatial fact #{i})"}}"#
            ),
        )
        .expect("POST /world");
        assert!(r.ok, "place {place} failed: {:?}", r.error);
    }

    // the walk-in reads back the SAME ledger — every fact proven.
    let (world_status, world_raw) = http_get_raw("127.0.0.1:8091", "/world").expect("GET /world");
    assert_eq!(world_status, 200);
    let world: braid_wire::WireResponse =
        serde_json::from_str(world_raw.split("\r\n\r\n").nth(1).unwrap()).expect("world json");
    assert!(world.ok, "world error: {:?}", world.error);
    assert_eq!(world.data["walk_in_count"].as_u64().unwrap_or(0), 4, "all 4 placed facts walk in");

    let facts = world.data["world"]["facts"].as_array().unwrap();
    let proven = facts
        .iter()
        .filter(|f| f["provenance"]["signature_ok"].as_bool().unwrap_or(false))
        .count();
    let agents = world.data["presence"]["agents"].as_array().unwrap();
    let echoes = world.data["window"]["echoes"].as_array().unwrap();

    // destructive spatial op: same m4/m8 gate, two tokens, escalated=true.
    let first_cid = facts[0]["provenance"]["cid"].as_str().unwrap();
    let mut destroy = WireRequest::new("http", spatial_token.clone(), WireOp::Spatial {
        snapshot: String::new(),
        op: "admin:destroy".into(),
        target: "place/tide-archive".into(),
        payload: serde_json::json!({"reason": "decommissioned over the wire"}),
    });
    assert!(!post(&destroy).ok, "single-token destroy must be denied");
    destroy.escalation = Some(human_token.clone());
    let esc = post(&destroy);
    assert!(esc.ok, "two-token destroy failed: {:?}", esc.error);
    assert!(esc.data["escalated"].as_bool().unwrap_or(false), "double-triplet path confirmed");

    println!(
        "m9 GREEN — door3 spatial shell over the ONE wire\n  \
         page    : http://127.0.0.1:8091/  (keyless, place-fact control)\n  \
         world   : http://127.0.0.1:8091/world ({} proven, {} excluded)\n  \
         placed  : 4 spatial facts via POST /world — no key in the browser\n  \
         walk-in : {} objects at deterministic positions (latest cid {}…)\n  \
         window  : {} echoes threading the braid spine\n  \
         agents  : {} from ledger identities\n  \
         gate    : admin:destroy over a world target = two tokens, escalated {}",
        proven,
        world.data["excluded"].as_u64().unwrap_or(0),
        facts.len(),
        &first_cid[..10.min(first_cid.len())],
        echoes.len(),
        agents.len(),
        esc.data["escalated"].as_bool().unwrap_or(false),
    );

    loop {
        thread::sleep(Duration::from_secs(3600));
    }
}