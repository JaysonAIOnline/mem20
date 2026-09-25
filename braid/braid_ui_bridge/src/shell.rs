//! door shells (m6/m7) — keyless web surfaces served by the ONE bridge.
//!
//! m6 (door3): the spatial walk-in page + server-side `WireOp::World`.
//! m7 (door1): the nav shell — witness (Lumen), structure (Axiom), state and
//! forge on one base URL, plus a bridge-surface directory (live + planned).
//! Every token is held by the bridge; the browser pages hold no secrets.

use braid_keys::SessionMacaroon;
use braid_wire::{Shell, WireOp};

/// Build the door3 walk-in surface: the embedded page + the bridge-held read
/// token that powers `GET /world`.
pub fn door3_shell(world_token: SessionMacaroon) -> Shell {
    Shell::from_html(include_str!("../assets/walk_in.html")).world_token(world_token)
}

/// Build the door3 spatial walk-in surface (m9, door3 quest3d): the same
/// keyless page + `GET /world` read, PLUS a keyless `POST /world` spatial-write
/// (creative `write:world`) committed into the ONE ledger through the SAME
/// bridge token — the browser never touches a key. The world you see and the
/// world you can add facts to are the same braid.
pub fn door3_spatial_shell(world_token: SessionMacaroon, spatial_token: SessionMacaroon) -> Shell {
    Shell::from_html(include_str!("../assets/walk_in.html"))
        .world_token(world_token)
        .spatial("/world", spatial_token, "write:world")
}

/// Build the door3 audio walk-in surface (m11, D3.5): the same keyless page +
/// `GET /world` read + keyless `POST /world` spatial-write, PLUS the SPOKEN
/// RESONANCE surface — `GET /sound` streams the last `depth` proven nodes of
/// the ONE ledger as a real `audio/wav` spine-audio, synthesized by the kokoro
/// TTS container over a bridge-held read token. The browser only holds the
/// `<audio>` URL; all tokens stay on the bridge.
pub fn door3_audio_shell(
    world_token: SessionMacaroon,
    spatial_token: SessionMacaroon,
    sound_token: SessionMacaroon,
    voice: impl Into<String>,
    depth: u64,
) -> Shell {
    Shell::from_html(include_str!("../assets/walk_in.html"))
        .world_token(world_token)
        .spatial("/world", spatial_token, "write:world")
        .sound("/sound", sound_token, voice, depth)
}

/// Build the door3 intent walk-in surface (m12, spec-forth): the same keyless
/// page + `GET /world` read + keyless `POST /world` spatial-write, PLUS the
/// INTENT STRAND surface — `GET /intent` streams the committed `write:intent`
/// projection (open desires + their proven resolutions) and `POST /intent`
/// commits a new intent, both over bridge-held tokens. The browser never
/// touches a key; a desire and its fulfillment are real braided nodes on the
/// ONE ledger.
pub fn door3_intent_shell(
    world_token: SessionMacaroon,
    spatial_token: SessionMacaroon,
    intent_read_token: SessionMacaroon,
    intent_write_token: SessionMacaroon,
) -> Shell {
    Shell::from_html(include_str!("../assets/walk_in.html"))
        .world_token(world_token)
        .spatial("/world", spatial_token, "write:world")
        .intent("/intent", intent_read_token, intent_write_token)
}

/// Build the door3 TERMINAL door surface (m13, spec-forth): the SAME walk-in
/// page + world/spatial/intent/sound surfaces, PLUS the unified READ VIEW and
/// the unified TAIL that every terminal door reads:
///
/// - `GET /inspect` — single-head/forks invariant, head cid + depth, and every
///   registered door's view position (the walk-in header also shows it).
/// - `GET /tail?limit=&since=` — the last committed nodes of the ONE ledger,
///   as real GK-serialized node records with prev links (cursor-driven so a
///   terminal can `--follow`).
/// - `GET /prove?cid=` — the Merkle spine to genesis for any committed node.
/// - `GET /policy` — the full frozen policy snapshot (rule list).
/// - `POST /query` — a real capability verdict (the console eval surface).
///
/// `read_token` powers the terminal read surfaces (and the sound strand); it
/// is held by the bridge — the CLI and the browser never touch a key.
#[allow(clippy::too_many_arguments)]
pub fn door3_terminal_shell(
    world_token: SessionMacaroon,
    spatial_token: SessionMacaroon,
    intent_read_token: SessionMacaroon,
    intent_write_token: SessionMacaroon,
    read_token: SessionMacaroon,
    voice: impl Into<String>,
    depth: u64,
    tail_limit: u64,
) -> Shell {
    Shell::from_html(include_str!("../assets/walk_in.html"))
        .world_token(world_token)
        .spatial("/world", spatial_token, "write:world")
        .intent("/intent", intent_read_token, intent_write_token)
        .sound("/sound", read_token.clone(), voice, depth)
        .tail("/tail", read_token.clone(), tail_limit)
        .inspect("/inspect", read_token.clone())
        .prove("/prove", read_token.clone())
        .policy("/policy", read_token.clone(), "")
        .eval("/query", read_token, "")
}

/// One entry in the door1 surface directory. `url == ""` marks a PLANNED
/// surface (its nav slot exists, nothing is mounted there yet); a non-empty
/// url is a live surface the bridge already serves (D1.4, no rewrites).
#[derive(Debug, Clone)]
pub struct Door1Surface {
    pub name: &'static str,
    pub url: &'static str,
}

/// Build the door1 nav shell on ONE base URL (D1.3).
///
/// Routes (all keyless, tokens server-side):
/// - `GET /`          → the nav SPA
/// - `GET /witness`   → WireOp::Read (door1 Lumen → witness view)
/// - `GET /structure` → WireOp::Read (door2 Axiom → structure view)
/// - `GET /state`     → WireOp::Health (bridge state)
/// - `POST /forge`    → WireOp::Write `write:note` (bridge write token)
/// - `GET /manifest`  → the surface directory (live + planned, D1.5)
pub fn door1_shell(
    witness_token: SessionMacaroon,
    structure_token: SessionMacaroon,
    forging_token: SessionMacaroon,
    surfaces: Vec<Door1Surface>,
) -> Shell {
    let manifest = serde_json::json!({
        "nav": ["witness", "structure", "forge", "state"],
        "surfaces": surfaces.iter().map(|s| {
            serde_json::json!({ "name": s.name, "url": s.url, "planned": s.url.is_empty() })
        }).collect::<Vec<_>>(),
        "base": "/",
    });

    Shell::from_html(include_str!("../assets/door1.html"))
        .op(
            "/witness",
            WireOp::Read { snapshot: String::new(), op_filter: None },
            witness_token.clone(),
        )
        .op(
            "/structure",
            WireOp::Read { snapshot: String::new(), op_filter: None },
            structure_token,
        )
        .op("/state", WireOp::Health, witness_token)
        .forge("/forge", forging_token)
        .json("/manifest", manifest)
}