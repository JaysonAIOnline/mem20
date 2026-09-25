//! braid_sonic — D3.5: the audio/speech strand. The spine speaks.
//!
//! The kokoro FastAPI container (`jayson-tts`, `:8880`) turns the text of a
//! committed braid node into a real PCM WAV. `braid_sonic` supplies the
//! deterministic elocution (what a node says), the raw HTTP client to kokoro,
//! and the spine stitcher that renders the last N proven nodes of the ONE
//! ledger as a single `audio/wav` resonance stream ("audio echoes of the
//! braid spine").
//!
//! Honesty rule (no-fake): nothing here generates a fake track. If the TTS
//! container is unreachable, every call returns an explicit `Err` naming the
//! failure — the bridge surfaces it as a denial, never as pretend audio.

pub mod elocution;
pub mod mix;
pub mod tts;