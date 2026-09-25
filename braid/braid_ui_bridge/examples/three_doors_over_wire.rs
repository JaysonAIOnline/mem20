//! m2 acceptance (E2 + U1/U2/U3): the three doors go LIVE over ONE wire.
//!
//! ONE engine, ONE router, ONE socket. door1/lumen (the real witness view),
//! door2/axiom (the structure view), door3/her (the conversation window).
//! Every request carries a braid session macaroon bound to that door's DID —
//! no second auth island — and each door receives its own shaped view.

use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;

use braid_core::crypto::new_signing_key;
use braid_core::engine::BraidEngine;
use braid_core::policy::{policy_from_toml, Capability, PolicySnapshot};
use braid_ui_bridge::frontdoor::{Door, DoorRegistration};
use braid_ui_bridge::Router;
use braid_wire::{http_post_raw, BraidWireServer, WireOp, WireRequest, WireResponse};

const SEED: &str = r#"
name = "genesis"
version = 1
default_deny = true
[[rules]]
allow = true
capability = "read:*:*"
[[rules]]
allow = true
capability = "write:note:*"
[[rules]]
allow = true
capability = "read:world:*"
[[rules]]
allow = true
capability = "invoke:tool:*"
"#;

fn main() {
    let path = "/tmp/opencode/braid-m2-wire.jsonl";
    let _ = std::fs::remove_file(path);

    // ONE substrate: engine + frozen policy snapshot
    let signing = new_signing_key();
    let mut engine = BraidEngine::new(path, signing).expect("boot engine");
    let policy = policy_from_toml(SEED).expect("parse seed");
    let snapshot_id = "snap-genesis-m2";
    let signer = engine.id_hex();
    engine.register_snapshot(PolicySnapshot {
        cid: snapshot_id.into(),
        signer,
        signature: String::new(),
        policy,
    });
    let engine = Arc::new(Mutex::new(engine));

    // THREE doors, each a distinct identity (DID) bound to a macaroon location.
    let door1 = door_key("door1/lumen");
    let door2 = door_key("door2/axiom");
    let door3 = door_key("door3/her");

    let doors: Vec<DoorRegistration> = vec![
        DoorRegistration {
            door: Door::Lumen,
            did: door1.did.clone(),
            location: "door1".into(),
        },
        DoorRegistration {
            door: Door::Axiom,
            did: door2.did.clone(),
            location: "door2".into(),
        },
        DoorRegistration {
            door: Door::Mem,
            did: door3.did.clone(),
            location: "door3".into(),
        },
    ];

    let router = Arc::new(Router::new(engine.clone(), doors, snapshot_id));
    let handler = braid_ui_bridge::handler_from(router);

    // ONE wire
    let server = BraidWireServer::new("127.0.0.1:0", handler).expect("bind");
    let addr = server.local_addr();
    thread::spawn(move || {
        let _ = server.run();
    });
    thread::sleep(Duration::from_millis(150));

    // ---- the three doors, live over the wire ----
    // door1 the real one writes a witness note
    let w1 = door1.post_write(&addr, "note", "note",
        serde_json::json!({"witness": "the real one: lumen sees it"}));
    assert_ok(&w1, "door1 write");
    println!("door1  WRITE  ok  cid={} precommit={}",
        w1.data["cid"].as_str().unwrap(),
        w1.data["precommit_verified"].as_bool().unwrap_or(false));

    // door2 (structure) writes, then asks for the axiom view
    let w2 = door2.post_write(&addr, "note", "note",
        serde_json::json!({"actor": "door2 axiom: structure observed"}));
    assert_ok(&w2, "door2 write");
    let r2 = door2.post_read(&addr, Some("write:note"));
    assert_ok(&r2, "door2 read");
    let axiom = r2.data["view"].clone();
    println!("door2  READ   ok  door={} nodes={} verified={} spine={}",
        axiom["door"].as_str().unwrap_or("?"),
        axiom["node_count"].as_u64().unwrap_or(0),
        axiom["verified"].as_bool().unwrap_or(false),
        axiom["spine_to_genesis"].as_array().map(|a| a.len()).unwrap_or(0));

    // door3/her — the conversation window: human + her interleave
    let w3a = door3.post_write(&addr, "note", "her-note",
        serde_json::json!({"human": "hello her, what do you see?"}));
    assert_ok(&w3a, "her window human write");
    let w3b = door3.post_write(&addr, "note", "her-note",
        serde_json::json!({"her": "i see the braid — one substrate, three doors"}));
    assert_ok(&w3b, "her window her write");
    let r3 = door3.post_read(&addr, Some("write:note"));
    assert_ok(&r3, "her window read");
    let convo = r3.data["view"].clone();
    println!("door3  READ   ok  door={} last_cid={} turns={}",
        convo["door"].as_str().unwrap_or("?"),
        convo["last_cid"].as_str().unwrap_or("none").chars().take(18).collect::<String>(),
        convo["conversation"].as_array().map(|a| a.len()).unwrap_or(0));

    // one braid, three doors — does the substrate hold?
    let r1 = door1.post_read(&addr, None);
    assert_ok(&r1, "door1 witness read");
    let lumen = r1.data["view"].clone();
    let total = lumen["timeline"].as_array().map(|a| a.len()).unwrap_or(0);
    println!("\nGREEN — 3 doors, 1 wire, 1 braid, {total} committed nodes");
    println!("      door1/lumen  witness timeline        : {total} nodes");
    println!("      door2/axiom  structure integrity     : verified={}",
        axiom["verified"].as_bool().unwrap_or(false));
    println!("      door3/her    conversation window     : live");

    // auth denied path: a forged/tampered macaroon must be refused (no second island)
    let forged = door1.forge_bad_capability();
    let resp = forged.post_read(&addr, None);
    assert!(!resp.ok, "forged macaroon must be refused at the door");
    println!("      security   forged macaroon refused    : {}", resp.error.as_deref().unwrap_or("denied"));
}

