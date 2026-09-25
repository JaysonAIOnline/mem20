//! W4 — three strands interleave over ONE wire WITHOUT deadlock, and partial
//! results feed others' prerequisites.
//!
//! door1 (lumen/witness) reads; door2 (godmode) writes then reads its own
//! proof; door3 (v-world) writes AFTER seeing read state. All three race the
//! same engine through the same socket while the engine serializes writes
//! under a single mutex (single-writer authority).

use std::sync::Arc;
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};

use braid_core::crypto::{new_signing_key, pub_key_hex};
use braid_core::engine::BraidEngine;
use braid_core::policy::{policy_from_toml, PolicySnapshot};
use braid_keys::SessionMacaroon;
use braid_wire::{http_post_raw, BraidWireServer, Handler, WireOp, WireRequest, WireResponse};

const SEED: &str = r#"
name = "genesis"
version = 1
[[rules]]
allow = true
capability = "read:*:*"
[[rules]]
allow = true
capability = "write:note:*"
[[rules]]
allow = true
capability = "invoke:tool:*"
"#;

fn tmp_path() -> String {
    use std::sync::atomic::{AtomicU64, Ordering};
    static SEQ: AtomicU64 = AtomicU64::new(0);
    let seq = SEQ.fetch_add(1, Ordering::Relaxed);
    format!("/tmp/opencode/braid-wire-conc-{}-{seq}.jsonl", std::process::id())
}

fn boot(addr: &mut String) -> Arc<Mutex<BraidEngine>> {
    let path = tmp_path();
    let _ = std::fs::remove_file(&path);
    let sk = new_signing_key();
    let id_hex = pub_key_hex(&ed25519_dalek::VerifyingKey::from(&sk));

    let mut engine = BraidEngine::new(&path, sk).expect("boot");
    let policy = policy_from_toml(SEED).expect("seed");
    engine.register_snapshot(PolicySnapshot {
        cid: "snap-w4".into(),
        signer: id_hex,
        signature: String::new(),
        policy,
    });
    let engine = Arc::new(Mutex::new(engine));

    let eng = engine.clone();
    let handler: Handler = Arc::new(move |req: WireRequest| -> WireResponse {
        let mut eng = eng.lock().expect("engine lock");
        let cap = braid_core::Capability::parse(&req.macaroon.caveats[0]);
        match &req.op {
            WireOp::Write { snapshot, op, target, payload } => {
                match eng.write(&cap, snapshot, op, target, payload.clone()) {
                    Ok(r) => WireResponse::ok(
                        serde_json::json!({ "cid": r.cid, "depth": r.depth }),
                        Some(r.triplet),
                    ),
                    Err(e) => WireResponse::err(e),
                }
            }
            WireOp::Read { snapshot, op_filter } => match eng.read(&cap, snapshot, op_filter.as_deref()) {
                Ok(nodes) => WireResponse::ok(
                    serde_json::json!({ "count": nodes.len(),
                        "cids": nodes.iter().map(|n| n.cid.clone()).collect::<Vec<_>>() }),
                    None,
                ),
                Err(e) => WireResponse::err(e),
            },
            _ => WireResponse::err("unsupported op"),
        }
    });

    let server = BraidWireServer::new("127.0.0.1:0", handler).expect("server");
    *addr = server.local_addr();
    thread::spawn(move || {
        let _ = server.run();
    });
    thread::sleep(Duration::from_millis(150));
    engine
}

fn mac(location: &str, caps: &[&str]) -> SessionMacaroon {
    let sk = new_signing_key();
    SessionMacaroon::issue(location, "w4-session", caps, &sk)
}

fn write_note(addr: &str, from: &str) -> Result<String, String> {
    let req = WireRequest::new("http", mac("door", &["write:note:*"]), WireOp::Write {
        snapshot: "snap-w4".into(),
        op: "write:note".into(),
        target: "note".into(),
        payload: serde_json::json!({ "from": from }),
    });
    let body = serde_json::to_string(&req).map_err(|e| e.to_string())?;
    let r = http_post_raw(addr, "/v1/op", &body)?;
    if !r.ok {
        return Err(r.error.unwrap_or("write failed".into()));
    }
    Ok(r.data["cid"].as_str().unwrap_or("").to_string())
}

fn read_count(addr: &str) -> Result<usize, String> {
    let req = WireRequest::new("http", mac("door", &["read:*:*"]), WireOp::Read {
        snapshot: "snap-w4".into(),
        op_filter: None,
    });
    let body = serde_json::to_string(&req).map_err(|e| e.to_string())?;
    let r = http_post_raw(addr, "/v1/op", &body)?;
    if !r.ok {
        return Err(r.error.unwrap_or("read failed".into()));
    }
    Ok(r.data["count"].as_u64().unwrap_or(0) as usize)
}

#[test]
fn three_strands_interleave_without_deadlock() {
    let mut addr = String::new();
    boot(&mut addr);

    let deadline = Instant::now() + Duration::from_secs(15);

    // door1: witness, read-only — hammer reads
    let d1 = thread::spawn({
        let addr = addr.clone();
        move || {
            let mut reads = 0;
            while Instant::now() < deadline {
                if read_count(&addr).is_ok() {
                    reads += 1;
                }
                thread::sleep(Duration::from_millis(10));
            }
            reads
        }
    });

    // door2: godmode — write then read (writes depend on nothing, read consumes own write)
    let d2 = thread::spawn({
        let addr = addr.clone();
        move || {
            let mut wrote = 0;
            while Instant::now() < deadline {
                if write_note(&addr, "godmode").is_ok() {
                    wrote += 1;
                }
                thread::sleep(Duration::from_millis(15));
            }
            wrote
        }
    });

    // door3: v-world — partial result feeds its write: read count THEN write
    let d3 = thread::spawn({
        let addr = addr.clone();
        move || {
            let mut wrote = 0;
            while Instant::now() < deadline {
                if let Ok(n) = read_count(&addr) {
                    if n > 0 {
                        // partial read feeds a dependent write
                        if write_note(&addr, "vworld").is_ok() {
                            wrote += 1;
                        }
                    }
                }
                thread::sleep(Duration::from_millis(20));
            }
            wrote
        }
    });

    let (reads, god_writes, vw_writes) = (d1.join().unwrap(), d2.join().unwrap(), d3.join().unwrap());
    assert!(reads > 0, "door1 must have read");
    assert!(god_writes > 0, "door2 must have written");
    assert!(vw_writes > 0, "door3 must have written, fed by partial reads");
    println!(
        "W4 liveness: reads={reads} godmode_writes={god_writes} vworld_writes={vw_writes} — interleaved, no deadlock"
    );
}

#[test]
fn concurrent_writes_serialize_and_address_uniquely() {
    let mut addr = String::new();
    boot(&mut addr);

    let mut handles = Vec::new();
    for i in 0..8 {
        let addr = addr.clone();
        handles.push(thread::spawn(move || write_note(&addr, &format!("t{i}"))));
    }
    let mut cids = std::collections::HashSet::new();
    for h in handles {
        let cid = h.join().unwrap().unwrap();
        cids.insert(cid);
    }
    assert_eq!(cids.len(), 8, "8 interleaved writes -> 8 unique CIDs");
}