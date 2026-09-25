//! m6 — door-3 acceptance: the walk-in SHELL served by the ONE bridge.
//!
//! Real engine + real router + real wire server + the embedded keyless page.
//! The browser-facing surface is proven over actual HTTP:
//!   GET /       → the static walk-in page (no token in the browser)
//!   GET /world  → the spatial scene (bridge-held read token, server-side)
//!   POST /v1/op → the same envelope every door already uses
//! Agent presence and world objects both ride ONE wire (D3.6), and a tampered
//! fact is EXCLUDED from the walk-in over that same wire (the fact gate).

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

struct Harness {
    router: Arc<Router>,
    addr: String,
    write_token: SessionMacaroon,
    human_token: SessionMacaroon,
}

fn boot() -> Harness {
    use std::sync::atomic::{AtomicU64, Ordering};
    static SEQ: AtomicU64 = AtomicU64::new(0);
    let seq = SEQ.fetch_add(1, Ordering::Relaxed);
    let path = format!("/tmp/opencode/braid-m6-shell-{}-{seq}.jsonl", std::process::id());
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

    let server = BraidWireServer::new("127.0.0.1:0", handler)
        .expect("bind")
        .with_shell(door3_shell(read_token));
    let addr = server.local_addr();
    thread::spawn(move || {
        let _ = server.run();
    });
    thread::sleep(Duration::from_millis(150));

    Harness { router, addr, write_token, human_token }
}

impl Harness {
    fn post(&self, req: &WireRequest) -> braid_wire::WireResponse {
        let body = serde_json::to_string(req).unwrap();
        http_post_raw(&self.addr, "/v1/op", &body).unwrap_or_else(braid_wire::WireResponse::err)
    }

    fn seed_rooms(&self) {
        for (room, name) in ["stone-garden", "tide-archive", "glass-bridge", "sky-well"].iter().enumerate() {
            let write = WireRequest::new("http", self.write_token.clone(), WireOp::Write {
                snapshot: String::new(),
                op: "write:note".into(),
                target: format!("place/{name}"),
                payload: serde_json::json!({"name": name, "room": room, "content": format!("a grounded room named {name}")}),
            });
            assert!(self.post(&write).ok, "seed write must succeed");
        }
    }
}

#[test]
fn door3_shell_serves_the_walk_in_over_one_wire() {
    let h = boot();
    h.seed_rooms();

    // decommission under the human-gated escalation path (two tokens)
    let mut decommission = WireRequest::new("http", h.write_token.clone(), WireOp::Write {
        snapshot: String::new(),
        op: "admin:destroy".into(),
        target: "place/tide-archive".into(),
        payload: serde_json::json!({"reason": "decommissioned by gate"}),
    });
    assert!(!h.post(&decommission).ok, "single-token destroy denied");
    decommission.escalation = Some(h.human_token.clone());
    assert!(h.post(&decommission).ok, "two-token destroy succeeds");

    // GET / — the static, keyless walk-in page
    let (status, raw) = http_get_raw(&h.addr, "/").expect("get /");
    assert_eq!(status, 200);
    assert!(raw.to_lowercase().contains("text/html"), "html content-type");
    assert!(raw.contains("door3 — spatial walk-in") || raw.contains("door3"), "page title");
    assert!(raw.contains("/world"), "page must poll the world endpoint");
    assert!(!raw.contains("macaroon"), "the page holds no session secret");

    // GET /world — the spatial scene, token held server-side
    let (status, raw) = http_get_raw(&h.addr, "/world").expect("get /world");
    assert_eq!(status, 200);
    let world: braid_wire::WireResponse =
        serde_json::from_str(raw.split("\r\n\r\n").nth(1).unwrap()).expect("world json");
    assert!(world.ok, "world error: {:?}", world.error);

    let facts = world.data["world"]["facts"].as_array().unwrap();
    assert_eq!(facts.len(), 5, "4 seed rooms + 1 decommission = 5 walked-in facts");
    for f in facts {
        assert!(f["provenance"]["signature_ok"].as_bool().unwrap(), "every fact proven");
        assert_eq!(f["position"].as_array().unwrap().len(), 3, "spatial positions are 3-vectors");
        assert!(!world.data["presence"]["agents"].as_array().unwrap().is_empty(), "agent present");
    }
    assert_eq!(world.data["excluded"], 0, "nothing tampered => nothing excluded");
    let echoes = world.data["window"]["echoes"].as_array().unwrap();
    assert_eq!(echoes.len(), 5, "window threads the whole braid spine");
    assert!(world.data["window"]["last_cid"].is_string());

    // the tamper gate reaches the shell: corrupt one committed payload in the
    // engine, re-ask the world over HTTP, and the node no longer walks in
    let first_cid = facts[0]["provenance"]["cid"].as_str().unwrap().to_string();
    {
        let mut guard = h.router.engine().lock().expect("engine");
        let mut node = guard.log.nodes.get(&first_cid).unwrap().clone();
        node.body.payload = serde_json::json!({"name": "tampered-room", "content": "evil"});
        assert!(node.audit.as_ref().unwrap().verified(&node.signer), "strand sig survives (documented)");
        assert!(!braid_core::engine::node_is_proven(&node), "precommitment no longer binds");
        guard.log.nodes.insert(first_cid, node);
    }
    let (_, raw) = http_get_raw(&h.addr, "/world").expect("get /world after tamper");
    let after: braid_wire::WireResponse =
        serde_json::from_str(raw.split("\r\n\r\n").nth(1).unwrap()).expect("world json");
    assert_eq!(after.data["excluded"], 1, "tampered node excluded over the wire");
    assert_eq!(after.data["proven"], 4, "four real facts still walk in");
}

#[test]
fn door3_op_envelope_still_walks_without_the_shell() {
    // sanity: the door consumes the braid envelope directly too
    let h = boot();
    h.seed_rooms();
    let world = h.post(&WireRequest::new("http", h.write_token.clone(), WireOp::World {
        snapshot: String::new(),
    }));
    // write token is NOT a read token (one-directional grants)
    assert!(!world.ok, "writer-only token cannot read the world");
    assert!(world.error.as_deref().unwrap_or("").contains("does not grant read"));
}