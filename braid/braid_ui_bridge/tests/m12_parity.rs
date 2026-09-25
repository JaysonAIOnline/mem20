//! m12 (spec-forth) — door-parity sweep WITH the intent strand AND the
//! speaking spine: every rib, every door, the INTENT strand, and the SPEECH
//! strand all converge at ONE address on ONE ledger.
//!
//! The m10/m11 convergence facts (same chain, same snapshot, same count) are
//! re-proven here with the intent strand added: after the 200 rib writes, the
//! spatial place, and the escalated destroy, a desire commits as an ordinary
//! `write:intent` node, and real work (a note carrying `payload.fulfills`)
//! resolves it. Every door reads 204; the spine speaks the final three nodes
//! (destroy, intent, resolve) in commit order; and the whole chain — intent
//! and resolution included — still proves to genesis at the same address.
//! If kokoro is unreachable the audio op denies honestly; nothing is faked.

use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;

use braid_core::crypto::new_signing_key;
use braid_core::engine::BraidEngine;
use braid_core::intent::{INTENT_OP, IntentStrand};
use braid_core::policy::{policy_from_toml, PolicySnapshot};
use braid_drive::wire::WireRib;
use braid_keys::{did_key, SessionMacaroon};
use braid_sonic::tts::TtsClient;
use braid_ui_bridge::frontdoor::{Door, DoorRegistration, Router};
use braid_ui_bridge::handler_from;
use braid_wire::{http_post_raw, BraidWireServer, WireOp, WireRequest};
use ed25519_dalek::{SigningKey, VerifyingKey};
use rand::rngs::OsRng;

const GENESIS: &str = r#"
name = "genesis-m12-parity"
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
name = "escalation-m12-parity"
version = 1

[[rules]]
allow = true
capability = "admin:destroy:*"

[[rules]]
allow = false
capability = "admin:wipe:*"
"#;

const STRANDS: usize = 8;
const PER_STRAND: usize = 25;
const TOTAL: usize = STRANDS * PER_STRAND; // 200 rib writes
const AFTER: usize = TOTAL + 4; // + spatial place + escalated destroy + intent + fulfilling note = 204

fn mac(loc: &str, sk: &SigningKey, caps: &[&str]) -> SessionMacaroon {
    SessionMacaroon::issue(loc, &did_key(&VerifyingKey::from(sk)), caps, sk)
}

struct Harness {
    addr: String,
    read1: SessionMacaroon,
    read2: SessionMacaroon,
    read3: SessionMacaroon,
    note: SessionMacaroon,
    world: SessionMacaroon,
    human: SessionMacaroon,
    intent: SessionMacaroon,
}

impl Harness {
    fn post(&self, req: &WireRequest) -> braid_wire::WireResponse {
        let body = serde_json::to_string(req).unwrap();
        http_post_raw(&self.addr, "/v1/op", &body).unwrap_or_else(braid_wire::WireResponse::err)
    }

    fn read(&self, token: &SessionMacaroon) -> u64 {
        let r = self.post(&WireRequest::new("http", token.clone(), WireOp::Read {
            snapshot: String::new(),
            op_filter: None,
        }));
        assert!(r.ok, "convergence read must not fail: {:?}", r.error);
        r.data["count"].as_u64().unwrap_or(0)
    }

    fn hear(&self, token: &SessionMacaroon, depth: u64) -> braid_wire::WireResponse {
        self.post(&WireRequest::new("http", token.clone(), WireOp::Audio { snapshot: String::new(), depth }))
    }
}

