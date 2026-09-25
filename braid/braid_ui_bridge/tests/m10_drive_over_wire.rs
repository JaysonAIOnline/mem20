//! m10 — the rib: braid_drive's workload, driven OVER the wire.
//!
//! m3 hammered the engine in-process (200 writes / 8 strands, audited
//! clean). m10 pulls that SAME data-plane out of the tool-plane and drives it
//! through a REAL wire: every write is `POST /v1/op` on the ONE listener, and
//! the audit m3 ran over the live ledger is re-run OVER the wire. This is the
//! "rip another rib" step — braid_drive becomes a wire data-plane, not a
//! library convenience:
//!   - 8 strands × 25 concurrent writes through real HTTP (no side channel)
//!   - every byte round-trips the braided-triplet path: snapshot+cap bound
//!     by the server, precommitment verified, CID echoed back
//!   - the m3 audit re-runs over the wire: every CID proves back to genesis,
//!     the registry resolves at the SAME address, health ticks
//!   - door1 witness reads back exactly what the rib wrote (same ledger)

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
name = "genesis-m10-rib"
version = 1

[[rules]]
allow = true
capability = "read:*:*"

[[rules]]
allow = true
capability = "write:note:*"

[[rules]]
allow = false
capability = "admin:*:*"
"#;

const STRANDS: usize = 8;
const PER_STRAND: usize = 25;
const TOTAL: usize = STRANDS * PER_STRAND;

fn mac(loc: &str, sk: &SigningKey, caps: &[&str]) -> SessionMacaroon {
    SessionMacaroon::issue(loc, &did_key(&VerifyingKey::from(sk)), caps, sk)
}

struct Harness {
    addr: String,
    read_token: SessionMacaroon,
    note_token: SessionMacaroon,
}

fn boot() -> Harness {
    use std::sync::atomic::{AtomicU64, Ordering};
    static SEQ: AtomicU64 = AtomicU64::new(0);
    let seq = SEQ.fetch_add(1, Ordering::Relaxed);
    let path = format!("/tmp/opencode/braid-m10-rib-{}-{seq}.jsonl", std::process::id());
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

    let router = Arc::new(Router::new(
        Arc::new(Mutex::new(engine)),
        vec![DoorRegistration { door: Door::Lumen, did: door_did, location: "door1".into() }],
        "snap-genesis",
    ));

    let read_token = mac("door1", &door_sk, &["read:*:*"]);
    let note_token = mac("door1", &door_sk, &["write:note:*"]);

    let server = BraidWireServer::new("127.0.0.1:0", handler_from(router)).expect("bind");
    let addr = server.local_addr();
    thread::spawn(move || {
        let _ = server.run();
    });
    thread::sleep(Duration::from_millis(150));

    Harness { addr, read_token, note_token }
}

#[test]
fn the_rib_drives_the_wire_and_audits_over_it() {
    let h = boot();
    let rib = WireRib::new(&h.addr, h.note_token.clone());

    // the rib: the m3 workload, but every write goes through /v1/op.
    let rig = rib.rig_write(STRANDS, PER_STRAND, "write:note", "rib/place");
    assert_eq!(rig.submitted, TOTAL, "exactly 200 writes submitted");
    assert!(rig.all_ok(), "200/200 must commit — failed {}", rig.failed);
    assert_eq!(rig.cids.len(), TOTAL, "every ok write echoes a CID");

    // the audit, OVER the wire: prove every CID back to genesis + health +
    // registry, all at the SAME address the rib wrote to.
    let audit = rib.audit_over_wire(&h.read_token, &rig.cids);
    assert_eq!(audit.node_count, TOTAL);
    assert!(audit.all_proven, "every rib CID proves over the wire");
    assert!(audit.healthy, "health ticks at the rib's own address");
    assert!(audit.registry_seen, "registry resolves at the rib's address");
    assert!(
        audit.clean,
        "the m10 rib audits clean over real HTTP: {}",
        serde_json::to_string(&audit).unwrap_or_default()
    );
    for proof in &audit.per_cid {
        assert!(
            proof.verified,
            "spine for {} must reach genesis",
            &proof.cid[..10.min(proof.cid.len())]
        );
    }

    // door1 witness reads back EXACTLY what the rib wrote — same ledger,
    // same address, no side channel.
    let req = WireRequest::new("http", h.read_token.clone(), WireOp::Read {
        snapshot: String::new(),
        op_filter: None,
    });
    let body = serde_json::to_string(&req).unwrap();
    let r = http_post_raw(&h.addr, "/v1/op", &body).unwrap_or_else(braid_wire::WireResponse::err);
    assert!(r.ok, "witness read must not fail: {:?}", r.error);
    let count = r.data["count"].as_u64().unwrap_or(0);
    assert_eq!(count as usize, TOTAL, "door1 witness sees the rib's 200 nodes");
}