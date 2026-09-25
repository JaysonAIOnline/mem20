//! The spine stitcher — render the last N proven nodes of the ONE ledger as a
//! single `audio/wav` resonance stream ("audio echoes of the braid spine").
//!
//! Each segment is one REAL kokoro render of the node's elocution; the PCM
//! payloads are concatenated into one canonical mono-16-bit WAV in ledger
//! order, so the audio plays the spine from oldest to newest. Honesty rule:
//! any node that fails to render aborts the WHOLE stream with an explicit
//! error — a broken, partial or fake track is never served.

use braid_core::storage::Node;
use serde::Serialize;

use crate::elocution::spoken_text;
use crate::tts::TtsClient;

/// One spoken echo in the spine stream.
#[derive(Debug, Clone, Serialize)]
pub struct SpineSegment {
    pub cid: String,
    pub depth: u64,
    pub op: String,
    pub target: String,
    pub spoken: String,
    pub bytes: usize,
    pub ms: u64,
    /// The verifier's live answer — mirrors the walk-in's `FactProvenance`.
    pub signature_ok: bool,
}

/// The full resonance stream: one canonical WAV + per-segment provenance.
#[derive(Debug, Clone, Serialize)]
pub struct SpineAudio {
    pub wav: Vec<u8>,
    pub sample_rate: u32,
    pub channels: u16,
    pub bits_per_sample: u16,
    pub total_bytes: usize,
    pub total_ms: u64,
    pub voice: String,
    pub segments: Vec<SpineSegment>,
}

/// Render the given proven nodes as one spine-audio stream. Nodes must be in
/// ascending ledger order (the caller supplies the last N). Returns an honest
/// `Err` when any node fails to render — the bridge surfaces it as a denial.
pub fn speak_spine(tts: &TtsClient, nodes: &[Node]) -> Result<SpineAudio, String> {
    if nodes.is_empty() {
        return Err("audio strand: no proven nodes to speak".into());
    }

    let mut pcm_all: Vec<u8> = Vec::new();
    let mut segments: Vec<SpineSegment> = Vec::with_capacity(nodes.len());
    let mut total_ms = 0u64;
    let mut sample_rate = 0u32;
    let mut channels = 1u16;

    for node in nodes {
        let spoken = spoken_text(&node.body.payload, &node.cid, &node.body.target, &node.body.op);
        let render = tts
            .synthesize(&spoken)
            .map_err(|e| format!("audio strand: node {} (depth {}) failed to render: {e}", node.cid, node.depth))?;
        sample_rate = render.sample_rate;
        channels = render.channels;
        total_ms += render.ms;
        pcm_all.extend_from_slice(&render.pcm);
        segments.push(SpineSegment {
            cid: node.cid.clone(),
            depth: node.depth,
            op: node.body.op.clone(),
            target: node.body.target.clone(),
            spoken,
            bytes: render.bytes,
            ms: render.ms,
            signature_ok: node.audit.as_ref().map(|a| a.verified(&node.signer)).unwrap_or(false),
        });
    }

    let wav = canonical_wav(&pcm_all, sample_rate)?;
    Ok(SpineAudio {
        total_bytes: wav.len(),
        total_ms,
        sample_rate,
        channels,
        bits_per_sample: 16,
        voice: tts.voice.clone(),
        wav,
        segments,
    })
}

/// Build a canonical mono 16-bit WAV from the concatenated PCM payloads.
pub fn canonical_wav(pcm: &[u8], sample_rate: u32) -> Result<Vec<u8>, String> {
    if pcm.is_empty() {
        return Err("canonical_wav: no PCM".into());
    }
    if sample_rate == 0 {
        return Err("canonical_wav: bad sample rate 0".into());
    }
    let data_len = pcm.len() as u32;
    let mut wav = Vec::with_capacity(44 + pcm.len());
    wav.extend_from_slice(b"RIFF");
    wav.extend_from_slice(&(36 + data_len).to_le_bytes());
    wav.extend_from_slice(b"WAVE");
    wav.extend_from_slice(b"fmt ");
    wav.extend_from_slice(&16u32.to_le_bytes());
    wav.extend_from_slice(&1u16.to_le_bytes()); // PCM
    wav.extend_from_slice(&1u16.to_le_bytes()); // mono
    wav.extend_from_slice(&sample_rate.to_le_bytes());
    wav.extend_from_slice(&(sample_rate * 2).to_le_bytes()); // byte rate
    wav.extend_from_slice(&2u16.to_le_bytes()); // block align
    wav.extend_from_slice(&16u16.to_le_bytes());
    wav.extend_from_slice(b"data");
    wav.extend_from_slice(&data_len.to_le_bytes());
    wav.extend_from_slice(pcm);
    Ok(wav)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn canonical_wav_is_a_well_formed_stream() {
        let pcm: Vec<u8> = (0..128u8).collect();
        let wav = canonical_wav(&pcm, 24000).expect("wav");
        assert!(wav.starts_with(b"RIFF"));
        assert!(&wav[8..12] == b"WAVE");
        assert_eq!(wav.len(), 44 + pcm.len());
        // mono 16-bit 24kHz header fields
        let rate = u32::from_le_bytes([wav[24], wav[25], wav[26], wav[27]]);
        assert_eq!(rate, 24000);
        assert_eq!(wav[22], 1); // channels
        let data_len = u32::from_le_bytes([wav[40], wav[41], wav[42], wav[43]]);
        assert_eq!(data_len as usize, pcm.len());
    }
}