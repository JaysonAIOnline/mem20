//! m13 (spec-forth) — the TERMINAL DOOR's unified read view: TAIL, INSPECT,
//! PROVE, POLICY, QUERY over the ONE wire, read-gated exactly like every read.

use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;

use braid_core::crypto::new_signing_key;
use braid_core::engine::BraidEngine;
use braid_core::policy::{policy_from_toml, PolicySnapshot};
use braid_keys::{did_key, SessionMacaroon};
use braid_sonic::tts::TtsClient;
use braid_ui_bridge::frontdoor::{Door, DoorRegistration, Router};
use braid_ui_bridge::handler_from;
use braid_wire::{http_get_raw, http_post_raw, BraidWireServer, WireOp, WireRequest};
use ed25519_dalek::{SigningKey, VerifyingKey};
use rand::rngs::OsRng;

const GENESIS: &str = r#"
name = "genesis-m13-terminal"
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

const ESCALATION: &str = r#"
name = "escalation-m13-terminal"
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

#[allow(dead_code)]
struct Harness {
    addr: String,
    read: SessionMacaroon,
    write_note: SessionMacaroon,
    write_intent: SessionMacaroon,
    write_world: SessionMacaroon,
    human: SessionMacaroon,
}

impl Harness {
    fn post(&self, req: &WireRequest) -> braid_wire::WireResponse {
        let body = serde_json::to_string(req).unwrap();
        http_post_raw(&self.addr, "/v1/op", &body).unwrap_or_else(braid_wire::WireResponse::err)
    }

    fn tail_raw(&self, since: Option<&str>, limit: Option<u64>) -> braid_wire::WireResponse {
        let mut path = "/tail".to_string();
        let mut qs = Vec::new();
        if let Some(s) = since {
            qs.push(format!("since={s}"));
        }
        if let Some(l) = limit {
            qs.push(format!("limit={l}"));
        }
        if !qs.is_empty() {
            path.push('?');
            path.push_str(&qs.join("&"));
        }
        let (_status, raw) = http_get_raw(&self.addr, &path).unwrap();
        let body = raw.split("\r\n\r\n").nth(1).unwrap_or("");
        serde_json::from_str(body).unwrap()
    }

    fn inspect_raw(&self) -> braid_wire::WireResponse {
        let (_status, raw) = http_get_raw(&self.addr, "/inspect").unwrap();
        let body = raw.split("\r\n\r\n").nth(1).unwrap_or("");
        serde_json::from_str(body).unwrap()
    }

    fn prove_raw(&self, cid: &str) -> braid_wire::WireResponse {
        let (_status, raw) = http_get_raw(&self.addr, &format!("/prove?cid={cid}")).unwrap();
        let body = raw.split("\r\n\r\n").nth(1).unwrap_or("");
        serde_json::from_str(body).unwrap()
    }

    fn policy_raw(&self) -> braid_wire::WireResponse {
        let (_status, raw) = http_get_raw(&self.addr, "/policy").unwrap();
        let body = raw.split("\r\n\r\n").nth(1).unwrap_or("");
        serde_json::from_str(body).unwrap()
    }

    fn query_raw(&self, cap: &str) -> braid_wire::WireResponse {
        let body = serde_json::json!({ "cap": cap }).to_string();
        http_post_raw(&self.addr, "/query", &body).unwrap_or_else(braid_wire::WireResponse::err)
    }
}

fn boot() -> Harness {
    use std::sync::atomic::{AtomicU64, Ordering};
    static SEQ: AtomicU64 = AtomicU64::new(0);
    let seq = SEQ.fetch_add(1, Ordering::Relaxed);
    let path = format!("/tmp/opencode/braid-m13-terminal-{}-{seq}.jsonl", std::process::id());
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

    let router = Arc::new(
        Router::new(
            Arc::new(Mutex::new(engine)),
            vec![
                DoorRegistration { door: Door::Lumen, did: door_did.clone(), location: "door1".into() },
                DoorRegistration { door: Door::Axiom, did: door_did.clone(), location: "door2".into() },
                DoorRegistration { door: Door::Mem, did: door_did, location: "door3".into() },
            ],
            "snap-genesis",
        )
        .with_escalation(human_did, "snap-escalation")
        .with_tts(TtsClient::new()),
    );

    let read = mac("door3", &door_sk, &["read:*:*"]);
    let write_note = mac("door1", &door_sk, &["write:note:*"]);
    let write_intent = mac("door3", &door_sk, &["write:intent:*"]);
    let write_world = mac("door3", &door_sk, &["write:world:*"]);
    let human = mac("human-escalation", &human_sk, &["admin:destroy:*"]);

    let shell = braid_ui_bridge::door3_terminal_shell(
        read.clone(), write_world.clone(), read.clone(), write_intent.clone(),
        read.clone(), "af_heart", 3, 64,
    );
    let server = BraidWireServer::new("127.0.0.1:0", handler_from(router)).expect("bind").with_shell(shell);
    let addr = server.local_addr();
    thread::spawn(move || {
        let _ = server.run();
    });
    thread::sleep(Duration::from_millis(150));

    Harness { addr, read, write_note, write_intent, write_world, human }
}