fn door_key(location: &str) -> DoorKey {
    let sk = new_signing_key();
    let vk = ed25519_dalek::VerifyingKey::from(&sk);
    let did = braid_keys::did_key(&vk);
    DoorKey { location: location.to_string(), did, sk }
}

struct DoorKey {
    location: String,
    did: String,
    sk: ed25519_dalek::SigningKey,
}

impl DoorKey {
    fn mac(&self, caps: &[&str]) -> braid_keys::SessionMacaroon {
        let loc = self.location.split('/').next().unwrap();
        braid_keys::SessionMacaroon::issue(loc, &format!("sess-{}", self.location), caps, &self.sk)
    }

    fn post_write(&self, addr: &str, action: &str, target: &str, payload: serde_json::Value) -> WireResponse {
        // one action name -> one capability ("write:note") and one engine op
        let cap = format!("write:{action}");
        let req = WireRequest::new("http", self.mac(&[&cap]), WireOp::Write {
            snapshot: "snap-genesis-m2".into(),
            op: cap.clone(),
            target: target.into(),
            payload,
        });
        let body = serde_json::to_string(&req).unwrap();
        http_post_raw(addr, "/v1/op", &body).unwrap_or_else(WireResponse::err)
    }

    fn post_read(&self, addr: &str, op_filter: Option<&str>) -> WireResponse {
        // A read is a read: the capability governs what you may READ, not what
        // filter text you paste. op_filter merely selects committed nodes whose
        // op equals the filter string (engine-side filtering after the gate).
        let cap = "read:*:*";
        let req = WireRequest::new("http", self.mac(&[cap]), WireOp::Read {
            snapshot: "snap-genesis-m2".into(),
            op_filter: op_filter.map(|s| s.to_string()),
        });
        let body = serde_json::to_string(&req).unwrap();
        http_post_raw(addr, "/v1/op", &body).unwrap_or_else(WireResponse::err)
    }

    fn forge_bad_capability(&self) -> DoorKey {
        let sk = new_signing_key();
        let vk = ed25519_dalek::VerifyingKey::from(&sk);
        let did = braid_keys::did_key(&vk);
        DoorKey { location: self.location.clone(), did, sk }
    }
}

fn assert_ok(r: &WireResponse, what: &str) {
    assert!(r.ok, "{what} FAILED: {}", r.error.as_deref().unwrap_or("no error"));
    let _ = Capability::parse("_");
}