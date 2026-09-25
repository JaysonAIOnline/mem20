//! m7 — door1 acceptance: the nav SHELL served by the ONE bridge.
//!
//! Real engine + real router (THREE registered doors: Lumen door1, Axiom
//! door2, Mem door3) + real wire server + the embedded door1 SPA. All over
//! one listener:
//!   GET /          → the nav page (keyless)
//!   GET /witness   → door1 Lumen witness view (Read via bridge token)
//!   GET /structure → door2 Axiom structure view (Read via bridge token)
//!   GET /state     → bridge health
//!   POST /forge    → keyless write:note via bridge write token
//!   GET /manifest  → surface directory (live + planned, D1.4/D1.5)
//! The same wire still serves the braid envelope and the door3 shell routes.

use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;

use braid_core::crypto::new_signing_key;
use braid_core::engine::BraidEngine;
use braid_core::policy::{policy_from_toml, PolicySnapshot};
use braid_keys::{did_key, SessionMacaroon};
use braid_ui_bridge::frontdoor::{Door, DoorRegistration, Router};
use braid_ui_bridge::{door1_shell, handler_from, Door1Surface};
use braid_wire::{http_get_raw, http_post_raw, BraidWireServer, WireOp, WireRequest};
use ed25519_dalek::{SigningKey, VerifyingKey};
use rand::rngs::OsRng;

const GENESIS: &str = r#"
name = "genesis-grand"
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

fn mac(loc: &str, sk: &SigningKey, caps: &[&str]) -> SessionMacaroon {
    SessionMacaroon::issue(loc, &did_key(&VerifyingKey::from(sk)), caps, sk)
}

struct Harness {
    addr: String,
    write_token: SessionMacaroon,
    door1_read: SessionMacaroon,
    door2_read: SessionMacaroon,
    door1_write: SessionMacaroon,
}

fn boot(door3_shell_armed: bool) -> Harness {
    use std::sync::atomic::{AtomicU64, Ordering};
    static SEQ: AtomicU64 = AtomicU64::new(0);
    let seq = SEQ.fetch_add(1, Ordering::Relaxed);
    let path = format!("/tmp/opencode/braid-m7-door1-{}-{seq}.jsonl", std::process::id());
    let _ = std::fs::remove_file(&path);
    let sk = new_signing_key();
    let engine_id = braid_core::crypto::pub_key_hex(&VerifyingKey::from(&sk));
    let mut engine = BraidEngine::new(&path, sk).expect("engine boots");
    engine.register_snapshot(PolicySnapshot {
        cid: "snap-genesis".into(),
        signer: engine_id,
        signature: String::new(),
        policy: policy_from_toml(GENESIS).expect("genesis"),
    });

    // ONE key, ONE router, THREE registered doors — the nav reads door1 + door2
    // views and forges through door1; door3 remains the walk-in.
    let door_sk = SigningKey::generate(&mut OsRng);
    let door_did = did_key(&VerifyingKey::from(&door_sk));

    let router = Arc::new(Router::new(
        Arc::new(Mutex::new(engine)),
        vec![
            DoorRegistration { door: Door::Lumen, did: door_did.clone(), location: "door1".into() },
            DoorRegistration { door: Door::Axiom, did: door_did.clone(), location: "door2".into() },
            DoorRegistration { door: Door::Mem, did: door_did.clone(), location: "door3".into() },
        ],
        "snap-genesis",
    ));

    let handler = handler_from(router.clone());
    let witness_token = mac("door1", &door_sk, &["read:*:*"]);
    let structure_token = mac("door2", &door_sk, &["read:*:*"]);
    let forge_token = mac("door1", &door_sk, &["write:note:*"]);
    let world_token = mac("door3", &door_sk, &["read:*:*"]);
    let write_token = mac("door3", &door_sk, &["write:note:*"]);
    let door1_read = witness_token.clone();
    let door2_read = structure_token.clone();
    let door1_write = forge_token.clone();

    let shell = door1_shell(
        witness_token,
        structure_token,
        forge_token,
        vec![
            Door1Surface { name: "dashboard", url: "/health" },
            Door1Surface { name: "arena", url: "" },
            Door1Surface { name: "tool-policy-console", url: "" },
        ],
    );
    let shell = if door3_shell_armed { shell.page("/walk-in", include_str!("../assets/walk_in.html")).world_token(world_token) } else { shell };

    let server = BraidWireServer::new("127.0.0.1:0", handler)
        .expect("bind")
        .with_shell(shell);
    let addr = server.local_addr();
    thread::spawn(move || {
        let _ = server.run();
    });
    thread::sleep(Duration::from_millis(150));

    Harness { addr, write_token, door1_read, door2_read, door1_write }
}

