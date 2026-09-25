//! m9 — door-3 SPATIAL WRITE over the SAME wire (door3 quest3d, D3.6).
//!
//! A spatial fact is committed into the ONE ledger through WireOp::Spatial —
//! the same braided-triplet path, the same macaroon gate, the same /v1/op
//! envelope as every write. The committed node is an ordinary braid node, so
//! the walk-in derives it as a PROVEN fact (deterministic position, proven
//! provenance) and the resonance window threads it onto the spine. This file
//! proves, over real HTTP:
//!   - a creative spatial write (write:world) commits escalated=false and
//!     echoes the fresh WorldScene + window + presence
//!   - spatial ops obey the ONE-DIRECTIONAL capability gate (writer cannot
//!     read, reader cannot write; admin stays human-gated)
//!   - destructive spatial ops (admin:destroy on a world object) ride the
//!     escalation path exactly like godmode (two tokens, escalated=true)
//!   - a tampered spatial fact is EXCLUDED from the walk-in over the wire
//!   - the keyless door3_spatial_shell places facts via POST /world and the
//!     walk-in updates from the SAME ledger

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
capability = "write:note:*"

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
    spatial_token: SessionMacaroon,
    read_token: SessionMacaroon,
    note_token: SessionMacaroon,
    human_token: SessionMacaroon,
}

fn boot() -> Harness {
    use std::sync::atomic::{AtomicU64, Ordering};
    static SEQ: AtomicU64 = AtomicU64::new(0);
    let seq = SEQ.fetch_add(1, Ordering::Relaxed);
    let path = format!("/tmp/opencode/braid-m9-spatial-{}-{seq}.jsonl", std::process::id());
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
    let note_token = mac("door3", &door_sk, &["write:note:*"]);
    let human_token = mac("human-escalation", &human_sk, &["admin:destroy:*"]);

    let server = BraidWireServer::new("127.0.0.1:0", handler)
        .expect("bind")
        .with_shell(door3_spatial_shell(read_token.clone(), spatial_token.clone()));
    let addr = server.local_addr();
    thread::spawn(move || {
        let _ = server.run();
    });
    thread::sleep(Duration::from_millis(150));

    Harness { router, addr, spatial_token, read_token, note_token, human_token }
}

impl Harness {
    fn post(&self, req: &WireRequest) -> braid_wire::WireResponse {
        let body = serde_json::to_string(req).unwrap();
        http_post_raw(&self.addr, "/v1/op", &body).unwrap_or_else(braid_wire::WireResponse::err)
    }

    fn spatial(&self, target: &str, payload: serde_json::Value) -> braid_wire::WireResponse {
        self.post(&WireRequest::new("http", self.spatial_token.clone(), WireOp::Spatial {
            snapshot: String::new(),
            op: "write:world".into(),
            target: target.into(),
            payload,
        }))
    }
}

