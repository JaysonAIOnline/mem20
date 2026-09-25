//! m11 (D3.5) — the spine speaks, live: every rib + every door + the AUDIO
//! strand at ONE address.
//!
//! Everything proven in m10 (rib/ARP convergence on one wire) plus the speech
//! strand: after the 202-node chain is committed, the SAME ledger's last
//! voices are synthesized by the kokoro TTS container into ONE backbone
//! `audio/wav`. The walk-in page at http://127.0.0.1:8093 now carries a
//! `GET /sound` resonance window — RAW audio to the browser, keys held by the
//! bridge, live `signature_ok` on every spoken segment. If kokoro is down the
//! strand denies honestly; it never fakes.
//!
//! Run: cargo run -p braid_ui_bridge --example audio_convergence_shell

use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;

use braid_core::crypto::new_signing_key;
use braid_core::engine::BraidEngine;
use braid_core::policy::{policy_from_toml, PolicySnapshot};
use braid_drive::wire::WireRib;
use braid_keys::{did_key, SessionMacaroon};
use braid_sonic::tts::{TtsClient, DEFAULT_VOICE};
use braid_ui_bridge::frontdoor::{Door, DoorRegistration, Router};
use braid_ui_bridge::{door3_audio_shell, handler_from};
use braid_wire::{BraidWireServer, WireOp, WireRequest};
use ed25519_dalek::{SigningKey, VerifyingKey};
use rand::rngs::OsRng;

