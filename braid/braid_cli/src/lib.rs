//! braid_cli — the m13 TERMINAL DOOR.
//!
//! A stateless, keyless read-only projection of the ONE ledger. The CLI owns
//! nothing: no engine, no keys, no state of its own — every fact it prints is
//! read over the bridge shell endpoints (/inspect, /tail, /query, /policy,
//! /prove), where every token lives on the bridge. Two identical invocations
//! against the same head print identical output; a changed head changes the
//! output because the ledger moved, not because the CLI remembers anything.

use serde::{Deserialize, Serialize};

/// The envelope every braid_cli command emits: type, payload, and a
/// timestamp — nothing else. No cursor, no config, no memory.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CliEnvelope {
    #[serde(rename = "type")]
    pub kind: String,
    pub payload: serde_json::Value,
    pub ts: u64,
}

pub const DEFAULT_BASE: &str = "http://127.0.0.1:8095";

fn now() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

fn addr_of(base: &str) -> &str {
    base.trim_start_matches("http://").trim_end_matches('/')
}

fn request(base: &str, path: &str) -> Result<serde_json::Value, String> {
    let addr = addr_of(base);
    let (status, raw) = braid_wire::http_get_raw(addr, path).map_err(|e| format!("wire: {e}"))?;
    let body = raw.split("\r\n\r\n").nth(1).unwrap_or("");
    let json: serde_json::Value = serde_json::from_str(body).map_err(|e| format!("decode: {e}"))?;
    if status != 200 {
        return Err(format!("http {status}: {json}"));
    }
    Ok(json)
}

fn wrap(json: serde_json::Value) -> Result<CliEnvelope, String> {
    let ok = json.get("ok").and_then(|v| v.as_bool()).unwrap_or(false);
    let payload = if ok {
        json.get("data").cloned().unwrap_or(serde_json::Value::Null)
    } else {
        json
    };
    Ok(CliEnvelope {
        kind: if ok { "result".into() } else { "error".into() },
        payload,
        ts: now(),
    })
}

pub fn run_inspect(base: &str) -> Result<CliEnvelope, String> {
    let json = request(base, "/inspect")?;
    wrap(json)
}

pub fn run_tail(base: &str, since: Option<&str>, limit: Option<u64>) -> Result<CliEnvelope, String> {
    let mut path = "/tail".to_string();
    let mut qs = Vec::new();
    if let Some(s) = since {
        qs.push(format!("since={s}"));
    }
    if let Some(l) = limit {
        qs.push(format!("limit={l}"));
    }
    if !qs.is_empty() {
        path.push('?');
        path.push_str(&qs.join("&"));
    }
    let json = request(base, &path)?;
    wrap(json)
}

pub fn run_query(base: &str, cap: &str) -> Result<CliEnvelope, String> {
    let addr = addr_of(base);
    let body = serde_json::json!({ "cap": cap }).to_string();
    let resp = braid_wire::http_post_raw(addr, "/query", &body)?;
    wrap(serde_json::to_value(resp).map_err(|e| format!("encode: {e}"))?)
}

pub fn run_policy(base: &str) -> Result<CliEnvelope, String> {
    let json = request(base, "/policy")?;
    wrap(json)
}

pub fn run_prove(base: &str, cid: &str) -> Result<CliEnvelope, String> {
    let json = request(base, &format!("/prove?cid={cid}"))?;
    wrap(json)
}