#[test]
fn tail_and_inspect_are_read_gated_like_every_read() {
    let h = boot();

    // write-only token cannot tail
    let denied = h.post(&WireRequest::new("http", h.write_note.clone(), WireOp::Tail {
        snapshot: String::new(),
        since_cid: None,
        limit: 10,
    }));
    assert!(!denied.ok, "write-only token must be denied tail");
    assert!(denied.error.as_ref().unwrap().contains("does not grant read"));

    // write-only token cannot inspect
    let denied = h.post(&WireRequest::new("http", h.write_note.clone(), WireOp::Inspect));
    assert!(!denied.ok, "write-only token must be denied inspect");
    assert!(denied.error.as_ref().unwrap().contains("does not grant read"));
}

#[test]
fn tail_streams_real_committed_nodes_with_prev_links_and_cursor() {
    let h = boot();

    // Commit 5 notes
    let mut cids = Vec::new();
    for i in 0..5 {
        let w = h.post(&WireRequest::new("http", h.write_note.clone(), WireOp::Write {
            snapshot: String::new(),
            op: "write:note".into(),
            target: format!("place/m13-{i}"),
            payload: serde_json::json!({ "content": format!("note {i}") }),
        }));
        assert!(w.ok, "write {i}: {:?}", w.error);
        cids.push(w.data["cid"].as_str().unwrap().to_string());
    }

    // Tail 3 from head (no since) -> last 3
    let t = h.tail_raw(None, Some(3));
    assert!(t.ok, "tail: {:?}", t.error);
    let nodes = t.data["nodes"].as_array().unwrap();
    assert_eq!(nodes.len(), 3, "tail limit respected");
    assert_eq!(nodes[0]["cid"], cids[2], "tail starts at correct offset");
    assert_eq!(nodes[1]["cid"], cids[3]);
    assert_eq!(nodes[2]["cid"], cids[4]);
    // Each node has prev link
    for n in nodes {
        assert!(n["prev"].is_string() || n["prev"].is_null(), "node has prev");
    }
    assert!(t.data["head_cid"].as_str().unwrap() == cids[4], "head matches last write");
    assert!(t.data["truncated"].as_bool().unwrap_or(false), "truncated: 5 available > limit 3");

    // Since cursor: resume after cids[2] (index 2) -> cids[3], cids[4]
    let t = h.tail_raw(Some(&cids[2]), Some(10));
    assert!(t.ok);
    let nodes = t.data["nodes"].as_array().unwrap();
    assert_eq!(nodes.len(), 2, "since cursor works");
    assert_eq!(nodes[0]["cid"], cids[3]);
    assert_eq!(nodes[1]["cid"], cids[4]);

    // Since unknown cid -> honest denial
    let t = h.tail_raw(Some("brUNKNOWN"), Some(10));
    assert!(!t.ok, "unknown since_cid must be denied");
    assert!(t.error.unwrap().contains("is not on this ledger"));
}

