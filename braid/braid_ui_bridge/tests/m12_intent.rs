//! m12 (spec-forth) — the intent strand, live over the ONE wire.
//!
//! The m1 stub promised: nothing speculative enters motion until atomic
//! braided triplets are proven end-to-end (m3). Triplets have run on every
//! strand since m4, so m12 makes the intent strand REAL: desires commit as
//! ordinary braided `write:intent` nodes, stay OPEN until later PROVEN work
//! references them via `payload.fulfills == <intent cid>`, and then RESOLVE
//! with that fulfilling node's cid as on-chain provenance. No speculative
//! execution — a desire and its fulfillment are both real ledger motion.

use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;

use braid_core::crypto::new_signing_key;
use braid_core::engine::BraidEngine;
use braid_core::intent::{INTENT_OP, IntentStrand};
use braid_core::policy::{policy_from_toml, PolicySnapshot};
use braid_keys::{did_key, SessionMacaroon};
use braid_ui_bridge::frontdoor::{Door, DoorRegistration, Router};
use braid_ui_bridge::handler_from;
use braid_wire::{http_get_raw, http_post_raw, BraidWireServer, WireOp, WireRequest};
use ed25519_dalek::{SigningKey, VerifyingKey};
use rand::rngs::OsRng;

const GENESIS: &str = r#"
name = "genesis-m12-intent"
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
allow = true
capability = "write:intent:*"

[[rules]]
allow = false
capability = "admin:*:*"
"#;

fn mac(loc: &str, sk: &SigningKey, caps: &[&str]) -> SessionMacaroon {
    SessionMacaroon::issue(loc, &did_key(&VerifyingKey::from(sk)), caps, sk)
}

struct Harness {
    addr: String,
    read3: SessionMacaroon,
    note: SessionMacaroon,
    intent: SessionMacaroon,
}

impl Harness {
    fn post(&self, req: &WireRequest) -> braid_wire::WireResponse {
        let body = serde_json::to_string(req).unwrap();
        http_post_raw(&self.addr, "/v1/op", &body).unwrap_or_else(braid_wire::WireResponse::err)
    }

    fn commit_intent(&self, desire: &str, target: &str) -> braid_wire::WireResponse {
        self.post(&WireRequest::new("http", self.intent.clone(), WireOp::Write {
            snapshot: String::new(),
            op: INTENT_OP.into(),
            target: target.into(),
            payload: IntentStrand::carrying(desire, target, serde_json::Value::Null, 1),
        }))
    }

    fn view_intent(&self) -> braid_wire::WireResponse {
        self.post(&WireRequest::new("http", self.read3.clone(), WireOp::Intent { snapshot: String::new() }))
    }

    fn prove(&self, cid: &str) -> bool {
        let r = self.post(&WireRequest::new("http", self.read3.clone(), WireOp::Prove { cid: cid.into() }));
        r.ok && r.data["verified"].as_bool().unwrap_or(false)
    }
}

fn boot() -> Harness {
    static SEQ: AtomicU64 = AtomicU64::new(0);
    let seq = SEQ.fetch_add(1, Ordering::Relaxed);
    let path = format!("/tmp/opencode/braid-m12-intent-{}-{seq}.jsonl", std::process::id());
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

    let door_sk = SigningKey::generate(&mut OsRng);
    let door_did = did_key(&VerifyingKey::from(&door_sk));

    let router = Arc::new(
        Router::new(
            Arc::new(Mutex::new(engine)),
            vec![
                DoorRegistration { door: Door::Lumen, did: door_did.clone(), location: "door1".into() },
                DoorRegistration { door: Door::Axiom, did: door_did.clone(), location: "door2".into() },
                DoorRegistration { door: Door::Mem, did: door_did, location: "door3".into() },
            ],
            "snap-genesis",
        ),
    );

    let read3 = mac("door3", &door_sk, &["read:*:*"]);
    let note = mac("door3", &door_sk, &["write:note:*"]);
    let intent = mac("door3", &door_sk, &["write:intent:*"]);

    let server = BraidWireServer::new("127.0.0.1:0", handler_from(router)).expect("bind");
    let addr = server.local_addr();
    thread::spawn(move || {
        let _ = server.run();
    });
    thread::sleep(Duration::from_millis(150));

    Harness { addr, read3, note, intent }
}

