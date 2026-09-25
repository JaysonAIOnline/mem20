//! Raw-TCP HTTP client for the kokoro FastAPI TTS container.
//!
//! The rest of the workspace ships with a hand-rolled HTTP stack (no
//! reqwest/ureq), so this client does the same: one `TcpStream`, one request,
//! one response. `POST {base}/v1/audio/speech` with the OpenAI-compatible
//! JSON body returns a binary WAV, which we parse back into PCM + sample
//! metadata.

use std::io::{Read, Write};
use std::net::TcpStream;
use std::time::Duration;

/// Default kokoro container endpoint (`jayson-tts` in the compose file).
pub const DEFAULT_KOKORO: &str = "127.0.0.1:8880";
/// Default deterministic voice (kokoro af_* readable female).
pub const DEFAULT_VOICE: &str = "af_heart";

/// A rendered speech track: the full WAV file plus the PCM we parsed out of
/// it (mono, 16-bit — what kokoro emits).
#[derive(Debug, Clone)]
pub struct VoiceRender {
    pub wav: Vec<u8>,
    pub pcm: Vec<u8>,
    pub sample_rate: u32,
    pub channels: u16,
    pub bits_per_sample: u16,
    pub bytes: usize,
    pub ms: u64,
}

impl VoiceRender {
    /// Parse a kokoro WAV into its PCM payload + stream metadata.
    pub fn from_wav(wav: Vec<u8>) -> Result<Self, String> {
        let (sample_rate, channels, bits, pcm_off, pcm_len) = parse_wav(&wav)?;
        let pcm = wav[pcm_off..pcm_off + pcm_len].to_vec();
        let bytes = wav.len();
        let block = (bits / 8) as u64 * channels as u64;
        let ms = if sample_rate == 0 {
            0
        } else {
            ((pcm.len() as u64 / block.max(1)) * 1000) / sample_rate as u64
        };
        Ok(VoiceRender { wav, pcm, sample_rate, channels, bits_per_sample: bits, bytes, ms })
    }
}

/// The TTS client. All fields public so the bridge can report its config.
#[derive(Debug, Clone)]
pub struct TtsClient {
    pub base_url: String,
    pub voice: String,
    pub timeout_ms: u64,
}

impl Default for TtsClient {
    fn default() -> Self {
        Self::new()
    }
}

impl TtsClient {
    /// Pointed at the local kokoro container with the default voice.
    pub fn new() -> Self {
        Self { base_url: DEFAULT_KOKORO.to_string(), voice: DEFAULT_VOICE.to_string(), timeout_ms: 20_000 }
    }

    pub fn with_url(mut self, base_url: impl Into<String>) -> Self {
        self.base_url = base_url.into();
        self
    }

    pub fn with_voice(mut self, voice: impl Into<String>) -> Self {
        self.voice = voice.into();
        self
    }

    pub fn with_timeout_ms(mut self, ms: u64) -> Self {
        self.timeout_ms = ms;
        self
    }

    /// Live probe: is the TTS container answering? `false` when unreachable.
    pub fn reachable(&self) -> bool {
        http_get_status(&self.base_url, "/v1/models").unwrap_or(false)
    }

    /// Speak `text` as real PCM WAV via the kokoro container.
    pub fn synthesize(&self, text: &str) -> Result<VoiceRender, String> {
        let body = serde_json::json!({
            "model": "kokoro",
            "input": text,
            "voice": self.voice,
            "response_format": "wav",
        });
        let raw = http_post_bin(&self.base_url, "/v1/audio/speech", &body.to_string(), self.timeout_ms)?;
        if raw.is_empty() {
            return Err("kokoro TTS returned an empty body".into());
        }
        let render = VoiceRender::from_wav(raw).map_err(|e| format!("kokoro TTS WAV parse: {e}"))?;
        if render.pcm.is_empty() {
            return Err("kokoro TTS produced a WAV with no PCM (empty speech)".into());
        }
        Ok(render)
    }
}

