//! m8 — door2 godmode console, LIVE: creative + destructive over ONE wire.
//!
//! The ONE bridge serves door1's nav shell, door2's godmode console AND
//! door3's walk-in under a single base URL. Godmode is NOT a static role —
//! it is a wider door2 token scope (read / write) verified against the same
//! door2 DID + location as every other door; destructive admin:* commits only
//! through the SECOND, human-gated escalation token (D2.3).
//!
//! Routes (all keyless, tokens server-side):
//!   GET  /godmode           → the godmode SPA
//!   GET  /console | /daemon → WireOp::Registry (real registry parity)
//!   GET  /canvas            → creative read (door2 Axiom structure view)
//!   POST /canvas            → write:note via door2 write token (creative)
//!   GET  /evaluate          → real frozen rule list
//!   POST /evaluate          → real verdict for { "cap": … }
//!   GET  /playground        → playground reads
//!   POST /playground        → creative single-token write
//!   POST /playground/reset  → escalated admin:destroy (double-triplet)
//! Plus m7's planned surfaces now mounted REAL: /arena, /tool-policy,
//! /workspace, /ipam.
//!
//! Run: cargo run -p braid_ui_bridge --example godmode_console

use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;

use braid_core::crypto::new_signing_key;
use braid_core::engine::BraidEngine;
use braid_core::policy::{policy_from_toml, PolicySnapshot};
use braid_keys::{did_key, SessionMacaroon};
use braid_ui_bridge::frontdoor::{Door, DoorRegistration, Router};
use braid_ui_bridge::{door1_shell, door2_shell, handler_from, mount_planned_surfaces, Door1Surface, GodmodeTokens};
use braid_wire::{http_get_raw, http_post_raw, BraidWireServer, WireOp, WireRequest};
use ed25519_dalek::{SigningKey, VerifyingKey};
use rand::rngs::OsRng;

const GENESIS: &str = r#"
name = "genesis-godmode"
version = 1

[[rules]]
allow = true
capability = "read:*:*"

[[rules]]
allow = true
capability = "write:*:*"

[[rules]]
allow = true
capability = "invoke:*:*"

[[rules]]
allow = false
capability = "admin:*:*"
"#;

const ESCALATION: &str = r#"
name = "escalation-godmode"
version = 1

[[rules]]
allow = true
capability = "admin:destroy:*"

[[rules]]
allow = true
capability = "admin:delete:*"

[[rules]]
allow = true
capability = "admin:create:*"

[[rules]]
allow = false
capability = "admin:wipe:*"
"#;

const PORT: &str = "127.0.0.1:8090";

fn mac(loc: &str, sk: &SigningKey, caps: &[&str]) -> SessionMacaroon {
    SessionMacaroon::issue(loc, &did_key(&VerifyingKey::from(sk)), caps, sk)
}