fn raw_post(addr: &str, path: &str, body: &str) -> Result<(u16, String), String> {
    use std::io::{Read, Write};
    use std::net::TcpStream;
    let mut stream = TcpStream::connect(addr).map_err(|e| format!("connect: {e}"))?;
    let req = format!(
        "POST {path} HTTP/1.1\r\nHost: {addr}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
        body.len()
    );
    stream.write_all(req.as_bytes()).map_err(|e| format!("write: {e}"))?;
    let mut resp_buf = Vec::new();
    stream.read_to_end(&mut resp_buf).map_err(|e| format!("read: {e}"))?;
    let text = String::from_utf8_lossy(&resp_buf).to_string();
    let status = text
        .lines()
        .next()
        .and_then(|l| l.split_whitespace().nth(1))
        .and_then(|s| s.parse::<u16>().ok())
        .ok_or("no status line")?;
    let body = text.split("\r\n\r\n").nth(1).unwrap_or("");
    Ok((status, body.to_string()))
}

#[test]
fn chosen_desires_commit_and_later_proven_work_resolves_them() {
    let h = boot();

    // 1. Three desires commit as ordinary braided write:intent nodes.
    let a = h.commit_intent("the tower shines at one address", "place/m12-tower");
    let b = h.commit_intent("the garden holds one name", "place/m12-garden");
    let c = h.commit_intent("the sundial keeps exact time", "place/m12-sundial");
    assert!(a.ok && b.ok && c.ok, "intents commit: {:?} {:?} {:?}", a.error, b.error, c.error);
    assert!(a.data["precommit_verified"].as_bool().unwrap_or(false));
    let a_cid = a.data["cid"].as_str().unwrap().to_string();
    let c_cid = c.data["cid"].as_str().unwrap().to_string();

    // 2. All three are OPEN, committed, proven — braided triplets intact.
    let v = h.view_intent();
    assert!(v.ok, "intent view: {:?}", v.error);
    assert_eq!(v.data["kind"], "intent");
    assert_eq!(v.data["submitted"].as_u64().unwrap_or(0), 3);
    assert_eq!(v.data["open"].as_u64().unwrap_or(0), 3);
    assert_eq!(v.data["resolved"].as_u64().unwrap_or(0), 0);
    assert_eq!(v.data["pending_count"].as_u64().unwrap_or(0), 3);
    let intents = v.data["intents"].as_array().unwrap();
    assert_eq!(intents.len(), 3);
    for i in intents.iter() {
        assert_eq!(i["status"], "open");
        assert!(i["provenance_ok"].as_bool().unwrap_or(false));
        assert_eq!(i["capability"], "write:intent:*");
        assert_eq!(i["snapshot"], "snap-genesis");
    }
    assert!(h.prove(&a_cid), "intents prove to genesis like every node");

    // 3. Real work fulfills one intent: an ordinary note write that carries
    //    `payload.fulfills == <intent cid>`. Resolution is committed motion.
    let done = h.post(&WireRequest::new("http", h.note.clone(), WireOp::Write {
        snapshot: String::new(),
        op: "write:note".into(),
        target: "place/m12-sundial".into(),
        payload: IntentStrand::intentional(serde_json::json!({ "content": "sundial placed and set" }), &c_cid),
    }));
    assert!(done.ok, "resolve write: {:?}", done.error);
    let done_cid = done.data["cid"].as_str().unwrap().to_string();
    assert_ne!(done_cid, c_cid);

    let v = h.view_intent();
    assert_eq!(v.data["open"].as_u64().unwrap_or(0), 2);
    assert_eq!(v.data["resolved"].as_u64().unwrap_or(0), 1);
    assert_eq!(v.data["pending_count"].as_u64().unwrap_or(0), 2);
    let intents = v.data["intents"].as_array().unwrap();
    let sun = intents.iter().find(|i| i["cid"] == c_cid).expect("sundial intent present");
    assert_eq!(sun["status"], "resolved");
    assert_eq!(sun["fulfilled_by"]["cid"], done_cid);
    assert_eq!(sun["fulfilled_by"]["op"], "write:note");
    let tower = intents.iter().find(|i| i["cid"] == a_cid).expect("tower intent present");
    assert_eq!(tower["status"], "open");
    assert!(tower["fulfilled_by"].is_null());

    // 4. Both the desire and its fulfillment still prove to genesis.
    assert!(h.prove(&c_cid) && h.prove(&done_cid));
}