/// Parse a minimal RIFF/WAVE file: returns (sample_rate, channels, bits,
/// data offset, data length). Only uncompressed PCM is accepted.
fn parse_wav(bytes: &[u8]) -> Result<(u32, u16, u16, usize, usize), String> {
    if bytes.len() < 12 || &bytes[0..4] != b"RIFF" || &bytes[8..12] != b"WAVE" {
        return Err("not a RIFF/WAVE file".into());
    }
    let mut off = 12usize;
    let mut sample_rate = 0u32;
    let mut channels = 0u16;
    let mut bits = 0u16;
    let mut pcm_off = 0usize;
    let mut pcm_len = 0usize;
    while off + 8 <= bytes.len() {
        let id = &bytes[off..off + 4];
        let size = u32::from_le_bytes([bytes[off + 4], bytes[off + 5], bytes[off + 6], bytes[off + 7]]) as usize;
        if id == b"fmt " {
            if off + 26 > bytes.len() {
                return Err("fmt chunk truncated".into());
            }
            let format = u16::from_le_bytes([bytes[off + 8], bytes[off + 9]]);
            if format != 1 && format != 0xFFFE {
                return Err(format!("not uncompressed PCM (audio format {format})"));
            }
            channels = u16::from_le_bytes([bytes[off + 10], bytes[off + 11]]);
            sample_rate = u32::from_le_bytes([bytes[off + 12], bytes[off + 13], bytes[off + 14], bytes[off + 15]]);
            bits = u16::from_le_bytes([bytes[off + 22], bytes[off + 23]]);
        } else if id == b"data" {
            pcm_off = off + 8;
            pcm_len = size.min(bytes.len().saturating_sub(pcm_off));
        }
        off += 8 + size + (size & 1);
    }
    if pcm_off == 0 || pcm_len == 0 {
        return Err("WAV has no data chunk".into());
    }
    if sample_rate == 0 || channels == 0 || bits == 0 {
        return Err("WAV fmt chunk missing rate/channels/bits".into());
    }
    Ok((sample_rate, channels, bits, pcm_off, pcm_len))
}

/// One raw HTTP POST returning the binary response body. URL is
/// `{base}{path}`, base is `host:port` without scheme.
fn http_post_bin(base: &str, path: &str, json: &str, timeout_ms: u64) -> Result<Vec<u8>, String> {
    let base = base.trim_start_matches("http://").trim_start_matches("https://");
    let mut stream = TcpStream::connect(base).map_err(|e| format!("kokoro TTS connect {base}: {e}"))?;
    stream
        .set_read_timeout(Some(Duration::from_millis(timeout_ms)))
        .map_err(|e| format!("set read timeout: {e}"))?;
    stream
        .set_write_timeout(Some(Duration::from_millis(timeout_ms)))
        .map_err(|e| format!("set write timeout: {e}"))?;
    let req = format!(
        "POST {path} HTTP/1.1\r\nHost: {base}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{json}",
        json.len()
    );
    stream.write_all(req.as_bytes()).map_err(|e| format!("kokoro TTS write: {e}"))?;
    let mut resp = Vec::new();
    stream.read_to_end(&mut resp).map_err(|e| format!("kokoro TTS read: {e}"))?;
    let header_end = resp
        .windows(4)
        .position(|w| w == b"\r\n\r\n")
        .map(|i| i + 4)
        .ok_or("kokoro TTS: no response headers")?;
    let head = String::from_utf8_lossy(&resp[..header_end]).to_string();
    let status: u16 = head
        .lines()
        .next()
        .and_then(|l| l.split_whitespace().nth(1))
        .and_then(|s| s.parse().ok())
        .ok_or("kokoro TTS: no status line")?;
    if status != 200 {
        let body = String::from_utf8_lossy(&resp[header_end..]);
        return Err(format!("kokoro TTS HTTP {status}: {}", body.trim()));
    }
    let body = &resp[header_end..];
    // uvicorn streams `/v1/audio/speech` with `Transfer-Encoding: chunked`;
    // the body is chunk-size lines + data, so it must be decoded before the
    // RIFF parser can see it.
    if head.to_ascii_lowercase().contains("transfer-encoding: chunked") {
        dechunk(body)
    } else {
        Ok(body.to_vec())
    }
}

