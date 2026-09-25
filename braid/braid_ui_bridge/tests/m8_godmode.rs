//! m8 — door2 godmode acceptance: creative + destructive over the SAME wire.
//!
//! Real engine + real router (THREE registered doors) + real wire server.
//! The godmode surfaces ride the same ONE bridge/base as door1 (nav) and
//! door3 (walk-in), all on one listener:
//!   GET  /godmode         → the godmode SPA (keyless)
//!   GET  /console         → WireOp::Registry (control-center parity)
//!   GET  /daemon          → WireOp::Registry (boot-time server info)
//!   GET  /canvas          → creative read (door2)
//!   POST /canvas          → creative `write:note` (door2 write token)
//!   GET  /evaluate        → real frozen policy rule list
//!   POST /evaluate        → real verdict for a capability
//!   GET  /playground      → creative reads
//!   POST /playground      → creative single-token write
//!   POST /playground/reset → escalated admin:destroy (double-token, D2.3)
//! D2.1/D2.4: the door2 tokens verify against the SAME DID+location as every
//! other door — no static role, no second auth island.
//!
//! m7's "planned" door1 surfaces (arena, tool-policy-console,
//! plugin-workspace, ipam) are mounted as REAL routes on the same base.

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

fn mac(loc: &str, sk: &SigningKey, caps: &[&str]) -> SessionMacaroon {
    SessionMacaroon::issue(loc, &did_key(&VerifyingKey::from(sk)), caps, sk)
}

struct Harness {
    addr: String,
    door2_write: SessionMacaroon,
    human: SessionMacaroon,
}

fn boot(escalation_armed: bool) -> Harness {
    use std::sync::atomic::{AtomicU64, Ordering};
    static SEQ: AtomicU64 = AtomicU64::new(0);
    let seq = SEQ.fetch_add(1, Ordering::Relaxed);
    let path = format!("/tmp/opencode/braid-m8-godmode-{}-{seq}.jsonl", std::process::id());
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

    let mut router = Router::new(
        Arc::new(Mutex::new(engine)),
        vec![
            DoorRegistration { door: Door::Lumen, did: door_did.clone(), location: "door1".into() },
            DoorRegistration { door: Door::Axiom, did: door_did.clone(), location: "door2".into() },
            DoorRegistration { door: Door::Mem, did: door_did.clone(), location: "door3".into() },
        ],
        "snap-genesis",
    );
    if escalation_armed {
        router = router.with_escalation(human_did, "snap-escalation");
    }

    let handler = handler_from(Arc::new(router));
    let witness_token = mac("door1", &door_sk, &["read:*:*"]);
    let structure_token = mac("door2", &door_sk, &["read:*:*"]);
    let forge_token = mac("door1", &door_sk, &["write:note:*"]);
    let world_token = mac("door3", &door_sk, &["read:*:*"]);

    // D2.1/D2.4: the door2 godm mode tokens are WIDER TOKENS on the SAME
    // door2 DID + location. Separate read + write tokens (scope reads
    // caveats[0] as the capability), like door1's witness/forge split.
    let god_read = mac("door2", &door_sk, &["read:*:*"]);
    let god_write = mac("door2", &door_sk, &["write:*:*"]);
    let human = mac("human-escalation", &human_sk, &["admin:destroy:*"]);

    // ONE shell, ONE base: door1 nav (planned surfaces now live) + door2
    // godmode + door3 walk-in on the SAME listener.
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
    let shell = door2_shell(shell, &GodmodeTokens::new(god_read, god_write.clone(), human.clone()), "snap-genesis");
    let shell = shell.page("/walk-in", include_str!("../assets/walk_in.html")).world_token(world_token);

    let server = BraidWireServer::new("127.0.0.1:0", handler)
        .expect("bind")
        .with_shell(shell);
    let addr = server.local_addr();
    thread::spawn(move || {
        let _ = server.run();
    });
    thread::sleep(Duration::from_millis(150));

    Harness { addr, door2_write: god_write, human }
}

impl Harness {
    fn post(&self, req: &WireRequest) -> braid_wire::WireResponse {
        let body = serde_json::to_string(req).unwrap();
        http_post_raw(&self.addr, "/v1/op", &body).unwrap_or_else(braid_wire::WireResponse::err)
    }

