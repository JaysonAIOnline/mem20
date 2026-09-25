//! m5 — door3 quest3d live over the wire: world-state to spatial nodes.
//!
//! A `WireOp::World` request goes through the SAME frontdoor router as every
//! other op (one read authority, one cap gate). The response is a spatial
//! WorldScene where every fact ships its ledger provenance, plus the
//! resonance window and ledger-derived presence. This test walks the whole
//! door3 path: write grounded facts on door3, then ask the WORLD.

use std::sync::{Arc, Mutex};

use braid_core::crypto::new_signing_key;
use braid_core::engine::BraidEngine;
use braid_core::policy::{policy_from_toml, PolicySnapshot};
use braid_keys::{did_key, SessionMacaroon};
use braid_ui_bridge::frontdoor::{Door, DoorRegistration, Router};
use braid_ui_bridge::handler_from;
use braid_wire::{WireOp, WireRequest};
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

fn boot() -> (Arc<Mutex<BraidEngine>>, String) {
    use std::sync::atomic::{AtomicU64, Ordering};
    static SEQ: AtomicU64 = AtomicU64::new(0);
    let seq = SEQ.fetch_add(1, Ordering::Relaxed);
    let path = format!("/tmp/opencode/braid-m5-{}-{seq}.jsonl", std::process::id());
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
        signer: engine_id.clone(),
        signature: String::new(),
        policy: policy_from_toml(ESCALATION).expect("escalation"),
    });
    (Arc::new(Mutex::new(engine)), engine_id)
}

fn mac(location: &str, sk: &SigningKey, caps: &[&str]) -> SessionMacaroon {
    SessionMacaroon::issue(location, &did_key(&VerifyingKey::from(sk)), caps, sk)
}

#[test]
fn world_returns_spatial_walk_in_over_one_real_wire() {
    let (engine, _engine_id) = boot();
    let door_sk = SigningKey::generate(&mut OsRng);
    let human_sk = SigningKey::generate(&mut OsRng);
    let door_did = did_key(&VerifyingKey::from(&door_sk));
    let human_did = did_key(&VerifyingKey::from(&human_sk));
    let router = Router::new(
        engine.clone(),
        vec![DoorRegistration { door: Door::Mem, did: door_did, location: "door3".into() }],
        "snap-genesis",
    )
    .with_escalation(human_did, "snap-escalation");
    let handler = handler_from(Arc::new(router));
    // One door, two scopes (one-directional grants: a write cap cannot also
    // grant read). The write scope seeds the ledger; the read scope asks the
    // WORLD — pinning both to the same door key so the door stays one native.
    let write_token = mac("door3", &door_sk, &["write:note:*"]);
    let read_token = mac("door3", &door_sk, &["read:*:*"]);

    // seed groundwork over the wire, through the frontdoor
    for (name, room) in [("stone-garden", 0), ("tide-archive", 1), ("glass-bridge", 2)] {
        let req = WireRequest::new(
            "http",
            write_token.clone(),
            WireOp::Write {
                snapshot: "snap-genesis".into(),
                op: "write:note".into(),
                target: format!("place/{name}"),
                payload: serde_json::json!({"name": name, "room": room, "content": format!("a grounded room named {name}")}),
            },
        );
        let resp = handler(req);
        assert!(resp.ok, "seed write failed: {:?}", resp.error);
    }

    // decommission one room under the ESCALATED path — the era marker for
    // presence (a two-token write).
    let esc = mac("human-escalation", &human_sk, &["admin:destroy:*"]);
    let esc_req = WireRequest {
        version: "braid/1".into(),
        transport: "http".into(),
        macaroon: write_token.clone(),
        escalation: Some(esc),
        op: WireOp::Write {
            snapshot: "snap-genesis".into(),
            op: "admin:destroy".into(),
            target: "place/tide-archive".into(),
            payload: serde_json::json!({"reason": "decommissioned by gate"}),
        },
    };
    let esc_resp = handler(esc_req);
    assert!(esc_resp.ok, "escalated destroy failed: {:?}", esc_resp.error);

    // ask the WORLD — pure spatial walk-in over the same wire
    let world_req = WireRequest::new(
        "http",
        read_token,
        WireOp::World { snapshot: "snap-genesis".into() },
    );
    let world = handler(world_req);
    assert!(world.ok, "world failed: {:?}", world.error);

    let data = world.data.as_object().unwrap();
    assert_eq!(data["kind"], "world");
    assert_eq!(data["walk_in_count"].as_u64().unwrap(), 4, "4 proven facts walk in");

    // every world fact is PROVEN (signature_ok) and carries ledger provenance
    let scene = data["world"]["facts"].as_array().unwrap();
    assert_eq!(scene.len(), 4);
    for f in scene {
        assert!(f["provenance"]["signature_ok"].as_bool().unwrap(), "fact must be proven");
        let cid = f["provenance"]["cid"].as_str().unwrap();
        assert!(engine.lock().unwrap().log.get(cid).is_some(), "provenance cid exists in ledger");
        // primary snapshot is either genesis (normal writes) or the escalation
        // snapshot (two-token writes) — both are registered and signed.
        let snap = f["provenance"]["snapshot"].as_str().unwrap();
        assert!(snap == "snap-genesis" || snap == "snap-escalation", "snapshot is registered: {snap}");
        assert_eq!(f["position"].as_array().unwrap().len(), 3, "spatial position");
    }

    // window threads the braid spine (4 echoes), presence counts the authority
    let echoes = data["window"]["echoes"].as_array().unwrap();
    assert_eq!(echoes.len(), 4);
    assert!(echoes.iter().enumerate().skip(1).all(|(i, e)| {
        e["resonates_from"].as_str() == echoes[i - 1]["cid"].as_str()
    }), "each echo resonates from the previous braid node");
    let presence = data["presence"]["agents"].as_array().unwrap();
    assert_eq!(presence.len(), 1);
    assert_eq!(presence[0]["node_count"].as_u64().unwrap(), 4);
    assert_eq!(presence[0]["escalated_ops"].as_u64().unwrap(), 1);

    // excluded must be 0 — the ledger is untouched, nothing got bounced
    assert_eq!(data["excluded"].as_u64().unwrap(), 0);
    // the engine really committed 4 nodes — the wire world matches the ledger
    let ledger_depth = engine.lock().unwrap().head().map(|h| h.depth).unwrap();
    assert_eq!(ledger_depth, 3);
}

#[test]
fn world_is_cap_gated_and_respects_engine_facts() {
    let (engine, _engine_id) = boot();
    let door_sk = SigningKey::generate(&mut OsRng);
    let door_did = did_key(&VerifyingKey::from(&door_sk));
    let router = Router::new(
        engine.clone(),
        vec![DoorRegistration { door: Door::Mem, did: door_did, location: "door3".into() }],
        "snap-genesis",
    );
    let handler = handler_from(Arc::new(router));

    // a writer token WITHOUT read cannot ask the world
    let writer_only = mac("door3", &door_sk, &["write:note:*"]);
    let req = WireRequest::new("http", writer_only, WireOp::World { snapshot: "snap-genesis".into() });
    let resp = handler(req);
    assert!(!resp.ok, "read-gated: writer-only token must be denied the world");
    assert!(resp.error.as_deref().unwrap().contains("does not grant read"));
}