/// Decode one HTTP chunked body (sizes are hex, data ends after the terminal
/// `0` chunk). Trailer fields after the terminal chunk are ignored.
fn dechunk(mut body: &[u8]) -> Result<Vec<u8>, String> {
    let mut out = Vec::new();
    loop {
        let line_end = body
            .iter()
            .position(|&b| b == b'\n')
            .ok_or("kokoro TTS: truncated chunk size line")?;
        let size_line = std::str::from_utf8(&body[..line_end]).unwrap_or("");
        // size may be followed by `;extensions` (RFC 9112 chunk extension).
        let size_str = size_line.split(';').next().unwrap_or("").trim();
        let size = usize::from_str_radix(size_str.trim(), 16)
            .map_err(|e| format!("kokoro TTS: bad chunk size {size_str:?}: {e}"))?;
        body = &body[line_end + 1..];
        if size == 0 {
            break;
        }
        if body.len() < size {
            return Err("kokoro TTS: chunk body truncated".into());
        }
        out.extend_from_slice(&body[..size]);
        body = &body[size..];
        if let Some(rest) = body.strip_prefix(b"\r\n") {
            body = rest;
        }
    }
    Ok(out)
}

/// One raw HTTP GET returning whether the server answered 200.
fn http_get_status(base: &str, path: &str) -> Result<bool, String> {
    let base = base.trim_start_matches("http://").trim_start_matches("https://");
    let mut stream = TcpStream::connect(base).map_err(|e| format!("kokoro TTS connect {base}: {e}"))?;
    stream
        .set_read_timeout(Some(Duration::from_millis(3_000)))
        .map_err(|e| format!("set read timeout: {e}"))?;
    let req = format!("GET {path} HTTP/1.1\r\nHost: {base}\r\nConnection: close\r\n\r\n");
    stream.write_all(req.as_bytes()).map_err(|e| format!("kokoro GET write: {e}"))?;
    let mut resp = Vec::new();
    stream.read_to_end(&mut resp).map_err(|e| format!("kokoro GET read: {e}"))?;
    let head = String::from_utf8_lossy(&resp).to_string();
    Ok(head
        .lines()
        .next()
        .and_then(|l| l.split_whitespace().nth(1))
        .map(|s| s == "200")
        .unwrap_or(false))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn wav_parse_extracts_pcm_and_rate() {
        // Build a tiny canonical mono 16-bit 24kHz WAV by hand.
        let rate = 24000u32;
        let pcm: Vec<u8> = (0..64u8).collect();
        let mut wav = Vec::new();
        let data_len = pcm.len() as u32;
        wav.extend_from_slice(b"RIFF");
        wav.extend_from_slice(&(36 + data_len).to_le_bytes());
        wav.extend_from_slice(b"WAVE");
        wav.extend_from_slice(b"fmt ");
        wav.extend_from_slice(&16u32.to_le_bytes());
        wav.extend_from_slice(&1u16.to_le_bytes()); // PCM
        wav.extend_from_slice(&1u16.to_le_bytes()); // mono
        wav.extend_from_slice(&rate.to_le_bytes());
        wav.extend_from_slice(&(rate * 2).to_le_bytes());
        wav.extend_from_slice(&2u16.to_le_bytes());
        wav.extend_from_slice(&16u16.to_le_bytes());
        wav.extend_from_slice(b"data");
        wav.extend_from_slice(&data_len.to_le_bytes());
        wav.extend_from_slice(&pcm);

        let r = VoiceRender::from_wav(wav).expect("parse");
        assert_eq!(r.sample_rate, 24000);
        assert_eq!(r.channels, 1);
        assert_eq!(r.bits_per_sample, 16);
        assert_eq!(r.pcm, pcm);
        assert_eq!(r.bytes, 44 + pcm.len());
        assert!(r.ms > 0);
    }

    #[test]
    fn wav_parse_rejects_non_riff() {
        let err = VoiceRender::from_wav(b"garbage".to_vec()).unwrap_err();
        assert!(err.contains("not a RIFF/WAVE"));
    }

    #[test]
    fn dechunk_decodes_hex_sized_chunks() {
        // exactly what uvicorn emits for a binary stream: hex size + CRLF + bytes.
        let wire = b"6\r\nhello \r\n5\r\nworld\r\n0\r\n\r\n";
        assert_eq!(dechunk(wire).unwrap(), b"hello world");
        // a chunk with extensions is still parseable; trailer after 0 ignored.
        let wire2 = b"3;foo=bar\r\nabc\r\n0\r\nX-Trailer: nope\r\n\r\n";
        assert_eq!(dechunk(wire2).unwrap(), b"abc");
        // truncated body must fail loudly, never yield partial audio.
        assert!(dechunk(b"8\r\nabcd").is_err());
    }
}