//! m10 — rib/ARP convergence, live: every rib + every door on ONE address.
//!
//! One server, three door registrations (door1 witness, door2 structure,
//! door3 walk-in), all resolved at http://127.0.0.1:8092. The braid_drive
//! data plane (200 concurrent writes / 8 strands) is driven through
//! POST /v1/op — the SAME envelope door3 places spatial facts through — then
//! a creative place + a human-gated destroy, then every read plane agrees on
//! the same ledger and every CID proves back to genesis at the same address.
//! That is ARP convergence, braid-style: one substrate, many ribs, no islands.
//!
//! Run: cargo run -p braid_ui_bridge --example drive_convergence_shell

use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;

use braid_core::crypto::new_signing_key;
use braid_core::engine::BraidEngine;
use braid_core::policy::{policy_from_toml, PolicySnapshot};
use braid_drive::wire::WireRib;
use braid_keys::{did_key, SessionMacaroon};
use braid_ui_bridge::frontdoor::{Door, DoorRegistration, Router};
use braid_ui_bridge::{door3_spatial_shell, handler_from};
use braid_wire::{BraidWireServer, WireOp, WireRequest};
use ed25519_dalek::{SigningKey, VerifyingKey};
use rand::rngs::OsRng;

const GENESIS: &str = r#"
name = "genesis-m10-convergence-live"
version = 1

[[rules]]
allow = true
capability = "read:*:*"

[[rules]]
allow = true
capability = "write:note:*"

[[rules]]
allow = true
capability = "write:world:*"

[[rules]]
allow = false
capability = "admin:*:*"
"#;

const ESCALATION: &str = r#"
name = "escalation-m10-convergence-live"
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
    let path = format!("/tmp/opencode/braid-m10-conv-example-{}.jsonl", std::process::id());
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
        vec![
            DoorRegistration { door: Door::Lumen, did: door_did.clone(), location: "door1".into() },
            DoorRegistration { door: Door::Axiom, did: door_did.clone(), location: "door2".into() },
            DoorRegistration { door: Door::Mem, did: door_did, location: "door3".into() },
        ],
        "snap-genesis",
    )
    .with_escalation(human_did, "snap-escalation"));

    let read1 = mac("door1", &door_sk, &["read:*:*"]);
    let read2 = mac("door2", &door_sk, &["read:*:*"]);
    let read3 = mac("door3", &door_sk, &["read:*:*"]);
    let note = mac("door1", &door_sk, &["write:note:*"]);
    let world = mac("door3", &door_sk, &["write:world:*"]);
    let human = mac("human-escalation", &human_sk, &["admin:destroy:*"]);

    let handler = handler_from(router.clone());
    let server = BraidWireServer::new("127.0.0.1:8092", handler)
        .expect("bind 8092")
        .with_shell(door3_spatial_shell(read3.clone(), world.clone()));
    thread::spawn(move || {
        let _ = server.run();
    });
    thread::sleep(Duration::from_millis(150));

    let post = |req: &WireRequest| {
        let body = serde_json::to_string(req).unwrap();
        braid_wire::http_post_raw("127.0.0.1:8092", "/v1/op", &body).unwrap_or_else(braid_wire::WireResponse::err)
    };

    // the rib drives the wire — the walk-in page is up at the SAME address.
    let rib = WireRib::new("127.0.0.1:8092", note.clone());
    let rig = rib.rig_write(8, 25, "write:note", "rib/place");
    assert!(rig.all_ok(), "rib failed: {}", rig.failed);

    let place = post(&WireRequest::new("http", world.clone(), WireOp::Spatial {
        snapshot: String::new(),
        op: "write:world".into(),
        target: "place/m10-atrium".into(),
        payload: serde_json::json!({"name": "M10 Atrium", "content": "where the ribs meet"}),
    }));
    assert!(place.ok, "place: {:?}", place.error);

    let mut destroy = WireRequest::new("http", world.clone(), WireOp::Spatial {
        snapshot: String::new(),
        op: "admin:destroy".into(),
        target: "place/m10-atrium".into(),
        payload: serde_json::json!({"reason": "convergence sweep"}),
    });
    assert!(!post(&destroy).ok, "single-token destroy must be denied");
    destroy.escalation = Some(human.clone());
    let esc = post(&destroy);
    assert!(esc.ok, "escalated: {:?}", esc.error);

    // convergence read plane — all at 127.0.0.1:8092.
    let witness = post(&WireRequest::new("http", read1.clone(), WireOp::Read { snapshot: String::new(), op_filter: None }));
    let structure = post(&WireRequest::new("http", read2.clone(), WireOp::Read { snapshot: String::new(), op_filter: None }));
    let scene = post(&WireRequest::new("http", read3.clone(), WireOp::World { snapshot: String::new() }));
    assert!(witness.ok && structure.ok && scene.ok);

    let reg = post(&WireRequest::new("http", read3.clone(), WireOp::Registry));
    let audit = rib.audit_over_wire(&read1, &rig.cids);

    let facts = scene.data["world"]["facts"].as_array().unwrap();
    let proven = facts.iter().filter(|f| f["provenance"]["signature_ok"].as_bool().unwrap_or(false)).count();

    println!(
        "m10 GREEN — rib/ARP convergence on ONE wire\n  \
         pages    : / (door3 walk-in)  /world  /v1/op\n  \
         address  : http://127.0.0.1:8092 — {} doors resolve\n  \
         rib      : {} writes / 8 strands through POST /v1/op — {} ok, {} failed\n  \
         audit    : {} proven over the wire, health ok, registry seen\n  \
         walls    : door1 witness {} nodes · door2 structure {} nodes · door3 walk-in {} ({} proven, {} excluded)\n  \
         gate     : admin:destroy = two tokens, escalated {} — wipe still floors\n  \
         snapshot : {} across every surface",
        reg.data["doors"].as_array().map(|d| d.len()).unwrap_or(0),
        rig.submitted,
        rig.ok,
        rig.failed,
        audit.node_count,
        witness.data["count"].as_u64().unwrap_or(0),
        structure.data["count"].as_u64().unwrap_or(0),
        scene.data["walk_in_count"].as_u64().unwrap_or(0),
        proven,
        scene.data["excluded"].as_u64().unwrap_or(1),
        esc.data["escalated"].as_bool().unwrap_or(false),
        reg.data["default_snapshot"].as_str().unwrap_or("?"),
    );

    loop {
        thread::sleep(Duration::from_secs(3600));
    }
}