#[test]
fn spatial_fact_commits_into_one_ledger_and_echoes_the_world() {
    let h = boot();

    let resp = h.spatial(
        "stone-garden",
        serde_json::json!({"name": "The Stone Garden", "room": 1, "content": "a grounded place"}),
    );
    assert!(resp.ok, "spatial write timed out/denied: {:?}", resp.error);
    assert_eq!(resp.data["door"], "door3", "spatial ops are door3-shaped");

    let cid = resp.data["cid"].as_str().expect("cid echoed").to_string();
    assert!(!resp.data["escalated"].as_bool().unwrap(), "creative spatial write is NOT escalated");

    // the response view is the freshly composed world (D3.6: object appears now)
    let view = &resp.data["view"];
    assert_eq!(view["kind"], "spatial");
    assert_eq!(view["walk_in_count"], 1, "the new object walks in immediately");
    assert_eq!(view["proven"], 1);
    assert_eq!(view["excluded"], 0, "nothing tampered => nothing excluded");
    let fact = &view["world"]["facts"][0];
    assert_eq!(fact["target"], "stone-garden", "target carried onto the node");
    assert_eq!(fact["provenance"]["cid"], cid.as_str(), "the walk-in node IS the committed braid node");
    assert!(fact["provenance"]["signature_ok"].as_bool().unwrap(), "proven over the wire");
    assert_eq!(fact["position"].as_array().unwrap().len(), 3, "deterministic 3-vector");

    // resonance: the spatial fact threads the braid spine (window = the ledger)
    let echoes = view["window"]["echoes"].as_array().unwrap();
    assert_eq!(echoes.len(), 1, "window = spine, and the spine just grew");
    assert_eq!(echoes[0]["cid"], cid.as_str(), "the newest echo IS the spatial node");

    // presence comes from ledger identities, not config
    assert!(!view["presence"]["agents"].as_array().unwrap().is_empty(), "agent present");

    // GET /world over the same wire sees the SAME ledger fact
    let (_, raw) = http_get_raw(&h.addr, "/world").expect("get /world");
    let world: braid_wire::WireResponse =
        serde_json::from_str(raw.split("\r\n\r\n").nth(1).unwrap()).expect("world json");
    assert!(world.ok, "world error: {:?}", world.error);
    assert_eq!(world.data["walk_in_count"], 1);
    assert!(world.data["world"]["facts"].as_array().unwrap()[0]["provenance"]["signature_ok"]
        .as_bool()
        .unwrap());

    // the node is also a real, proveable braid node on the same envelope
    let prove = h.post(&WireRequest::new(
        "http",
        h.read_token.clone(),
        WireOp::Prove { cid: cid.clone() },
    ));
    assert!(prove.ok, "prove: {:?}", prove.error);
    assert!(prove.data["verified"].as_bool().unwrap(), "whole spine verifies to genesis");
}

#[test]
fn spatial_ops_obey_one_directional_caps_and_human_gated_destruction() {
    let h = boot();
    let _ = h.spatial("tide-archive", serde_json::json!({"name": "Tide Archive"}));
    assert_eq!(
        h.spatial("glass-bridge", serde_json::json!({"name": "Glass Bridge"})).data["view"]["walk_in_count"],
        2
    );

    // reader CANNOT write: a read-only token is denied (escalation has no token -> human-gated)
    let reader_write = h.post(&WireRequest::new("http", h.read_token.clone(), WireOp::Spatial {
        snapshot: String::new(),
        op: "write:world".into(),
        target: "sky-well".into(),
        payload: serde_json::json!({"name": "Sky Well"}),
    }));
    assert!(!reader_write.ok, "reader cannot create a spatial fact");
    assert!(
        reader_write.error.as_deref().unwrap_or("").contains("second human-gated token"),
        "gate blocks before the floor"
    );

    // writer CANNOT read the world (one-directional grants, caveats[0])
    let writer_read = h.post(&WireRequest::new("http", h.spatial_token.clone(), WireOp::World {
        snapshot: String::new(),
    }));
    assert!(!writer_read.ok, "spatial WRITE token cannot READ the world");
    assert!(writer_read.error.as_deref().unwrap_or("").contains("does not grant read"));

    // a note token cannot sneak into the spatial surface either
    let note_spatial = h.post(&WireRequest::new("http", h.note_token.clone(), WireOp::Spatial {
        snapshot: String::new(),
        op: "write:world".into(),
        target: "sky-well".into(),
        payload: serde_json::json!({"name": "Sky Well"}),
    }));
    assert!(!note_spatial.ok, "note-only token has no spatial grant");
    assert!(note_spatial.error.as_deref().unwrap_or("").contains("second human-gated token"));

    // DESTRUCTIVE spatial op: admin:destroy on a world object takes the
    // escalation path — one token denied, two tokens commit escalated=true.
    let mut destroy = WireRequest::new("http", h.spatial_token.clone(), WireOp::Spatial {
        snapshot: String::new(),
        op: "admin:destroy".into(),
        target: "place/tide-archive".into(),
        payload: serde_json::json!({"reason": "decommissioned over the wire"}),
    });
    assert!(!h.post(&destroy).ok, "single-token spatial destroy denied");
    destroy.escalation = Some(h.human_token.clone());
    let dest = h.post(&destroy);
    assert!(dest.ok, "two-token spatial destroy commits: {:?}", dest.error);
    assert!(dest.data["escalated"].as_bool().unwrap(), "the double-triplet path is marked escalated");
    assert!(dest.data["view"]["excluded"] == serde_json::json!(0), "nothing tampered");

    // the nuclear floor still holds: admin:wipe is unreachable even two-token
    let mut wipe = WireRequest::new("http", h.spatial_token.clone(), WireOp::Spatial {
        snapshot: String::new(),
        op: "admin:wipe".into(),
        target: "place/*".into(),
        payload: serde_json::json!({"nuke": true}),
    });
    wipe.escalation = Some(h.human_token.clone());
    assert!(!h.post(&wipe).ok, "admin:wipe stays denied");
}