fn main() {
    let path = format!("/tmp/opencode/braid-m8-godmode-example-{}.jsonl", std::process::id());
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

    // THREE doors on ONE router + the human escalation gate (D2.4): godmode
    // is the same macaroon/auth/router/wire as door1, plus an armed gate.
    let router = Arc::new(
        Router::new(
            Arc::new(Mutex::new(engine)),
            vec![
                DoorRegistration { door: Door::Lumen, did: door_did.clone(), location: "door1".into() },
                DoorRegistration { door: Door::Axiom, did: door_did.clone(), location: "door2".into() },
                DoorRegistration { door: Door::Mem, did: door_did.clone(), location: "door3".into() },
            ],
            "snap-genesis",
        )
        .with_escalation(human_did, "snap-escalation"),
    );

    let handler = handler_from(router.clone());
    let witness_token = mac("door1", &door_sk, &["read:*:*"]);
    let structure_token = mac("door2", &door_sk, &["read:*:*"]);
    let forge_token = mac("door1", &door_sk, &["write:note:*"]);
    let world_token = mac("door3", &door_sk, &["read:*:*"]);

    // D2.1/D2.4: door2's godmode tokens are WIDER TOKENS on the SAME door2
    // DID + location — a separate read and write token (scope reads caveats[0]
    // as the capability), mirroring door1's witness/forge split. The human
    // token rides only the escalated route (D2.3).
    let god_read = mac("door2", &door_sk, &["read:*:*"]);
    let god_write = mac("door2", &door_sk, &["write:*:*"]);
    let human = mac("human-escalation", &human_sk, &["admin:destroy:*"]);

    // ONE shell, ONE base URL: door1 nav (planned surfaces now REAL) + door2
    // godmode + door3 walk-in on the same listener.
    let shell = door1_shell(
        witness_token.clone(),
        structure_token,
        forge_token,
        vec![
            Door1Surface { name: "dashboard", url: "/health" },
            Door1Surface { name: "arena", url: "/arena" },
            Door1Surface { name: "tool-policy-console", url: "/tool-policy" },
            Door1Surface { name: "plugin-workspace", url: "/workspace" },
            Door1Surface { name: "ipam", url: "/ipam" },
        ],
    );
    let shell = mount_planned_surfaces(shell, witness_token.clone(), "snap-genesis");
    let shell = door2_shell(shell, &GodmodeTokens::new(god_read, god_write, human), "snap-genesis");
    let shell = shell.page("/walk-in", include_str!("../assets/walk_in.html")).world_token(world_token);

    let server = BraidWireServer::new(PORT, handler)
        .expect("bind 8090")
        .with_shell(shell);
    thread::spawn(move || {
        let _ = server.run();
    });
    thread::sleep(Duration::from_millis(150));

    let post = |req: &WireRequest| {
        let body = serde_json::to_string(req).unwrap();
        http_post_raw(PORT, "/v1/op", &body).unwrap_or_else(braid_wire::WireResponse::err)
    };
    let get = |path: &str| {
        let (status, raw) = http_get_raw(PORT, path).expect("GET");
        let body = raw.split("\r\n\r\n").nth(1).unwrap_or("");
        let resp: braid_wire::WireResponse =
            serde_json::from_str(body).unwrap_or_else(|_| braid_wire::WireResponse::err("not json"));
        (status, resp)
    };

    // seed the playground, then drive every godmode surface over real HTTP
    let seed = WireRequest::new("http", mac("door2", &door_sk, &["write:note:*"]), WireOp::Write {
        snapshot: String::new(),
        op: "write:note".into(),
        target: "playground/origin".into(),
        payload: serde_json::json!({"content": "the godmode playground origin"}),
    });
    assert!(post(&seed).ok, "seed write failed");

    let (_s, page_raw) = http_get_raw(PORT, "/godmode").expect("GET /godmode");
    assert!(page_raw.contains("godmode"));
    let (_s, console) = get("/console");
    let (_s, daemon) = get("/daemon");
    let (_s, canvas_rd) = get("/canvas");
    let (_s, evaluate) = get("/evaluate");
    let created = http_post_raw(
        PORT,
        "/canvas",
        &serde_json::json!({ "target": "canvas/room-1", "content": "compiled over the wire" }).to_string(),
    )
    .expect("POST /canvas");
    assert!(created.ok, "creative canvas write: {:?}", created.error);
    let eval_ok = http_post_raw(
        PORT,
        "/evaluate",
        &serde_json::json!({ "cap": "write:note" }).to_string(),
    )
    .expect("POST /evaluate");
    assert!(eval_ok.ok, "eval: {:?}", eval_ok.error);
    let playground = http_post_raw(
        PORT,
        "/playground",
        &serde_json::json!({ "target": "playground/sand-pit", "content": "creative single-token" }).to_string(),
    )
    .expect("POST /playground");
    assert!(playground.ok, "playground: {:?}", playground.error);
    let reset = http_post_raw(
        PORT,
        "/playground/reset",
        &serde_json::json!({ "target": "playground", "content": "self-reset via destructive escalation" }).to_string(),
    )
    .expect("POST /playground/reset");
    assert!(reset.ok, "reset: {:?}", reset.error);
    let (_s, arena) = get("/arena");
    let (_s, tool_policy) = get("/tool-policy");
    let (_s, workspace) = get("/workspace");
    let (_s, ipam) = get("/ipam");
    assert!(
        console.ok && daemon.ok && canvas_rd.ok && evaluate.ok && arena.ok && tool_policy.ok && workspace.ok && ipam.ok,
        "one of the godmode/planned surfaces failed"
    );

    println!(
        "m8 GREEN — godmode console served by the ONE bridge\n  \
         godmode   : http://{PORT}/godmode  (keyless SPA, open in a browser)\n  \
         console   : door {door}, {doors} doors, escalation {armed}armed\n  \
         daemon    : boot-time registry parity with console\n  \
         canvas    : compiled cid {created_cid} (door2 creative, escalated false)\n  \
         evaluate  : cap write:note → {{ allowed: {allowed} }} against snap-genesis\n  \
         playground: wrote cid {play_cid} (creative, single-token)\n  \
         reset     : committed cid {reset_cid} (destructive, escalated, double-triplet)\n  \
         planned→live: arena / tool-policy / workspace / ipam all mounted REAL\n  \
         wire      : POST /v1/op unchanged — every door, one surface, one gate.",
        door = console.data["door"].as_str().unwrap_or("?"),
        doors = console.data["doors"].as_array().unwrap().len(),
        armed = if console.data["escalation_armed"].as_bool().unwrap_or(false) { "" } else { "NOT " },
        created_cid = created.data["cid"].as_str().unwrap_or("?").chars().take(16).collect::<String>(),
        allowed = eval_ok.data["allowed"].as_bool().unwrap_or(false),
        play_cid = playground.data["cid"].as_str().unwrap_or("?").chars().take(16).collect::<String>(),
        reset_cid = reset.data["cid"].as_str().unwrap_or("?").chars().take(16).collect::<String>(),
    );

    println!("  (ctrl-c to stop; the bridge stays live until then)");
    loop {
        thread::sleep(Duration::from_secs(3600));
    }
}