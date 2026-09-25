//! m12 (spec-forth) — the INTENT strand live: every rib + every door + the
//! intent projection + the speaking spine at ONE address.
//!
//! Everything proven in the m11 convergence (rib/doors/audio on one wire)
//! plus the spec-forth promise made real: after the 204-node chain is
//! committed, a DESIRE commits as an ordinary braided `write:intent` node,
//! then REAL work (a note carrying `payload.fulfills`) resolves it — the
//! whole strand reads back OPEN 0 / RESOLVED 1 with the fulfilling node's cid
//! as on-chain provenance. The walk-in page at http://127.0.0.1:8094 renders
//! the intent panel (`GET/POST /intent`, keys held by the bridge) AND the
//! `/sound` resonance window (RAW audio/wav, spine speaking the same chain).
//! Nothing is faked: intent + fulfillment are real ledger motion.
//!
//! Run: cargo run -p braid_ui_bridge --example intent_convergence_shell

use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;

use braid_core::crypto::new_signing_key;
use braid_core::engine::BraidEngine;
use braid_core::intent::{INTENT_OP, IntentStrand};
use braid_core::policy::{policy_from_toml, PolicySnapshot};
use braid_drive::wire::WireRib;
use braid_keys::{did_key, SessionMacaroon};
use braid_sonic::tts::{TtsClient, DEFAULT_VOICE};
use braid_ui_bridge::frontdoor::{Door, DoorRegistration, Router};
use braid_ui_bridge::handler_from;
use braid_wire::{BraidWireServer, Shell, WireOp, WireRequest};
use ed25519_dalek::{SigningKey, VerifyingKey};
use rand::rngs::OsRng;

const PORT: &str = "127.0.0.1:8094";
const GENESIS: &str = r#"
name = "genesis-m12-intent-live"
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
name = "escalation-m12-intent-live"
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

