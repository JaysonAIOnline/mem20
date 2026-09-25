//! m11 (D3.5) — the audio strand: spoken resonance over the ONE wire.
//!
//! The spine speaks its last `depth` proven nodes as one backbone `audio/wav`
//! stream, synthesized by the kokoro TTS container (jayson-tts) through a
//! bridge-held READ token. Honesty rule: the test NEVER expects a fake track —
//! if the TTS container is unreachable it asserts the bridge denies with an
//! explicit `audio strand` error instead. Proven over real HTTP:
//!   - WireOp::Audio renders real RIFF/WAVE audio of the last N committed nodes
//!   - each spoken segment carries live provenance (signature_ok), exactly like
//!     the walk-in's facts
//!   - depth clamps to the nodes the token can read (no invented echoes)
//!   - WRITE-only tokens cannot hear (audio is read-gated like every read)
//!   - the keyless `/sound` shell route streams raw `audio/wav` (not JSON)
//!   - an unreachable TTS never fabricates: the op denies honestly

use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;

use braid_core::crypto::new_signing_key;
use braid_core::engine::BraidEngine;
use braid_core::policy::{policy_from_toml, PolicySnapshot};
use braid_keys::{did_key, SessionMacaroon};
use braid_sonic::tts::{TtsClient, DEFAULT_VOICE};
use braid_ui_bridge::frontdoor::{Door, DoorRegistration, Router};
use braid_ui_bridge::handler_from;
use braid_ui_bridge::shell::door3_audio_shell;
use braid_wire::{http_get_bytes, http_post_raw, BraidWireServer, WireOp, WireRequest};
use ed25519_dalek::{SigningKey, VerifyingKey};
use rand::rngs::OsRng;

const GENESIS: &str = r#"
name = "genesis-m11-audio"
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
name = "escalation-m11-audio"
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

struct Harness {
    addr: String,
    read3: SessionMacaroon,
    note: SessionMacaroon,
}

impl Harness {
    fn post(&self, req: &WireRequest) -> braid_wire::WireResponse {
        let body = serde_json::to_string(req).unwrap();
        http_post_raw(&self.addr, "/v1/op", &body).unwrap_or_else(braid_wire::WireResponse::err)
    }

    fn write(&self, content: &str) -> braid_wire::WireResponse {
        self.post(&WireRequest::new("http", self.note.clone(), WireOp::Write {
            snapshot: String::new(),
            op: "write:note".into(),
            target: "sound/echos".into(),
            payload: serde_json::json!({ "content": content }),
        }))
    }

    fn hear(&self, token: &SessionMacaroon, depth: u64) -> braid_wire::WireResponse {
        self.post(&WireRequest::new("http", token.clone(), WireOp::Audio { snapshot: String::new(), depth }))
    }
}

fn boot(tts: TtsClient, with_sound_shell: bool) -> Harness {
    use std::sync::atomic::{AtomicU64, Ordering};
    static SEQ: AtomicU64 = AtomicU64::new(0);
    let seq = SEQ.fetch_add(1, Ordering::Relaxed);
    let path = format!("/tmp/opencode/braid-m11-audio-{}-{seq}.jsonl", std::process::id());
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
        .with_tts(tts),
    );

    let read3 = mac("door3", &door_sk, &["read:*:*"]);
    let note = mac("door1", &door_sk, &["write:note:*"]);
    let world = mac("door3", &door_sk, &["write:world:*"]);

    let server = if with_sound_shell {
        // The keyless audio surface: page + world read + spatial write + the
        // `/sound` resonance stream (bridge-held read token, kokoro voice).
        let shell = door3_audio_shell(read3.clone(), world, read3.clone(), DEFAULT_VOICE, 10);
        BraidWireServer::new("127.0.0.1:0", handler_from(router))
            .expect("bind")
            .with_shell(shell)
    } else {
        BraidWireServer::new("127.0.0.1:0", handler_from(router)).expect("bind")
    };
    let addr = server.local_addr();
    thread::spawn(move || {
        let _ = server.run();
    });
    thread::sleep(Duration::from_millis(150));

    Harness { addr, read3, note }
}