impl Harness {
    fn post(&self, req: &WireRequest) -> braid_wire::WireResponse {
        let body = serde_json::to_string(req).unwrap();
        http_post_raw(&self.addr, "/v1/op", &body).unwrap_or_else(braid_wire::WireResponse::err)
    }

    fn get(&self, path: &str) -> (u16, braid_wire::WireResponse) {
        let (status, raw) = http_get_raw(&self.addr, path).unwrap();
        let body = raw.split("\r\n\r\n").nth(1).unwrap_or("");
        let resp = if body.trim().is_empty() {
            braid_wire::WireResponse::err("empty body")
        } else {
            serde_json::from_str(body).unwrap_or_else(|_| braid_wire::WireResponse::err("not json"))
        };
        (status, resp)
    }

    fn seed(&self) {
        for (i, name) in ["first-note", "second-note"].iter().enumerate() {
            let write = WireRequest::new("http", self.write_token.clone(), WireOp::Write {
                snapshot: String::new(),
                op: "write:note".into(),
                target: format!("note/{name}"),
                payload: serde_json::json!({"content": format!("seed {i}: {name}")}),
            });
            assert!(self.post(&write).ok, "seed write must succeed");
        }
    }
}



#[test]
fn door1_nav_serves_views_forge_and_manifest_over_one_wire() {
    let h = boot(false);
    h.seed();

    // GET / → the keyless nav SPA
    let (status, raw) = http_get_raw(&h.addr, "/").expect("get /");
    assert_eq!(status, 200);
    assert!(raw.to_lowercase().contains("text/html"));
    assert!(raw.contains("door1 · nav") || raw.contains("door1"));
    assert!(!raw.contains("macaroon"), "the page holds no session secret");

    // GET /witness → door1 Lumen witness view (bridge-held token)
    let (status, resp) = h.get("/witness");
    assert_eq!(status, 200);
    assert!(resp.ok, "witness error: {:?}", resp.error);
    assert_eq!(resp.data["door"], "door1");
    assert_eq!(resp.data["view"]["kind"], "witness");
    let timeline = resp.data["view"]["timeline"].as_array().unwrap();
    assert!(timeline.len() >= 2, "seeded notes are in the witness");

    // GET /structure → door2 Axiom structure view
    let (status, resp) = h.get("/structure");
    assert_eq!(status, 200);
    assert!(resp.ok, "structure error: {:?}", resp.error);
    assert_eq!(resp.data["door"], "door2");
    assert_eq!(resp.data["view"]["kind"], "structure");
    assert!(resp.data["view"]["verified"].as_bool().unwrap_or(false), "whole log verifies");
    let hops = resp.data["view"]["spine_to_genesis"].as_array().unwrap().len();
    assert!(hops >= 2, "spine reaches genesis from head; hops={hops}");

    // GET /state → bridge health (keyless)
    let (status, resp) = h.get("/state");
    assert_eq!(status, 200);
    assert!(resp.ok);
    assert_eq!(resp.data["status"], "ok");

    // GET /manifest → surface directory: live url + planned url + nav
    let (status, resp) = h.get("/manifest");
    assert_eq!(status, 200);
    assert!(resp.ok);
    let surfaces = resp.data["surfaces"].as_array().unwrap();
    let dashboard = &surfaces[0];
    assert_eq!(dashboard["name"], "dashboard");
    assert_eq!(dashboard["planned"], false, "dashboard is live at /health");
    let arena = &surfaces[1];
    assert_eq!(arena["planned"], true, "arena planned (no mount yet)");

    // POST /forge → keyless write:note lands in the witness over the SAME wire
    let before = h.get("/witness").1;
    let before_n = before.data["view"]["timeline"].as_array().unwrap().len();
    let forge = serde_json::json!({ "target": "note/forged-from-nav", "content": "hello from the door1 shell" });
    let r = http_post_raw(&h.addr, "/forge", &forge.to_string()).expect("post /forge");
    assert!(r.ok, "forge error: {:?}", r.error);
    assert_eq!(r.data["door"], "door1", "forge writes through the door1 door");
    assert!(r.data["cid"].is_string());

    let after = h.get("/witness").1;
    let after_n = after.data["view"]["timeline"].as_array().unwrap().len();
    assert_eq!(after_n, before_n + 1, "forged node entered the witness");

    // POST /forge with a bad body is refused by the shell (no secret path)
    let r = http_post_raw(&h.addr, "/forge", "{}").expect("post /forge bad");
    assert!(!r.ok);
    assert!(r.error.as_deref().unwrap_or("").contains("target"));
}