    fn get(&self, path: &str) -> (u16, braid_wire::WireResponse) {
        let (status, raw) = http_get_raw(&self.addr, path).unwrap();
        let body = raw.split("\r\n\r\n").nth(1).unwrap_or("");
        let resp = if body.trim().is_empty() {
            braid_wire::WireResponse::err("empty body")
        } else {
            serde_json::from_str(body).unwrap_or_else(|_| braid_wire::WireResponse::err("not json"))
        };
        (status, resp)
    }
}

#[test]
fn godmode_console_canvas_evaluate_daemon_playground_over_one_wire() {
    let h = boot(true);

    // GET /godmode → the keyless godmode SPA (no secret in the page)
    let (status, raw) = http_get_raw(&h.addr, "/godmode").expect("get /godmode");
    assert_eq!(status, 200);
    assert!(raw.to_lowercase().contains("text/html"));
    assert!(raw.contains("godmode"));
    assert!(!raw.contains("macaroon"), "the page holds no session secret");

    // GET /console → REGISTRY (control-center parity): 3 doors, gate armed.
    let (status, resp) = h.get("/console");
    assert_eq!(status, 200);
    assert!(resp.ok, "console error: {:?}", resp.error);
    assert_eq!(resp.data["door"], "door2", "console is a door2 surface");
    let doors = resp.data["doors"].as_array().unwrap();
    assert_eq!(doors.len(), 3, "three registered doors");
    assert_eq!(doors[0]["door"], "door1");
    assert_eq!(doors[1]["door"], "door2");
    assert_eq!(doors[2]["door"], "door3");
    assert_eq!(resp.data["default_snapshot"], "snap-genesis");
    assert_eq!(resp.data["escalation_armed"], true);

    // GET /daemon → the same real registry, boot-time info shape.
    let (status, resp) = h.get("/daemon");
    assert_eq!(status, 200);
    assert!(resp.ok, "daemon error: {:?}", resp.error);
    assert_eq!(resp.data["door"], "door2");
    assert_eq!(resp.data["escalation_armed"], true);

    // GET /canvas → creative read through door2 (Axiom structure view).
    let (status, resp) = h.get("/canvas");
    assert_eq!(status, 200);
    assert!(resp.ok, "canvas read error: {:?}", resp.error);
    assert_eq!(resp.data["door"], "door2");
    assert_eq!(resp.data["view"]["kind"], "structure");

    let seed = h.post(&WireRequest::new("http", h.door2_write.clone(), WireOp::Write {
        snapshot: String::new(),
        op: "write:note".into(),
        target: "canvas/base-seed".into(),
        payload: serde_json::json!({"content": "seeded on the canvas"}),
    }));
    assert!(seed.ok, "canvas seed write: {:?}", seed.error);

    // POST /canvas → creative write (single door2 token). escalated=false.
    let body = serde_json::json!({ "target": "canvas/room-1", "content": "compiled over the wire" });
    let r = http_post_raw(&h.addr, "/canvas", &body.to_string()).expect("post /canvas");
    assert!(r.ok, "creative canvas write: {:?}", r.error);
    assert_eq!(r.data["door"], "door2", "canvas writes ride the door2 identity");
    assert_eq!(r.data["escalated"], false, "creative op is not escalated");
    assert!(r.data["cid"].is_string());

    // GET /canvas → the creative write landed in the door2 canvas.
    let (_, resp) = h.get("/canvas");
    assert_eq!(resp.data["view"]["kind"], "structure");
    let count = resp.data["view"]["node_count"].as_u64().unwrap_or(0);
    assert!(count >= 2, "canvas shows the seed + compiled note, got {count}");
    assert!(resp.data["view"]["verified"].as_bool().unwrap_or(false), "canvas stays whole-log-verified");

    // GET /evaluate → the REAL frozen policy rule list (no fake table).
    let (status, resp) = h.get("/evaluate");
    assert_eq!(status, 200);
    assert!(resp.ok, "evaluate error: {:?}", resp.error);
    assert_eq!(resp.data["snapshot"], "snap-genesis");
    let rules = resp.data["policy"]["policy"]["rules"].as_array().unwrap();
    assert_eq!(rules.len(), 4, "four genesis rules");
    assert_eq!(rules[0]["capability"], "read:*:*");
    assert_eq!(rules[0]["allow"], true);
    assert_eq!(rules[3]["capability"], "admin:*:*");
    assert_eq!(rules[3]["allow"], false);

    // POST /evaluate → real verdicts from the snapshot.
    let ok_body = serde_json::json!({ "cap": "write:note" });
    let r = http_post_raw(&h.addr, "/evaluate", &ok_body.to_string()).expect("eval write:note");
    assert!(r.ok, "eval error: {:?}", r.error);
    assert_eq!(r.data["allowed"], true, "write:note allowed by genesis");

    let denied_body = serde_json::json!({ "cap": "admin:destroy:*" });
    let r = http_post_raw(&h.addr, "/evaluate", &denied_body.to_string()).expect("eval admin");
    assert!(r.ok, "eval of a denied cap still resolves: {:?}", r.error);
    assert_eq!(r.data["allowed"], false, "admin:destroy denied by genesis");

    // POST /playground → creative single-token write commits.
    let body = serde_json::json!({ "target": "playground/sand-pit", "content": "creative single-token" });
    let r = http_post_raw(&h.addr, "/playground", &body.to_string()).expect("post /playground");
    assert!(r.ok, "playground creative write: {:?}", r.error);
    assert_eq!(r.data["door"], "door2");
    assert_eq!(r.data["escalated"], false);

    // POST /playground/reset → escalated admin:destroy commits double-triplet.
    let body = serde_json::json!({ "target": "playground", "content": "self-reset" });
    let r = http_post_raw(&h.addr, "/playground/reset", &body.to_string()).expect("post /playground/reset");
    assert!(r.ok, "reset error: {:?}", r.error);
    assert_eq!(r.data["door"], "door2");
    assert_eq!(r.data["escalated"], true, "reset is escalated");
    assert!(r.data["cid"].is_string());

    // D2.3 boundary over the SAME wire: the door2 write token ALONE cannot
    // do admin:destroy (no human token) — the shell route proves it too.
    let mut raw_destroy = WireRequest::new("http", h.door2_write.clone(), WireOp::Write {
        snapshot: String::new(),
        op: "admin:destroy".into(),
        target: "zone-a".into(),
        payload: serde_json::json!({"reason": "no human"}),
    });
    let r = h.post(&raw_destroy);
    assert!(!r.ok, "single-token destructive is denied");
    assert!(r.error.as_deref().unwrap_or("").contains("human-gated"), "{:?}", r.error);

    // WITH the human token it commits (double-triplet).
    let mut escalated = WireRequest::new("http", h.door2_write.clone(), WireOp::Write {
        snapshot: String::new(),
        op: "admin:destroy".into(),
        target: "zone-a".into(),
        payload: serde_json::json!({"reason": "authorized"}),
    });
    escalated.escalation = Some(h.human.clone());
    let r = h.post(&escalated);
    assert!(r.ok, "two-token destructive commits: {:?}", r.error);
    assert_eq!(r.data["escalated"], true);
    assert!(r.triplet.is_some(), "double-triplet echoed on the wire");

    // Wipe floor: admin:wipe stays denied even with both tokens.
    raw_destroy.op = WireOp::Write { snapshot: String::new(), op: "admin:wipe".into(), target: "*".into(), payload: serde_json::json!({}) };
    let mut wipe = raw_destroy;
    wipe.escalation = Some(h.human.clone());
    let r = h.post(&wipe);
    assert!(!r.ok, "wipe stays denied: {:?}", r.error);

    println!("m8 GREEN — godmode console/canvas/evaluate/daemon/playground all over ONE wire; creative single-token, destructive escalated, wipe floor denied.");
}