#[test]
fn audio_strand_is_real_or_honest() {
    let h = boot(TtsClient::new(), false);

    // The spine only speaks what was committed.
    for (i, text) in ["the spine wakes", "it remembers the walk", "ribs converge on this wire", "one ledger"].iter().enumerate() {
        let w = h.write(&format!("{text} — echo {i}"));
        assert!(w.ok, "write {i}: {:?}", w.error);
    }

    let deny_msg = |r: &braid_wire::WireResponse| format!("{} {}", r.error.clone().unwrap_or_default(), r.data);

    // The RESPONSE decides the branch: a live TTS must yield real barrels, a
    // downed TTS must deny HONESTLY (naming the strand). Either branch is
    // asserted strictly — never a fake track.
    let a = h.hear(&h.read3, 4);
    if !a.ok {
        assert!(
            deny_msg(&a).contains("audio strand"),
            "honest denial expected (audio strand): got {:?}",
            deny_msg(&a)
        );
        return;
    }

    // Real barrels: 4 nodes, depth clamp, live provenance.
    assert_eq!(a.data["spoken"].as_u64().unwrap_or(0), 4, "the spine speaks exactly the last 4 nodes");
    assert_eq!(a.data["sample_rate"].as_u64().unwrap_or(0), 24000, "kokoro emits 24kHz");
    assert_eq!(a.data["channels"].as_u64().unwrap_or(0), 1);
    assert_eq!(a.data["voice"], DEFAULT_VOICE);
    assert!(a.data["total_ms"].as_u64().unwrap_or(0) > 0, "real audio has duration");
    let segments = a.data["segments"].as_array().unwrap();
    for (i, seg) in segments.iter().enumerate() {
        assert!(seg["signature_ok"].as_bool().unwrap_or(false), "segment {i} must be a proven node");
        assert!(!seg["spoken"].as_str().unwrap_or("").is_empty(), "segment {i} must have elocution");
        assert!(seg["ms"].as_u64().unwrap_or(0) > 0, "segment {i} must be a real render");
    }
    // The WAV is real RIFF audio, not a placeholder.
    let wav = braid_wire::b64::decode(a.data["wav_b64"].as_str().unwrap()).expect("wav base64");
    assert!(wav.starts_with(b"RIFF") && &wav[8..12] == b"WAVE", "real WAVE stream");

    // Depth clamps to what the token can read — no invented echoes.
    let cl = h.hear(&h.read3, 1000);
    assert_eq!(cl.data["spoken"].as_u64().unwrap_or(0), 4, "depth 1000 clamps to 4 read nodes");
}

#[test]
fn audio_is_read_gated_not_write_gated() {
    // The note token writes but cannot HEAR.
    let h = boot(TtsClient::new(), false);
    let w = h.write("a note");
    assert!(w.ok);
    let denied = h.hear(&h.note, 4);
    assert!(!denied.ok, "a write token must not hear");
    assert!(denied.error.clone().unwrap_or_default().contains("does not grant read"), "got: {:?}", denied.error);
}

#[test]
fn unreachable_tts_denies_honestly() {
    // A dead kokoro endpoint: the strand runs on a REAL wire, the container
    // is the ONLY synthesis engine — so the whole stream denies with an
    // explicit upstream error. No pretend audio, ever.
    let h = boot(TtsClient::new().with_url("127.0.0.1:1"), false);
    let w = h.write("one honest echo");
    assert!(w.ok);
    let a = h.hear(&h.read3, 4);
    assert!(!a.ok, "dead TTS must deny");
    let msg = format!("{} {}", a.error.clone().unwrap_or_default(), a.data);
    assert!(msg.contains("audio strand"), "honest denial naming the strand: got {msg}");
}

#[test]
fn sound_shell_streams_real_wav() {
    // The keyless `/sound` route (door3 audio shell): RAW audio/wav to the
    // browser — base64 never leaves the bridge.
    let h = boot(TtsClient::new(), true);
    for text in ["one", "two", "three"] {
        let w = h.write(text);
        assert!(w.ok);
    }

    let (status, content_type, body) = http_get_bytes(&h.addr, "/sound").expect("get /sound");
    if status != 200 {
        // TTS down (or mid-warm): the shell must deny HONESTLY as audio/wav
        // never leaks as a fake. Assert the 403 names the strand.
        assert_eq!(status, 403, "sound route must deny honestly, got {status}");
        let raw = String::from_utf8_lossy(&body).to_string();
        assert!(raw.contains("audio strand"), "honest denial through the shell: got {raw}");
        return;
    }
    assert_eq!(content_type, "audio/wav", "content-type audio/wav (got {content_type})");
    assert!(body.starts_with(b"RIFF"), "raw WAV body at /sound");
    assert!(body.len() > 44, "the body is a whole real WAV, not a stub");
}