#[test]
fn inspect_reports_single_head_and_door_positions() {
    let h = boot();

    // Before any writes, inspect shows empty ledger
    let i = h.inspect_raw();
    assert!(i.ok, "inspect: {:?}", i.error);
    assert_eq!(i.data["heads"].as_u64().unwrap_or(1), 0);
    assert_eq!(i.data["forks"].as_u64().unwrap_or(0), 0);
    assert_eq!(i.data["nodes"].as_u64().unwrap_or(0), 0);
    assert_eq!(i.data["head_depth"].as_u64().unwrap_or(0), 0);
    assert_eq!(i.data["snapshot"], "snap-genesis");
    let doors = i.data["doors"].as_array().unwrap();
    assert_eq!(doors.len(), 3, "three registered doors");
    for d in doors {
        assert_eq!(d["view_position"].as_u64().unwrap_or(0), 0, "all doors at 0 initially");
    }

    // Commit one note (genesis depth = 0)
    let w = h.post(&WireRequest::new("http", h.write_note.clone(), WireOp::Write {
        snapshot: String::new(),
        op: "write:note".into(),
        target: "place/m13-one".into(),
        payload: serde_json::json!({ "content": "one" }),
    }));
    assert!(w.ok);
    let cid = w.data["cid"].as_str().unwrap().to_string();

    // First inspect: _MEM hasnt't read yet, so view_position = 0
    let i1 = h.inspect_raw();
    assert!(i1.ok);
    assert_eq!(i1.data["heads"].as_u64().unwrap_or(0), 1, "single head");
    assert_eq!(i1.data["forks"].as_u64().unwrap_or(0), 0, "no forks in single-writer chain");
    assert_eq!(i1.data["nodes"].as_u64().unwrap_or(0), 1, "one node total");
    assert_eq!(i1.data["head_cid"].as_str().unwrap(), cid);
    assert_eq!(i1.data["head_depth"].as_u64().unwrap_or(0), 0, "genesis depth is 0");
    let doors1 = i1.data["doors"].as_array().unwrap();
    let door_mem1 = doors1.iter().find(|d| d["door"] == "door3").unwrap();
    assert_eq!(door_mem1["view_position"].as_u64().unwrap_or(0), 0, "_MEM hasnt't read yet");

    // Second inspect: now MEM has read, view_position advances
    let i2 = h.inspect_raw();
    assert!(i2.ok);
    let doors2 = i2.data["doors"].as_array().unwrap();
    let door_mem2 = doors2.iter().find(|d| d["door"] == "door3").unwrap();
    assert!(door_mem2["view_position"].as_u64().unwrap_or(0) >= 1, "advanced after first inspect");
}

#[test]
fn terminal_shell_surfaces_are_keyless_and_real() {
    let h = boot();

    // Commit a note so there's data
    let w = h.post(&WireRequest::new("http", h.write_note.clone(), WireOp::Write {
        snapshot: String::new(),
        op: "write:note".into(),
        target: "place/m13-shell".into(),
        payload: serde_json::json!({ "content": "shell test" }),
    }));
    assert!(w.ok);
    let cid = w.data["cid"].as_str().unwrap().to_string();

    // GET /inspect keyless -> 200 JSON with heads=1
    let (status, raw) = http_get_raw(&h.addr, "/inspect").unwrap();
    assert_eq!(status, 200);
    let body = raw.split("\r\n\r\n").nth(1).unwrap_or("");
    let json: serde_json::Value = serde_json::from_str(body).unwrap();
    assert!(json["ok"].as_bool().unwrap_or(false));
    assert_eq!(json["data"]["heads"].as_u64().unwrap_or(0), 1);

    // GET /tail keyless -> 200 JSON
    let (status, raw) = http_get_raw(&h.addr, "/tail?limit=5").unwrap();
    assert_eq!(status, 200);
    let body = raw.split("\r\n\r\n").nth(1).unwrap_or("");
    let json: serde_json::Value = serde_json::from_str(body).unwrap();
    assert!(json["ok"].as_bool().unwrap_or(false));
    assert_eq!(json["data"]["nodes"].as_array().unwrap().len(), 1);

    // GET /policy keyless -> full snapshot rule list
    let (status, raw) = http_get_raw(&h.addr, "/policy").unwrap();
    assert_eq!(status, 200);
    let body = raw.split("\r\n\r\n").nth(1).unwrap_or("");
    let json: serde_json::Value = serde_json::from_str(body).unwrap();
    assert!(json["ok"].as_bool().unwrap_or(false));
    assert!(json["data"]["policy"]["policy"]["rules"].is_array());

    // GET /prove?cid= keyless -> verified true
    let (status, raw) = http_get_raw(&h.addr, &format!("/prove?cid={cid}")).unwrap();
    assert_eq!(status, 200);
    let body = raw.split("\r\n\r\n").nth(1).unwrap_or("");
    let json: serde_json::Value = serde_json::from_str(body).unwrap();
    assert!(json["ok"].as_bool().unwrap_or(false));
    assert!(json["data"]["verified"].as_bool().unwrap_or(false));
    assert_eq!(json["data"]["cid"], cid);

    // POST /query keyless -> real verdict
    let body = serde_json::json!({ "cap": "write:note:*" }).to_string();
    let resp = http_post_raw(&h.addr, "/query", &body).unwrap();
    assert!(resp.ok);
    assert_eq!(resp.data["allowed"], true);
}