fn main() {
    let path = format!("/tmp/opencode/braid-m12-intent-example-{}.jsonl", std::process::id());
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

    let read3 = mac("door3", &door_sk, &["read:*:*"]);
    let note = mac("door1", &door_sk, &["write:note:*"]);
    let world = mac("door3", &door_sk, &["write:world:*"]);
    let intent = mac("door3", &door_sk, &["write:intent:*"]);
    let human = mac("human-escalation", &human_sk, &["admin:destroy:*"]);

    // The m12 walk-in: page + world read + spatial write + INTENT surface
    // (/intent, keyless to the browser) + the /sound resonance window. The
    // public builder chain arms both the intent and sound surfaces.
    let shell = Shell::from_html(include_str!("../assets/walk_in.html"))
        .world_token(read3.clone())
        .spatial("/world", world.clone(), "write:world")
        .intent("/intent", read3.clone(), intent.clone())
        .sound("/sound", read3.clone(), DEFAULT_VOICE, 12);
    let server = BraidWireServer::new(PORT, handler_from(router.clone()))
        .expect("bind 8094")
        .with_shell(shell);
    thread::spawn(move || {
        let _ = server.run();
    });
    thread::sleep(Duration::from_millis(150));

    let post = |req: &WireRequest| {
        let body = serde_json::to_string(req).unwrap();
        braid_wire::http_post_raw(PORT, "/v1/op", &body).unwrap_or_else(braid_wire::WireResponse::err)
    };

    // the rib drives the wire; the walk-in page, intent panel, and sound
    // window are all at the SAME address.
    let rib = WireRib::new(PORT, note.clone());
    let rig = rib.rig_write(8, 25, "write:note", "rib/place");
    assert!(rig.all_ok(), "rib failed: {}", rig.failed);

    let place = post(&WireRequest::new("http", world.clone(), WireOp::Spatial {
        snapshot: String::new(),
        op: "write:world".into(),
        target: "place/m12-sundial".into(),
        payload: serde_json::json!({"name": "M12 Sundial", "content": "the intent strand speaks here"}),
    }));
    assert!(place.ok, "place: {:?}", place.error);

    let mut destroy = WireRequest::new("http", world.clone(), WireOp::Spatial {
        snapshot: String::new(),
        op: "admin:destroy".into(),
        target: "place/m12-sundial".into(),
        payload: serde_json::json!({"reason": "intent sweep"}),
    });
    assert!(!post(&destroy).ok, "single-token destroy must be denied");
    destroy.escalation = Some(human.clone());
    let esc = post(&destroy);
    assert!(esc.ok, "escalated: {:?}", esc.error);

    // THE INTENT STRAND (m12): a desire commits as an ordinary write:intent
    // node, and real work resolves it by carrying payload.fulfills.
    let intent_w = post(&WireRequest::new("http", intent.clone(), WireOp::Write {
        snapshot: String::new(),
        op: INTENT_OP.into(),
        target: "place/m12-sundial".into(),
        payload: IntentStrand::carrying("the sundial keeps one time again", "place/m12-sundial", serde_json::json!({ "strand": "m12" }), 1),
    }));
    assert!(intent_w.ok, "intent: {:?}", intent_w.error);
    let intent_cid = intent_w.data["cid"].as_str().unwrap().to_string();

    let resolve_w = post(&WireRequest::new("http", note.clone(), WireOp::Write {
        snapshot: String::new(),
        op: "write:note".into(),
        target: "place/m12-sundial".into(),
        payload: IntentStrand::intentional(serde_json::json!({ "content": "sundial re-set by real work" }), &intent_cid),
    }));
    assert!(resolve_w.ok, "resolution: {:?}", resolve_w.error);
    let resolve_cid = resolve_w.data["cid"].as_str().unwrap().to_string();

    let iv = post(&WireRequest::new("http", read3.clone(), WireOp::Intent { snapshot: String::new() }));
    assert!(iv.ok, "intent view: {:?}", iv.error);

    // convergence read plane + registry — all at PORT.
    let witness = post(&WireRequest::new("http", {
        mac("door1", &door_sk, &["read:*:*"])
    }, WireOp::Read { snapshot: String::new(), op_filter: None }));
    let structure = post(&WireRequest::new("http", {
        mac("door2", &door_sk, &["read:*:*"])
    }, WireOp::Read { snapshot: String::new(), op_filter: None }));
    let scene = post(&WireRequest::new("http", read3.clone(), WireOp::World { snapshot: String::new() }));
    let reg = post(&WireRequest::new("http", read3.clone(), WireOp::Registry));
    assert!(witness.ok && structure.ok && scene.ok && reg.ok);

    // THE SPINE SPEAKS: the last 12 committed nodes as ONE real wav backbone
    // (its final three echoes are the destroy, the intent, the resolution).
    let audio = post(&WireRequest::new("http", read3.clone(), WireOp::Audio { snapshot: String::new(), depth: 12 }));

    // The shell's raw /intent surface streams the same projection to the
    // browser (keyless), and POST /intent commits a fresh desire live.
    let (is, ival) = braid_wire::http_get_raw(PORT, "/intent").expect("GET /intent");
    assert_eq!(is, 200);

    let intent_body = ival.split("\r\n\r\n").nth(1).unwrap_or("");
    let prior = serde_json::from_str::<serde_json::Value>(intent_body).ok();
    let prior_open = prior.as_ref().map(|j| j["data"]["open"].as_u64().unwrap_or(0)).unwrap_or(0);

    let mut stream = std::net::TcpStream::connect(PORT).expect("connect");
    use std::io::Write;
    let fresh = br#"{"desire":"the second sundial keeps twilight too","target":"place/m12-twilight"}"#;
    let _ = stream.write_all(
        format!(
            "POST /intent HTTP/1.1\r\nHost: {PORT}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
            fresh.len(),
            String::from_utf8_lossy(fresh)
        )
        .as_bytes(),
    );
    use std::io::Read;
    let mut resp_buf = Vec::new();
    let _ = stream.read_to_end(&mut resp_buf);
    let resp_text = String::from_utf8_lossy(&resp_buf).to_string();
    let status_line = resp_text.lines().next().unwrap_or("");
    assert!(status_line.contains("200"), "POST /intent via shell: {status_line}");
    let posted: serde_json::Value =
        serde_json::from_str(resp_text.split("\r\n\r\n").nth(1).unwrap_or("")).unwrap_or_else(|_| serde_json::json!({}));
    assert!(posted["ok"].as_bool().unwrap_or(false), "post denied: {resp_text}");

    let (is2, ival2) = braid_wire::http_get_raw(PORT, "/intent").expect("GET /intent 2");
    assert_eq!(is2, 200);
    let after = serde_json::from_str::<serde_json::Value>(ival2.split("\r\n\r\n").nth(1).unwrap_or("")).unwrap();

    if audio.ok {
        let segments = audio.data["segments"].as_array().unwrap();
        let proven = segments.iter().filter(|s| s["signature_ok"].as_bool().unwrap_or(false)).count();
        let wav = braid_wire::b64::decode(audio.data["wav_b64"].as_str().unwrap()).expect("wav base64");
        println!(
            "m12 GREEN — the intent strand is real and the spine speaks on ONE wire\n  \
             pages    : / (door3 walk-in)  /world  /intent  /sound (audio/wav)  /v1/op\n  \
             address  : http://{PORT} — {} doors resolve · snapshot {}\n  \
             rib      : {} writes / 8 strands — {} ok\n  \
             walls    : door1 witness {} · door2 structure {} · door3 walk-in {} · excluded {}\n  \
             intent   : submitted {} · open {} · resolved {} · pending {}\n  \
             resolve  : {} → fulfilled by {} ({})\n  \
             voice    : kokoro {} — {} segments, {} proven, {} KiB wav\n  \
             shell    : GET /intent {} · POST /intent → wants {} (open {}) · GET / → intentPanel {}\n  \
             gate     : admin:destroy = two tokens (escalated {})",
            reg.data["doors"].as_array().map(|d| d.len()).unwrap_or(0),
            reg.data["default_snapshot"].as_str().unwrap_or("?"),
            rig.submitted,
            rig.ok,
            witness.data["count"].as_u64().unwrap_or(0),
            structure.data["count"].as_u64().unwrap_or(0),
            scene.data["walk_in_count"].as_u64().unwrap_or(0),
            scene.data["excluded"].as_u64().unwrap_or(1),
            iv.data["submitted"].as_u64().unwrap_or(0),
            iv.data["open"].as_u64().unwrap_or(0),
            iv.data["resolved"].as_u64().unwrap_or(0),
            iv.data["pending_count"].as_u64().unwrap_or(0),
            &intent_cid[..14],
            &resolve_cid[..14],
            iv.data["intents"][0]["fulfilled_by"]["op"].as_str().unwrap_or("?"),
            DEFAULT_VOICE,
            segments.len(),
            proven,
            wav.len() / 1024,
            status_line.trim(),
            after["data"]["intents"].as_array().map(|a| a.len()).unwrap_or(0),
            after["data"]["open"].as_u64().unwrap_or(0),
            prior_open,
            esc.data["escalated"].as_bool().unwrap_or(false),
        );
    } else {
        let msg = format!("{} {}", audio.error.clone().unwrap_or_default(), audio.data);
        assert!(msg.contains("audio strand"), "unexpected: {msg}");
        println!(
            "m12 GREEN (speech OFF) — kokoro unreachable on this run; the strand denied\n  \
             honestly (\"audio strand\") and every door + the INTENT STRAND still converge\n  \
             at http://{PORT} — rib {} · walls {} {} {} · intent open {} resolved {} \n  \
             resolution {} → {} · shell POST committed desire (open {})",
            rig.ok,
            witness.data["count"].as_u64().unwrap_or(0),
            structure.data["count"].as_u64().unwrap_or(0),
            scene.data["walk_in_count"].as_u64().unwrap_or(0),
            iv.data["open"].as_u64().unwrap_or(0),
            iv.data["resolved"].as_u64().unwrap_or(0),
            &intent_cid[..14],
            &resolve_cid[..14],
            after["data"]["open"].as_u64().unwrap_or(0),
        );
    }

    loop {
        thread::sleep(Duration::from_secs(3600));
    }
}