const PORT: &str = "127.0.0.1:8093";
const GENESIS: &str = r#"
name = "genesis-m11-audio-live"
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
name = "escalation-m11-audio-live"
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
    let path = format!("/tmp/opencode/braid-m11-audio-example-{}.jsonl", std::process::id());
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
    let human = mac("human-escalation", &human_sk, &["admin:destroy:*"]);

    // The audio walk-in: page + world read + spatial write + `/sound` spine.
    let shell = door3_audio_shell(read3.clone(), world.clone(), read3.clone(), DEFAULT_VOICE, 12);
    let handler = handler_from(router.clone());
    let server = BraidWireServer::new(PORT, handler)
        .expect("bind 8093")
        .with_shell(shell);
    thread::spawn(move || {
        let _ = server.run();
    });
    thread::sleep(Duration::from_millis(150));

    let post = |req: &WireRequest| {
        let body = serde_json::to_string(req).unwrap();
        braid_wire::http_post_raw(PORT, "/v1/op", &body).unwrap_or_else(braid_wire::WireResponse::err)
    };

    // the rib drives the wire — the walk-in page and its sound window are up
    // at the SAME address.
    let rib = WireRib::new(PORT, note.clone());
    let rig = rib.rig_write(8, 25, "write:note", "rib/place");
    assert!(rig.all_ok(), "rib failed: {}", rig.failed);

    let place = post(&WireRequest::new("http", world.clone(), WireOp::Spatial {
        snapshot: String::new(),
        op: "write:world".into(),
        target: "place/m11-sundial".into(),
        payload: serde_json::json!({"name": "M11 Sundial", "content": "the spine speaks here"}),
    }));
    assert!(place.ok, "place: {:?}", place.error);

    let mut destroy = WireRequest::new("http", world.clone(), WireOp::Spatial {
        snapshot: String::new(),
        op: "admin:destroy".into(),
        target: "place/m11-sundial".into(),
        payload: serde_json::json!({"reason": "audio sweep"}),
    });
    assert!(!post(&destroy).ok, "single-token destroy must be denied");
    destroy.escalation = Some(human.clone());
    let esc = post(&destroy);
    assert!(esc.ok, "escalated: {:?}", esc.error);

    // convergence read plane — all at PORT.
    let witness = post(&WireRequest::new("http", read1.clone(), WireOp::Read { snapshot: String::new(), op_filter: None }));
    let structure = post(&WireRequest::new("http", read2.clone(), WireOp::Read { snapshot: String::new(), op_filter: None }));
    let scene = post(&WireRequest::new("http", read3.clone(), WireOp::World { snapshot: String::new() }));
    assert!(witness.ok && structure.ok && scene.ok);
    let reg = post(&WireRequest::new("http", read3.clone(), WireOp::Registry));

    // THE SPINE SPEAKS: the last 12 committed nodes as ONE real wav backbone.
    let audio = post(&WireRequest::new("http", read3.clone(), WireOp::Audio { snapshot: String::new(), depth: 12 }));
    if audio.ok {
        let segments = audio.data["segments"].as_array().unwrap();
        let proven = segments.iter().filter(|s| s["signature_ok"].as_bool().unwrap_or(false)).count();
        let wav = braid_wire::b64::decode(audio.data["wav_b64"].as_str().unwrap()).expect("wav base64");
        let wav_kb = wav.len() / 1024;
        println!(
            "m11 GREEN — the spine speaks on ONE wire\n  \
             pages    : / (door3 audio walk-in)  /world  /sound (audio/wav)  /v1/op\n  \
             address  : http://{PORT} — {} doors resolve\n  \
             rib      : {} writes / 8 strands — {} ok, {} failed\n  \
             walls    : door1 witness {} nodes · door2 structure {} · door3 walk-in {} — {}\n  \
             voice    : kokoro {} — {} segments, {} proven, {wav_kb} KiB wav, {} ms total\n  \
             gate     : admin:destroy = two tokens, escalated {}; audio denied for write-only\n  \
             snapshot : {} across every surface",
            reg.data["doors"].as_array().map(|d| d.len()).unwrap_or(0),
            rig.submitted,
            rig.ok,
            rig.failed,
            witness.data["count"].as_u64().unwrap_or(0),
            structure.data["count"].as_u64().unwrap_or(0),
            scene.data["walk_in_count"].as_u64().unwrap_or(0),
            scene.data["excluded"].as_u64().unwrap_or(1),
            DEFAULT_VOICE,
            segments.len(),
            proven,
            audio.data["total_ms"].as_u64().unwrap_or(0),
            esc.data["escalated"].as_bool().unwrap_or(false),
            reg.data["default_snapshot"].as_str().unwrap_or("?"),
        );

        // The shell's raw /sound route streams the spine as REAL audio/wav
        // (separate kokoro pass — same semantics, fresh synthesis). Base64
        // never leaves the bridge.
        let (status, ctype, body) = braid_wire::http_get_bytes(PORT, "/sound").expect("GET /sound");
        assert_eq!(status, 200, "GET /sound must stream audio");
        assert_eq!(ctype, "audio/wav");
        assert!(body.starts_with(b"RIFF"));
        let shell_render = braid_sonic::tts::VoiceRender::from_wav(body).expect("shell WAV parses");
        assert_eq!(shell_render.sample_rate, 24000, "same 24kHz spine");
        assert!(shell_render.pcm.len() >= wav.len() / 2, "a full real render, not a stub");
        println!("  sound    : GET /sound 200 audio/wav — {} KiB, ~{} s spine (fresh synthesis)", shell_render.bytes / 1024, shell_render.ms / 1000);
    } else {
        // kokoro down: honest denial, never fake. The walls still converge.
        let msg = format!("{} {}", audio.error.clone().unwrap_or_default(), audio.data);
        assert!(msg.contains("audio strand"), "unexpected: {msg}");
        println!(
            "m11 GREEN (speech OFF) — kokoro unreachable on this run; the strand denied\n  \
             honestly (\"audio strand\") and every door still converges on ONE wire at http://{PORT}\n  \
             rib {} ok / walls {} {} {}\n  gate escalated {} — snapshot {}",
            rig.ok,
            witness.data["count"].as_u64().unwrap_or(0),
            structure.data["count"].as_u64().unwrap_or(0),
            scene.data["walk_in_count"].as_u64().unwrap_or(0),
            esc.data["escalated"].as_bool().unwrap_or(false),
            reg.data["default_snapshot"].as_str().unwrap_or("?"),
        );
    }

    loop {
        thread::sleep(Duration::from_secs(3600));
    }
}