//! BraidContext — the substrate's handle to the runner (HER). Adapt your
//! process in; never the other way around.

use serde_json::Value;

/// Context trait: what the braid needs from the process that hosts it.
pub trait BraidContext: Send + Sync {
    /// A tiny human-readable alias for the identity this context runs as.
    fn whoami(&self) -> String;
    /// Record an audit line into the process's own log (e.g. stdout/otel).
    fn audit_note(&self, cid: &str, message: &str);
    /// Enumerate substrate primitives a capability may reference.
    fn primitives(&self) -> Vec<String>;
    /// Snapshot a piece of process state as JSON (used by door views).
    fn snapshot(&self, key: &str) -> Value;
}

/// Mock implementation used by integration tests and the three_uis demo.
pub struct MockContext {
    identity: String,
    notes: std::sync::Mutex<Vec<String>>,
}

impl MockContext {
    pub fn new(identity: &str) -> Self {
        Self {
            identity: identity.into(),
            notes: std::sync::Mutex::new(Vec::new()),
        }
    }

    pub fn drain_notes(&self) -> Vec<String> {
        let mut n = self.notes.lock().expect("lock");
        std::mem::take(&mut *n)
    }
}

impl BraidContext for MockContext {
    fn whoami(&self) -> String {
        self.identity.clone()
    }

    fn audit_note(&self, cid: &str, message: &str) {
        self.notes
            .lock()
            .expect("lock")
            .push(format!("{cid} | {message}"));
    }

    fn primitives(&self) -> Vec<String> {
        vec!["timeline".into(), "note".into(), "tool".into(), "world".into(), "spatial".into()]
    }

    fn snapshot(&self, key: &str) -> Value {
        serde_json::json!({ "ctx": self.identity, "key": key, "at": std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0) })
    }
}