#[test]
fn planned_surfaces_mounted_real_and_shown_live_in_nav_manifest() {
    let h = boot(true);

    // GET /manifest → the four previously-"planned" door1 surfaces are LIVE.
    let (status, resp) = h.get("/manifest");
    assert_eq!(status, 200);
    assert!(resp.ok, "manifest: {:?}", resp.error);
    let surfaces = resp.data["surfaces"].as_array().unwrap();
    let mut by_name = std::collections::HashMap::new();
    for s in surfaces {
        by_name.insert(s["name"].as_str().unwrap().to_string(), s.clone());
    }
    let live_urls = [
        ("dashboard", "/health"),
        ("arena", "/arena"),
        ("tool-policy-console", "/tool-policy"),
        ("plugin-workspace", "/workspace"),
        ("ipam", "/ipam"),
    ];
    for (name, url) in live_urls {
        let s = &by_name[name];
        assert_eq!(s["planned"], false, "{name} is live");
        assert_eq!(s["url"], url, "{name} served at {url}");
    }

    // GET /arena → real Read (shared creative arena).
    let (status, resp) = h.get("/arena");
    assert_eq!(status, 200);
    assert!(resp.ok, "arena: {:?}", resp.error);
    assert_eq!(resp.data["door"], "door1", "arena is a door1 surface");

    // GET /tool-policy → the REAL frozen rule list, mounted live.
    let (status, resp) = h.get("/tool-policy");
    assert_eq!(status, 200);
    assert!(resp.ok, "tool-policy: {:?}", resp.error);
    assert_eq!(resp.data["snapshot"], "snap-genesis");
    assert_eq!(resp.data["door"], "door1");
    assert_eq!(resp.data["policy"]["policy"]["rules"].as_array().unwrap().len(), 4);

    // POST /tool-policy → real verdict.
    let body = serde_json::json!({ "cap": "write:plugin:*" });
    let r = http_post_raw(&h.addr, "/tool-policy", &body.to_string()).expect("eval tool-policy");
    assert!(r.ok, "tool-policy eval: {:?}", r.error);
    assert_eq!(r.data["allowed"], true);

    // GET /workspace → plugin workspace read (may be empty — the route is real).
    let (status, resp) = h.get("/workspace");
    assert_eq!(status, 200);
    assert!(resp.ok, "workspace: {:?}", resp.error);

    // GET /ipam → identity-policy-action registry.
    let (status, resp) = h.get("/ipam");
    assert_eq!(status, 200);
    assert!(resp.ok, "ipam: {:?}", resp.error);
    assert_eq!(resp.data["doors"].as_array().unwrap().len(), 3);
    assert_eq!(resp.data["escalation_armed"], true);

    // The door1 nav SPA still renders (door1 + door2 + door3 on one base).
    let (status, raw) = http_get_raw(&h.addr, "/").expect("get /");
    assert_eq!(status, 200);
    assert!(raw.contains("door1"));

    println!("m8 GREEN — planned surfaces mounted real; door1 nav + door2 godmode + door3 walk-in share ONE base.");
}

