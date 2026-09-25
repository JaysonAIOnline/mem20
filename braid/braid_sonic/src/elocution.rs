//! Elocution — the deterministic text a committed node speaks.
//!
//! The spine does not invent words: the speech text is derived from the node's
//! own payload (`content`/`name`/`message`), falling back to its target, and
//! only then to a factual descriptor of the node itself. Same inputs → same
//! sentence, so an audio echo is reproducible from the ledger alone.

/// Cap a sentence so a single runaway payload cannot make a giant track.
const MAX_CHARS: usize = 200;

/// The sentence a node says. Deterministic; never invented.
pub fn spoken_text(payload: &serde_json::Value, cid: &str, target: &str, op: &str) -> String {
    for key in ["content", "name", "message", "text", "title"] {
        if let Some(s) = payload.get(key).and_then(|v| v.as_str()) {
            if !s.trim().is_empty() {
                return clip(s.trim());
            }
        }
    }
    if !target.trim().is_empty() {
        return clip(&format!("{target}. A {op} node in the braid."));
    }
    clip(&format!("A {op} node in the braid. {cid}."))
}

fn clip(s: &str) -> String {
    let mut out = s.trim().to_string();
    if out.chars().count() > MAX_CHARS {
        out = out.chars().take(MAX_CHARS - 3).collect();
        out.push_str("...");
    }
    if !out.ends_with(['.', '!', '?']) && !out.ends_with("...") {
        out.push('.');
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn content_wins_over_fallbacks() {
        let payload = serde_json::json!({ "content": "hello from the spine", "target": "ignored" });
        assert_eq!(spoken_text(&payload, "cid1", "obj", "write:note"), "hello from the spine.");
    }

    #[test]
    fn falls_back_to_target_fact() {
        let payload = serde_json::json!({});
        let s = spoken_text(&payload, "cid-abc", "rib/place", "write:note");
        assert!(s.contains("rib/place."), "got: {s}");
        assert!(s.contains("write:note"));
    }
}