#[test]
fn cli_is_stateless_and_deterministic() {
    let h = boot();

    // Commit a note
    let w = h.post(&WireRequest::new("http", h.write_note.clone(), WireOp::Write {
        snapshot: String::new(),
        op: "write:note".into(),
        target: "place/m13-cli".into(),
        payload: serde_json::json!({ "content": "cli test" }),
    }));
    assert!(w.ok);

    // Run CLI lib functions twice - tail is deterministic (no door view position)
    let e1 = braid_cli::run_tail(&h.addr, None, Some(10)).unwrap();
    let e2 = braid_cli::run_tail(&h.addr, None, Some(10)).unwrap();
    assert_eq!(e1.payload, e2.payload, "tail is deterministic (no door view positions)");

    // Inspect advances door view position each call (expected bridge behavior),
    // but the CLI itself has no state - prove it by checking everything
    // except the door view positions is identical.
    let e1 = braid_cli::run_inspect(&h.addr).unwrap();
    let e2 = braid_cli::run_inspect(&h.addr).unwrap();
    let mut p1 = e1.payload.clone();
    let mut p2 = e2.payload.clone();
    // Door view positions advance on each inspect - remove for comparison
    if let Some(doors) = p1["doors"].as_array_mut() {
        for d in doors { d["view_position"] = serde_json::Value::Null; }
    }
    if let Some(doors) = p2["doors"].as_array_mut() {
        for d in doors { d["view_position"] = serde_json::Value::Null; }
    }
    assert_eq!(p1, p2, "inspect is deterministic aside from door view positions");

    // After a new write, inspect depth changes - proving CLI reads live ledger
    let w2 = h.post(&WireRequest::new("http", h.write_note.clone(), WireOp::Write {
        snapshot: String::new(),
        op: "write:note".into(),
        target: "place/m13-cli2".into(),
        payload: serde_json::json!({ "content": "cli test 2" }),
    }));
    assert!(w2.ok);

    let e3 = braid_cli::run_inspect(&h.addr).unwrap();
    assert_ne!(e2.payload["head_depth"], e3.payload["head_depth"], "inspect reflects new commit");
}

#[test]
fn cli_replay_matches_committed_chain() {
    let h = boot();

    // Commit 3 notes with distinct content
    let mut cids = Vec::new();
    let mut ops = Vec::new();
    for i in 0..3 {
        let w = h.post(&WireRequest::new("http", h.write_note.clone(), WireOp::Write {
            snapshot: String::new(),
            op: "write:note".into(),
            target: format!("place/m13-replay-{i}"),
            payload: serde_json::json!({ "content": format!("replay {i}") }),
        }));
        assert!(w.ok);
        cids.push(w.data["cid"].as_str().unwrap().to_string());
        ops.push(w.data["cid"].as_str().unwrap().to_string()); // track by cid for replay
    }

    // Full tail replay
    let e = braid_cli::run_tail(&h.addr, None, Some(10)).unwrap();
    let nodes = e.payload["nodes"].as_array().unwrap();
    assert_eq!(nodes.len(), 3);
    // Replay: the nodes' ops in order match committed order
    for (idx, n) in nodes.iter().enumerate() {
        assert_eq!(n["cid"], cids[idx], "replay order matches commit order");
    }
}

#[test]
fn prove_shell_returns_real_merkle_spine() {
    let h = boot();

    let w = h.post(&WireRequest::new("http", h.write_note.clone(), WireOp::Write {
        snapshot: String::new(),
        op: "write:note".into(),
        target: "place/m13-prove".into(),
        payload: serde_json::json!({ "content": "prove test" }),
    }));
    assert!(w.ok);
    let cid = w.data["cid"].as_str().unwrap().to_string();

    // Shell /prove
    let p = h.prove_raw(&cid);
    assert!(p.ok);
    assert_eq!(p.data["cid"], cid);
    assert!(p.data["verified"].as_bool().unwrap_or(false));
    let spine = p.data["spine_to_genesis"].as_array().unwrap();
    assert!(!spine.is_empty(), "spine includes at least the node itself");
    assert_eq!(spine[0], cid, "spine starts with the node itself");
}

#[test]
fn policy_shell_returns_full_frozen_snapshot() {
    let h = boot();

    let p = h.policy_raw();
    assert!(p.ok);
    assert_eq!(p.data["snapshot"], "snap-genesis");
    let policy = &p.data["policy"]["policy"];
    assert!(policy["rules"].is_array(), "policy has rule list at data.policy.policy.rules");
    let rules = policy["rules"].as_array().unwrap();
    // genesis allows read/write:note/write:world/write:intent, denies admin:*
    let allows = rules.iter().filter(|r| r["allow"].as_bool().unwrap_or(false)).count();
    assert!(allows >= 4, "genesis has at least 4 allow rules");
}

#[test]
fn query_shell_returns_real_verdict() {
    let h = boot();

    let q = h.query_raw("write:note:*");
    assert!(q.ok);
    assert_eq!(q.data["allowed"], true);

    let q = h.query_raw("admin:destroy:*");
    assert!(q.ok);
    assert_eq!(q.data["allowed"], false);
}