#[test]
fn door1_and_door3_can_coexist_on_one_base_without_crossing_auth() {
    let h = boot(true);
    h.seed();

    // both shells on ONE listener
    let (status, raw) = http_get_raw(&h.addr, "/").expect("get /");
    assert_eq!(status, 200);
    assert!(raw.contains("witness") || raw.contains("door1"), "door1 page");

    let (status, raw) = http_get_raw(&h.addr, "/walk-in").expect("get /walk-in");
    assert_eq!(status, 200);
    assert!(raw.to_lowercase().contains("text/html"));
    assert!(raw.contains("walk-in") || raw.contains("door3"), "door3 page");

    // auth boundaries hold over the envelope: the door1 WRITE token (forge) is
    // not a READ token (one-directional grants).
    let read_attempt = WireRequest::new(
        "http",
        h.door1_write.clone(),
        WireOp::Read { snapshot: String::new(), op_filter: None },
    );
    let r = h.post(&read_attempt);
    assert!(!r.ok, "write token must not read");
    assert!(r.error.as_deref().unwrap_or("").contains("does not grant read"));

    // the door2 READ token cannot write.
    let write_attempt = WireRequest::new(
        "http",
        h.door2_read.clone(),
        WireOp::Write {
            snapshot: String::new(),
            op: "write:note".into(),
            target: "note/illegal".into(),
            payload: serde_json::json!({"content": "should not land"}),
        },
    );
    let r = h.post(&write_attempt);
    assert!(!r.ok, "door2 read token cannot write");
    assert!(
        r.error.as_deref().unwrap_or("").contains("denied"),
        "expected denied, got {:?}",
        r.error
    );

    // same engine, distinct doors: door1 read sees a witness, door2 read sees
    // structure — same wire, views differ by door, not by rewrite.
    let w = h.post(&WireRequest::new("http", h.door1_read.clone(), WireOp::Read {
        snapshot: String::new(),
        op_filter: None,
    }));
    assert!(w.ok);
    assert_eq!(w.data["view"]["kind"], "witness");

    let s = h.post(&WireRequest::new("http", h.door2_read.clone(), WireOp::Read {
        snapshot: String::new(),
        op_filter: None,
    }));
    assert!(s.ok);
    assert_eq!(s.data["view"]["kind"], "structure");

    // the door1 shell only owns witness/structure/state/forge/manifest (+ the
    // walk-in when the bridge deliberately mounts it) — a stray route is 403.
    let (status, _) = h.get("/no-such-route");
    assert_eq!(status, 403, "unknown routes are refused, never served");

    // identities stay per-door: the door1 read token OPENs the shared world
    // (the ledger is shared), but its door identity stays door1.
    let w_attempt = h.post(&WireRequest::new("http", h.door1_read.clone(), WireOp::World {
        snapshot: String::new(),
    }));
    assert!(w_attempt.ok, "read token may open the shared world");
    assert_eq!(w_attempt.data["door"], "door1", "identities never cross");
    assert_eq!(w_attempt.data["kind"], "world");
    assert!(
        w_attempt.data["world"]["walk_in_count"].as_u64().unwrap_or(0) >= 1,
        "seeded notes appear as walk-ins in the shared world"
    );
}