#[test]
fn door3_spatial_shell_places_facts_and_the_walk_in_tracks_the_same_ledger() {
    let h = boot();

    // GET / — the static, keyless page (m9: now with the place-fact control)
    let (status, raw) = http_get_raw(&h.addr, "/").expect("get /");
    assert_eq!(status, 200);
    assert!(raw.contains("/world"), "page polls the world endpoint");
    assert!(raw.contains("place fact"), "page exposes the spatial write surface");
    assert!(!raw.contains("macaroon"), "the page holds no session secret");

    // empty world to start
    let (_, raw) = http_get_raw(&h.addr, "/world").expect("get /world");
    let world: braid_wire::WireResponse =
        serde_json::from_str(raw.split("\r\n\r\n").nth(1).unwrap()).expect("world json");
    assert_eq!(world.data["walk_in_count"], 0);

    // the browser-facing rule: POST /world with just {target, content} — the
    // bridge holds the write:world token, the page never touches a key
    let place = r#"{"target": "sky-well", "content": "A room that floats above the archive."}"#;
    let resp = http_post_raw(&h.addr, "/world", place).expect("post /world");
    assert!(resp.ok, "place failed: {:?}", resp.error);
    assert!(resp.data["cid"].as_str().is_some(), "cid echoed to the page");

    // walk-in updates from the SAME ledger, not a side channel
    let (_, raw) = http_get_raw(&h.addr, "/world").expect("get /world after place");
    let after: braid_wire::WireResponse =
        serde_json::from_str(raw.split("\r\n\r\n").nth(1).unwrap()).expect("world json");
    assert_eq!(after.data["walk_in_count"], 1, "the placed fact walks in");
    let fact = &after.data["world"]["facts"][0];
    assert_eq!(fact["target"], "sky-well");
    assert!(fact["provenance"]["signature_ok"].as_bool().unwrap(), "proven over the wire");
    assert_eq!(fact["position"].as_array().unwrap().len(), 3, "deterministic position");

    // tamper that placed fact inside the engine; over the wire it is EXCLUDED
    let cid = fact["provenance"]["cid"].as_str().unwrap().to_string();
    {
        let mut guard = h.router.engine().lock().expect("engine");
        let mut node = guard.log.nodes.get(&cid).unwrap().clone();
        node.body.payload = serde_json::json!({"name": "tampered-room", "content": "evil"});
        assert!(node.audit.as_ref().unwrap().verified(&node.signer), "strand sig survives (documented)");
        assert!(!braid_core::engine::node_is_proven(&node), "precommitment no longer binds");
        guard.log.nodes.insert(cid, node);
    }
    let (_, raw) = http_get_raw(&h.addr, "/world").expect("get /world after tamper");
    let tampered: braid_wire::WireResponse =
        serde_json::from_str(raw.split("\r\n\r\n").nth(1).unwrap()).expect("world json");
    assert_eq!(tampered.data["excluded"], 1, "spatial facts obey the fact gate too");
    assert_eq!(tampered.data["proven"], 0, "the only fact was tampered");
}