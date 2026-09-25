//! m7 — door1 nav SHELL, live: every door1 surface under ONE base URL.
//!
//! The ONE bridge now serves the door1 nav shell: witness (door1), structure
//! (door2), state, forge and the surface directory (live + planned) all under
//! one base URL. The page is keyless; every token lives on the bridge. The
//! same wire still posts to /v1/op and still servers the door3 walk-in at
//! /walk-in — one ledger, three doors, one bridge.
//!
//! Run: cargo run -p braid_ui_bridge --example door1_nav_shell

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
name = "genesis-nav"
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

const PORT: &str = "127.0.0.1:8089";

fn mac(loc: &str, sk: &SigningKey, caps: &[&str]) -> SessionMacaroon {
    SessionMacaroon::issue(loc, &did_key(&VerifyingKey::from(sk)), caps, sk)
}

fn main() {
    let path = format!("/tmp/opencode/braid-m7-nav-example-{}.jsonl", std::process::id());
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

    // THREE doors on ONE router: door1 Lumen (witness), door2 Axiom
    // (structure), door3 Mem (walk-in).
    let router = Arc::new(Router::new(
        Arc::new(Mutex::new(engine)),
        vec![
            DoorRegistration { door: Door::Lumen, did: door_did.clone(), location: "door1".into() },
            DoorRegistration { door: Door::Axiom, did: door_did.clone(), location: "door2".into() },
            DoorRegistration { door: Door::Mem, did: door_did, location: "door3".into() },
        ],
        "snap-genesis",
    ));

    let handler = handler_from(router.clone());
    let witness_token = mac("door1", &door_sk, &["read:*:*"]);
    let structure_token = mac("door2", &door_sk, &["read:*:*"]);
    let forge_token = mac("door1", &door_sk, &["write:note:*"]);
    let read_token = mac("door3", &door_sk, &["read:*:*"]);
    let write_token = mac("door3", &door_sk, &["write:note:*"]);

    // LIVE surfaces the bridge already serves (D1.4: no rewrites) + planned
    // surfaces whose nav slots exist (D1.5) but nothing is mounted yet.
    let shell = door1_shell(
        witness_token,
        structure_token,
        forge_token,
        vec![
            Door1Surface { name: "dashboard", url: "/health" },
            Door1Surface { name: "pull-order", url: "/health" },
            Door1Surface { name: "arena", url: "" },
            Door1Surface { name: "tool-policy-console", url: "" },
            Door1Surface { name: "plugin-workspace", url: "" },
            Door1Surface { name: "ipam", url: "" },
        ],
    )
    .page("/walk-in", include_str!("../assets/walk_in.html"))
    .world_token(read_token);

    let server = BraidWireServer::new(PORT, handler)
        .expect("bind 8089")
        .with_shell(shell);
    thread::spawn(move || {
        let _ = server.run();
    });
    thread::sleep(Duration::from_millis(150));

    let post = |req: &WireRequest| {
        let body = serde_json::to_string(req).unwrap();
        http_post_raw(PORT, "/v1/op", &body).unwrap_or_else(braid_wire::WireResponse::err)
    };

    for name in ["first-note", "second-note"].iter() {
        let write = WireRequest::new("http", write_token.clone(), WireOp::Write {
            snapshot: String::new(),
            op: "write:note".into(),
            target: format!("note/{name}"),
            payload: serde_json::json!({"content": format!("a grounded note named {name}")}),
        });
        assert!(post(&write).ok, "seed write failed");
    }

    // prove every door1 surface over real HTTP, in the terminal
    let get = |path: &str| {
        let (status, raw) = http_get_raw(PORT, path).expect("GET");
        let body = raw.split("\r\n\r\n").nth(1).unwrap_or("");
        let resp: braid_wire::WireResponse =
            serde_json::from_str(body).unwrap_or_else(|_| braid_wire::WireResponse::err("not json"));
        (status, resp)
    };

    let (page_status, _page) = http_get_raw(PORT, "/").expect("GET /");
    assert_eq!(page_status, 200);
    let (_s, witness) = get("/witness");
    let (_s, structure) = get("/structure");
    let (_s, state) = get("/state");
    let (_s, manifest) = get("/manifest");
    let (_s, walkin) = get("/walk-in");
    assert!(witness.ok && structure.ok && state.ok && manifest.ok);
    assert!(walkin.ok, "walk-in still served: {:?}", walkin.error);

    let forged = http_post_raw(
        PORT,
        "/forge",
        &serde_json::json!({ "target": "note/from-live-nav", "content": "forged live from the door1 shell" }).to_string(),
    )
    .expect("POST /forge");
    assert!(forged.ok, "forge failed: {:?}", forged.error);

    let surfaces = manifest.data["surfaces"].as_array().unwrap();
    let planned: Vec<_> = surfaces.iter().filter(|s| s["planned"].as_bool().unwrap_or(false)).collect();
    let live: usize = surfaces.iter().filter(|s| !s["planned"].as_bool().unwrap_or(false)).count();

    println!(
        "m7 GREEN — door1 nav shell served by the ONE bridge\n  \
         base     : http://{PORT}/  (keyless; open in a browser)\n  \
         witness  : {} nodes (door1 Lumen)\n  \
         structure: door2 Axiom, spine reaches genesis ({} hops)\n  \
         state    : {}\n  \
         forge    : wrote cid {} over the SAME wire\n  \
         manifest : {} live surface(s) + {} planned surface(s)\n  \
         walk-in  : served at /walk-in (door3, unchanged from m6)\n  \
         wire     : POST /v1/op unchanged — every door, one surface.",
        witness.data["view"]["timeline"].as_array().unwrap().len(),
        structure.data["view"]["spine_to_genesis"].as_array().unwrap().len(),
        state.data["status"].as_str().unwrap_or("?"),
        forged.data["cid"].as_str().unwrap_or("?").chars().take(16).collect::<String>(),
        live,
        planned.len(),
    );

    loop {
        thread::sleep(Duration::from_secs(3600));
    }
}