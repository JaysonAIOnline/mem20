//! m10 — rib/ARP convergence: every rib and every door on ONE address, ONE
//! ledger, ONE snapshot.
//!
//! ARP, braid-style: the substrate is DIFFERENT data planes announcing on the
//! same wire — the drive rib (200 concurrent writes), the door3 spatial rib,
//! the godmode escalation rib — and the READ planes: door1 witness, door2
//! structure, door3 walk-in. Convergence means they all RESOLVE to the same
//! address and agree on the same ledger (same default snapshot, same node
//! count, every CID provable back to genesis). Over real HTTP, this file
//! proves:
//!   - one server, three door registrations, one base URL
//!   - the rib (braid_drive over /v1/op) + a spatial place + an escalated
//!     destroy all commit into the SAME chain
//!   - door1 witness reads back 202/202 nodes
//!   - door2 structural read + Prove spines converge on the same count
//!   - door3 walk-in turns the rib's 200 writes into 202 PROVEN facts, 0
//!     excluded — the data plane walks into the spatial surface
//!   - registry resolves all three doors at one address, escalation armed,
//!     default snapshot identical

use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;

use braid_core::crypto::new_signing_key;
use braid_core::engine::BraidEngine;
use braid_core::policy::{policy_from_toml, PolicySnapshot};
use braid_drive::wire::WireRib;
use braid_keys::{did_key, SessionMacaroon};
use braid_ui_bridge::frontdoor::{Door, DoorRegistration, Router};
use braid_ui_bridge::handler_from;
use braid_wire::{http_post_raw, BraidWireServer, WireOp, WireRequest};
use ed25519_dalek::{SigningKey, VerifyingKey};
use rand::rngs::OsRng;

const GENESIS: &str = r#"
name = "genesis-m10-convergence"
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
name = "escalation-m10-convergence"
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
const AFTER: usize = TOTAL + 2; // + spatial place + escalated destroy = 202

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
}

fn boot() -> Harness {
    use std::sync::atomic::{AtomicU64, Ordering};
    static SEQ: AtomicU64 = AtomicU64::new(0);
    let seq = SEQ.fetch_add(1, Ordering::Relaxed);
    let path = format!("/tmp/opencode/braid-m10-conv-{}-{seq}.jsonl", std::process::id());
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

    let server = BraidWireServer::new("127.0.0.1:0", handler_from(router)).expect("bind");
    let addr = server.local_addr();
    thread::spawn(move || {
        let _ = server.run();
    });
    thread::sleep(Duration::from_millis(150));

    Harness { addr, read1, read2, read3, note, world, human }
}

#[test]
fn every_rib_converges_on_the_one_ledger_at_the_one_address() {
    let h = boot();

    // 1. ONE address, all three doors resolvable, gate armed.
    let reg = h.post(&WireRequest::new("http", h.read3.clone(), WireOp::Registry));
    assert!(reg.ok, "registry: {:?}", reg.error);
    assert_eq!(reg.data["doors"].as_array().map(|d| d.len()).unwrap_or(0), 3, "all three doors resolve at one address");
    assert_eq!(reg.data["default_snapshot"], "snap-genesis");
    assert!(reg.data["escalation_armed"].as_bool().unwrap_or(false));

    // 2. The rib: 200 writes through /v1/op (the data plane on the wire).
    let rib = WireRib::new(&h.addr, h.note.clone());
    let rig = rib.rig_write(STRANDS, PER_STRAND, "write:note", "rib/place");
    assert!(rig.all_ok(), "rib must commit 200/200 — failed {}", rig.failed);

    // 3. door3 spatial rib: one creative place + one escalated destroy.
    let place = h.post(&WireRequest::new("http", h.world.clone(), WireOp::Spatial {
        snapshot: String::new(),
        op: "write:world".into(),
        target: "place/m10-atrium".into(),
        payload: serde_json::json!({"name": "M10 Atrium", "content": "where the ribs meet"}),
    }));
    assert!(place.ok, "spatial place: {:?}", place.error);
    assert!(!place.data["escalated"].as_bool().unwrap());

    let mut destroy = WireRequest::new("http", h.world.clone(), WireOp::Spatial {
        snapshot: String::new(),
        op: "admin:destroy".into(),
        target: "place/m10-atrium".into(),
        payload: serde_json::json!({"reason": "convergence sweep"}),
    });
    assert!(!h.post(&destroy).ok, "single-token destroy stays denied");
    destroy.escalation = Some(h.human.clone());
    let esc = h.post(&destroy);
    assert!(esc.ok, "escalated destroy: {:?}", esc.error);
    assert!(esc.data["escalated"].as_bool().unwrap(), "double-triplet path confirmed at door3");

    // 4. CONVERGENCE — three read planes, one ledger.
    let witness = h.read(&h.read1);
    assert_eq!(witness as usize, AFTER, "door1 witness sees 202 nodes (one chain)");
    let structure = h.read(&h.read2);
    assert_eq!(structure as usize, AFTER, "door2 structural read converges on the same chain");

    let world_scene = h.post(&WireRequest::new("http", h.read3.clone(), WireOp::World { snapshot: String::new() }));
    assert!(world_scene.ok, "walk-in: {:?}", world_scene.error);
    assert_eq!(world_scene.data["walk_in_count"].as_u64().unwrap_or(0), AFTER as u64,
        "the rib's 200 writes walk in as PROVEN facts alongside the place+destroy");
    assert_eq!(world_scene.data["excluded"].as_u64().unwrap_or(1), 0,
        "no tampered node sneaks into the converging world");
    let facts = world_scene.data["world"]["facts"].as_array().unwrap();
    let proven = facts.iter().filter(|f| f["provenance"]["signature_ok"].as_bool().unwrap_or(false)).count();
    assert_eq!(proven, AFTER, "every walked-in fact carries a live signature check");

    // 5. the whole chain is ONE spine: prove a rib write, the place, the
    //    destroy — every CID reaches the same genesis at the same address.
    let place_cid = place.data["cid"].as_str().unwrap();
    let destroy_cid = esc.data["cid"].as_str().unwrap();
    for cid in [&rig.cids[0], &rig.cids[199], place_cid, destroy_cid] {
        let p = h.post(&WireRequest::new("http", h.read2.clone(), WireOp::Prove { cid: cid.to_string() }));
        assert!(p.ok, "prove {cid:?}: {:?}", p.error);
        assert!(p.data["verified"].as_bool().unwrap_or(false), "{cid:?} must prove to genesis");
    }

    // 6. the rib's own over-the-wire audit agrees at the same address.
    let audit = rib.audit_over_wire(&h.read1, &rig.cids);
    assert!(audit.clean, "rib audit clean over the converging wire");
}