#[test]
fn no_escalation_gate_means_creative_ok_but_destructive_unreachable() {
    // D2.3/D2.4: without an armed escalation gate, admin ops are UNREACHABLE
    // even if a human token is attached — godmode is token scope + gate, not a
    // magic role.
    let h = boot(false);

    // Creative still works (door2 tokens alone are enough for write).
    let body = serde_json::json!({ "target": "playground/pavilion", "content": "creative even unarmed" });
    let r = http_post_raw(&h.addr, "/playground", &body.to_string()).expect("post /playground");
    assert!(r.ok, "creative survives unarmed bridge: {:?}", r.error);
    assert_eq!(r.data["escalated"], false);

    // Destructive through the SHELL route: refused (no gate registered).
    let body = serde_json::json!({ "target": "playground", "content": "self-reset" });
    let r = http_post_raw(&h.addr, "/playground/reset", &body.to_string()).expect("post /playground/reset");
    assert!(!r.ok, "reset refused when no gate is armed");
    assert!(r.error.as_deref().unwrap_or("").contains("no escalation gate"), "{:?}", r.error);

    // Destructive over the raw wire with BOTH tokens: refused too.
    let mut escalated = WireRequest::new("http", h.door2_write.clone(), WireOp::Write {
        snapshot: String::new(),
        op: "admin:destroy".into(),
        target: "x".into(),
        payload: serde_json::json!({}),
    });
    escalated.escalation = Some(h.human.clone());
    let r = h.post(&escalated);
    assert!(!r.ok, "even two tokens cannot destroy without the armed gate");
    assert!(r.error.as_deref().unwrap_or("").contains("no escalation gate"), "{:?}", r.error);

    println!("m8 GREEN — no armed gate => destructive unreachable; creative still lives.");
}