fn boot() -> Harness {
    use std::sync::atomic::{AtomicU64, Ordering};
    static SEQ: AtomicU64 = AtomicU64::new(0);
    let seq = SEQ.fetch_add(1, Ordering::Relaxed);
    let path = format!("/tmp/opencode/braid-m12-parity-{}-{seq}.jsonl", std::process::id());
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

    let read1 = mac("door1", &door_sk, &["read:*:*"]);
    let read2 = mac("door2", &door_sk, &["read:*:*"]);
    let read3 = mac("door3", &door_sk, &["read:*:*"]);
    let note = mac("door1", &door_sk, &["write:note:*"]);
    let world = mac("door3", &door_sk, &["write:world:*"]);
    let intent = mac("door3", &door_sk, &["write:intent:*"]);
    let human = mac("human-escalation", &human_sk, &["admin:destroy:*"]);

    let server = BraidWireServer::new("127.0.0.1:0", handler_from(router)).expect("bind");
    let addr = server.local_addr();
    thread::spawn(move || {
        let _ = server.run();
    });
    thread::sleep(Duration::from_millis(150));

    Harness { addr, read1, read2, read3, note, world, human, intent }
}

#[test]
fn every_door_the_intent_strand_and_the_spine_converge_on_one_ledger() {
    let h = boot();

    // 1. ONE address, all three doors resolve, gate armed, intent writeable.
    let reg = h.post(&WireRequest::new("http", h.read3.clone(), WireOp::Registry));
    assert!(reg.ok, "registry: {:?}", reg.error);
    assert_eq!(reg.data["doors"].as_array().map(|d| d.len()).unwrap_or(0), 3, "three doors at one address");
    assert_eq!(reg.data["default_snapshot"], "snap-genesis");
    assert!(reg.data["escalation_armed"].as_bool().unwrap_or(false));

    // 2. The data plane: 200 rib writes through /v1/op.
    let rib = WireRib::new(&h.addr, h.note.clone());
    let rig = rib.rig_write(STRANDS, PER_STRAND, "write:note", "rib/place");
    assert!(rig.all_ok(), "rib must commit 200/200 — failed {}", rig.failed);

    // 3. door3 spatial rib: one creative place + one escalated destroy.
    let place = h.post(&WireRequest::new("http", h.world.clone(), WireOp::Spatial {
        snapshot: String::new(),
        op: "write:world".into(),
        target: "place/m12-sundial".into(),
        payload: serde_json::json!({"name": "M12 Sundial", "content": "the spine speaks here"}),
    }));
    assert!(place.ok, "spatial place: {:?}", place.error);

    let mut destroy = WireRequest::new("http", h.world.clone(), WireOp::Spatial {
        snapshot: String::new(),
        op: "admin:destroy".into(),
        target: "place/m12-sundial".into(),
        payload: serde_json::json!({"reason": "parity sweep"}),
    });
    assert!(!h.post(&destroy).ok, "single-token destroy stays denied");
    destroy.escalation = Some(h.human.clone());
    let esc = h.post(&destroy);
    assert!(esc.ok, "escalated destroy: {:?}", esc.error);

    // 4. The INTENT STRAND, m12: a desire commits as an ordinary braided
    //    `write:intent` node (same single-write path as every write) and then
    //    REAL work resolves it — a note that carries `payload.fulfills`.
    let intent_w = h.post(&WireRequest::new("http", h.intent.clone(), WireOp::Write {
        snapshot: String::new(),
        op: INTENT_OP.into(),
        target: "place/m12-sundial".into(),
        payload: IntentStrand::carrying("the sundial keeps one time again", "place/m12-sundial", serde_json::json!({ "strand": "m12" }), 1),
    }));
    assert!(intent_w.ok, "intent commits: {:?}", intent_w.error);
    assert!(intent_w.data["precommit_verified"].as_bool().unwrap_or(false));
    let intent_cid = intent_w.data["cid"].as_str().unwrap().to_string();

    let resolve_w = h.post(&WireRequest::new("http", h.note.clone(), WireOp::Write {
        snapshot: String::new(),
        op: "write:note".into(),
        target: "place/m12-sundial".into(),
        payload: IntentStrand::intentional(serde_json::json!({ "content": "sundial re-set by real work" }), &intent_cid),
    }));
    assert!(resolve_w.ok, "resolution commits: {:?}", resolve_w.error);
    let resolve_cid = resolve_w.data["cid"].as_str().unwrap().to_string();
    assert_ne!(resolve_cid, intent_cid);

    let iv = h.post(&WireRequest::new("http", h.read3.clone(), WireOp::Intent { snapshot: String::new() }));
    assert!(iv.ok, "intent view: {:?}", iv.error);
    assert_eq!(iv.data["kind"], "intent");
    assert_eq!(iv.data["submitted"].as_u64().unwrap_or(0), 1);
    assert_eq!(iv.data["open"].as_u64().unwrap_or(0), 0);
    assert_eq!(iv.data["resolved"].as_u64().unwrap_or(0), 1);
    assert_eq!(iv.data["pending_count"].as_u64().unwrap_or(0), 0);
    let it = &iv.data["intents"][0];
    assert_eq!(it["cid"], intent_cid);
    assert_eq!(it["status"], "resolved");
    assert!(it["provenance_ok"].as_bool().unwrap_or(false));
    assert_eq!(it["fulfilled_by"]["cid"], resolve_cid);
    assert_eq!(it["fulfilled_by"]["op"], "write:note");

    // 5. Door parity — every read plane converges on 204 (intent included).
    assert_eq!(h.read(&h.read1) as usize, AFTER, "door1 witness sees 204");
    assert_eq!(h.read(&h.read2) as usize, AFTER, "door2 structural read converges");
    let world_scene = h.post(&WireRequest::new("http", h.read3.clone(), WireOp::World { snapshot: String::new() }));
    assert!(world_scene.ok, "walk-in: {:?}", world_scene.error);
    assert_eq!(world_scene.data["walk_in_count"].as_u64().unwrap_or(0), AFTER as u64, "door3 walk-in 204");
    assert_eq!(world_scene.data["excluded"].as_u64().unwrap_or(1), 0, "no tampered node walks in");

    // 6. The spine SPEAKS THE SAME CHAIN: the last three sounds are the
    //    destroy, the intent, and its resolution — in commit order.
    let a = h.hear(&h.read3, 3);
    if !a.ok {
        let msg = format!("{} {}", a.error.clone().unwrap_or_default(), a.data);
        assert!(msg.contains("audio strand"), "parity audio must be real or honestly denied: {msg}");
        // kokoro down: the sweep keeps the rib + intent proof, never fakes audio
    } else {
        assert_eq!(a.data["spoken"].as_u64().unwrap_or(0), 3, "spine speaks exactly depth 3");
        let segments = a.data["segments"].as_array().unwrap();
        assert_eq!(segments.len(), 3);
        let destroy_cid = esc.data["cid"].as_str().unwrap().to_string();
        assert_eq!(segments[2]["cid"].as_str().unwrap(), resolve_cid, "last echo is the resolution");
        assert_eq!(segments[1]["cid"].as_str().unwrap(), intent_cid, "middle echo is the intent");
        assert_eq!(segments[0]["cid"].as_str().unwrap(), destroy_cid, "first echo is the destroy");
        for seg in segments.iter() {
            assert!(seg["signature_ok"].as_bool().unwrap_or(false), "every echo is a proven node");
            assert!(seg["ms"].as_u64().unwrap_or(0) > 0, "every echo is a real render");
        }
        assert_eq!(a.data["sample_rate"].as_u64().unwrap_or(0), 24000, "kokoro 24kHz spine");
        let wav = braid_wire::b64::decode(a.data["wav_b64"].as_str().unwrap()).expect("wav base64");
        assert!(wav.starts_with(b"RIFF") && &wav[8..12] == b"WAVE", "one real backbone wav for the whole spine");
    }

    // 7. Goodbye: the whole chain — ribs, place, destroy, INTENT, and its
    //    resolution — still proves to genesis at the same address.
    for cid in [
        &rig.cids[0],
        &rig.cids[199],
        &place.data["cid"].as_str().unwrap().to_string(),
        &esc.data["cid"].as_str().unwrap().to_string(),
        &intent_cid,
        &resolve_cid,
    ] {
        let p = h.post(&WireRequest::new("http", h.read2.clone(), WireOp::Prove { cid: cid.to_string() }));
        assert!(p.ok, "prove {cid:?}: {:?}", p.error);
        assert!(p.data["verified"].as_bool().unwrap_or(false), "{cid:?} still proves to genesis");
    }
}