#[test]
fn intent_read_is_gated_like_every_read() {
    let h = boot();
    h.commit_intent("a desire", "place/m12-gated");

    // A write-only intent token (write:intent:* but no read grant) cannot see
    // the strand — same gate shape as audio/world/timeline reads.
    let denied = h.post(&WireRequest::new("http", h.intent.clone(), WireOp::Intent { snapshot: String::new() }));
    assert!(!denied.ok, "write-only token must be denied the intent read");
    let msg = denied.error.clone().unwrap_or_default();
    assert!(msg.contains("does not grant read"), "honest denial: {msg}");
}

#[test]
fn intent_submit_needs_the_write_grant() {
    let h = boot();

    // A read-only token is not a write token: committing write:intent from it
    // is denied by the same policy authority that licenses every other write.
    let forged = h.post(&WireRequest::new("http", h.read3.clone(), WireOp::Write {
        snapshot: String::new(),
        op: INTENT_OP.into(),
        target: "place/m12-forged".into(),
        payload: IntentStrand::carrying("a forged desire", "place/m12-forged", serde_json::Value::Null, 1),
    }));
    assert!(!forged.ok, "read-only token cannot commit write:intent");
    assert_eq!(h.view_intent().data["submitted"].as_u64().unwrap_or(0), 0, "nothing was committed");
}

#[test]
fn shell_intent_surface_streams_real_intent_view_and_submit() {
    use braid_ui_bridge::door3_intent_shell;

    static SEQ: AtomicU64 = AtomicU64::new(0);
    let seq = SEQ.fetch_add(1, Ordering::Relaxed);
    let path = format!("/tmp/opencode/braid-m12-shell-{}-{seq}.jsonl", std::process::id());
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

    let door_sk = SigningKey::generate(&mut OsRng);
    let door_did = did_key(&VerifyingKey::from(&door_sk));
    let router = Arc::new(
        Router::new(
            Arc::new(Mutex::new(engine)),
            vec![DoorRegistration { door: Door::Mem, did: door_did.clone(), location: "door3".into() }],
            "snap-genesis",
        ),
    );

    let world = mac("door3", &door_sk, &["write:world:*"]);
    let read = mac("door3", &door_sk, &["read:*:*"]);
    let intent = mac("door3", &door_sk, &["write:intent:*"]);

    let shell = door3_intent_shell(read.clone(), world, read.clone(), intent);
    let server = BraidWireServer::new("127.0.0.1:0", handler_from(router))
        .expect("bind")
        .with_shell(shell);
    let addr = server.local_addr();
    thread::spawn(move || {
        let _ = server.run();
    });
    thread::sleep(Duration::from_millis(150));

    // The page carries the intent surface (and its markers are gone).
    let (status, html) = http_get_raw(&addr, "/").expect("GET /");
    assert_eq!(status, 200);
    assert!(html.contains("intentPanel"), "walk-in renders the intent panel");
    assert!(html.contains("id=\"intentOpen\""), "walk-in header shows open count");
    assert!(!html.contains("<!--INTENT_PANEL-->"), "marker is replaced, not served");

    // GET /intent streams the committed projection (kind=intent).
    let (s, view) = http_get_raw(&addr, "/intent").expect("GET /intent");
    assert_eq!(s, 200);
    let view_body = view.split("\r\n\r\n").nth(1).unwrap_or("");
    assert!(view_body.contains("\"submitted\":0"), "empty strand view: {view_body}");

    // POST /intent commits a desire through the bridge-held write token —
    // the browser never holds a key.
    let (s, body) = raw_post(&addr, "/intent", r#"{"desire":"the aperture stays open","target":"place/m12-aperture"}"#).expect("POST /intent");
    assert_eq!(s, 200, "post body: {body}");
    let json: serde_json::Value = serde_json::from_str(&body).unwrap();
    assert!(json["ok"].as_bool().unwrap_or(false), "post denied: {body}");
    let intent_cid = json["data"]["cid"].as_str().unwrap().to_string();
    assert!(!intent_cid.is_empty());

    // The strand now shows one OPEN intent, committed with live provenance.
    let (s, view) = http_get_raw(&addr, "/intent").expect("GET /intent second");
    assert_eq!(s, 200);
    let view_body = view.split("\r\n\r\n").nth(1).unwrap_or("");
    let json: serde_json::Value = serde_json::from_str(view_body).unwrap();
    assert_eq!(json["data"]["open"].as_u64().unwrap_or(0), 1);
    assert_eq!(json["data"]["intents"][0]["cid"], intent_cid);
    assert_eq!(json["data"]["intents"][0]["status"], "open");
    assert!(json["data"]["intents"][0]["provenance_ok"].as_bool().unwrap_or(false));
}