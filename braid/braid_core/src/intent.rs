//! IntentStrand (m12) — the spec-forth strand, now REAL on the braid.
//!
//! The final dream surfaced a speculative FOURTH strand: an intent thread that
//! projects what the user might want next. m1 froze this module as a stub and
//! the build rules were explicit — nothing speculative enters motion until
//! atomic braided triplets are proven end-to-end (m3). Triplets have been
//! proven on every strand since m4, so m12 honors the promise: the intent
//! strand is now a REAL committed strand on the ONE ledger.
//!
//! Honest semantics — no fake speculation: an intent is an ordinary braided
//! node of op `write:intent`, committed through the same single-write path as
//! every write. Its payload carries the `desire`, a `target` (the object of
//! the desire), optional `context`, and a `weight`. An intent stays OPEN until
//! a LATER committed, proven node explicitly references it through
//! `payload.fulfills == <intent cid>` — the fulfilling node is the actual
//! work (a note, a world object, a placed fact), so fulfillment is honest
//! recorded motion, never an imagined run. Every intent and every resolution
//! ships with live provenance (`signature_ok`), exactly like a world fact.

use serde::Serialize;

use crate::engine::{node_is_proven, BraidEngine, WriteReceipt};
use crate::policy::Capability;

/// The op every intent commits under. A resource:action capability, so the
/// policy authority that licenses normal writes also licenses the strand.
pub const INTENT_OP: &str = "write:intent";

/// The payload key a resolving node uses to point back at the intent it
/// fulfills. Resolution is a STRUCTURAL fact about the ledger — no hidden
/// registry, no second authority.
pub const FULFILLS_KEY: &str = "fulfills";

/// Lifecycle of a committed, proven intent.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum IntentStatus {
    /// Committed and proven, but no later proven node has claimed it yet.
    Open,
    /// A later proven node carries `payload.fulfills == this intent's cid`.
    Resolved,
}

/// Which committed node fulfilled an intent (its on-chain receipt).
#[derive(Debug, Clone, Serialize)]
pub struct FulfilledBy {
    pub cid: String,
    pub depth: u64,
    pub op: String,
}

/// One committed intent + its live provenance, the way the walk-in sees it.
#[derive(Debug, Clone, Serialize)]
pub struct IntentRef {
    pub cid: String,
    pub depth: u64,
    pub target: String,
    pub desire: String,
    #[serde(skip_serializing_if = "serde_json::Value::is_null")]
    pub context: serde_json::Value,
    pub weight: u64,
    pub signer: String,
    /// The capability + frozen snapshot bound into this intent's triplet.
    pub capability: String,
    pub snapshot: String,
    /// The verifier's live answer, computed here — never trusted from the log.
    pub provenance_ok: bool,
    pub status: IntentStatus,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub fulfilled_by: Option<FulfilledBy>,
}

/// The strand projection: every committed intent of the ONE ledger, plus the
/// aggregate the walk-in header shows. Derived from a cap-gated `braid_read`
/// — the intent strand is read through the exact same authority as every other
/// strand.
#[derive(Debug, Clone, Serialize)]
pub struct IntentView {
    /// Every `write:intent` node the read could see.
    pub submitted: usize,
    /// Proven intents with no proven fulfiller.
    pub open: usize,
    /// Proven intents with a proven fulfiller.
    pub resolved: usize,
    /// Back-compat name for the walk-in: open intents awaiting fulfillment.
    pub pending_count: usize,
    pub intents: Vec<IntentRef>,
}

/// The strand handle. Stateless — the ledger is the source of truth.
#[derive(Debug, Clone, Copy, Default)]
pub struct IntentStrand;

impl IntentStrand {
    /// Compose the canonical payload of an intent node.
    pub fn carrying(
        desire: impl Into<String>,
        target: impl Into<String>,
        context: serde_json::Value,
        weight: u64,
    ) -> serde_json::Value {
        serde_json::json!({
            "desire": desire.into(),
            "target": target.into(),
            "context": context,
            "weight": weight,
        })
    }

    /// Attach a `fulfills` reference to a payload, declaring that the write
    /// fulfills the given intent cid. The reference is an ordinary payload
    /// field on an ordinary braided node — resolution is committed motion.
    pub fn intentional(payload: serde_json::Value, intent_cid: &str) -> serde_json::Value {
        let mut v = payload;
        if v.is_object() {
            v[FULFILLS_KEY] = serde_json::json!(intent_cid);
        } else {
            v = serde_json::json!({ "content": v, FULFILLS_KEY: intent_cid });
        }
        v
    }

    /// Commit an intent node through the single-write authority: braided
    /// triplet (cap token + frozen policy snapshot + audit pre-commitment),
    /// like every str written. Returns the receipt or an honest `Err`.
    pub fn submit(
        engine: &mut BraidEngine,
        cap: &Capability,
        snapshot_cid: &str,
        desire: impl Into<String>,
        target: impl Into<String>,
        context: serde_json::Value,
        weight: u64,
    ) -> Result<WriteReceipt, String> {
        let target = target.into();
        let desire = desire.into();
        engine.write(
            cap,
            snapshot_cid,
            INTENT_OP,
            &target,
            Self::carrying(desire, &target, context, weight),
        )
    }

    /// Project the strand from the cap-gated ledger. Reads go through
    /// `braid_read` (same frozen snapshot), never a raw log walk.
    pub fn from_ledger(engine: &BraidEngine, cap: &Capability, snapshot_cid: &str) -> IntentView {
        let intents = engine.read(cap, snapshot_cid, Some(INTENT_OP)).unwrap_or_default();
        let all = engine.read(cap, snapshot_cid, None).unwrap_or_default();

        // Which proven node claims which intent cid. Only PROVEN resolvers
        // resolve — a reference on a tampered or unsigned node changes nothing.
        let mut resolvers: std::collections::HashMap<String, FulfilledBy> =
            std::collections::HashMap::new();
        for n in all.iter() {
            if !node_is_proven(n) {
                continue;
            }
            let fulfills = match n.body.payload.get(FULFILLS_KEY).and_then(serde_json::Value::as_str) {
                Some(c) => c.to_string(),
                None => continue,
            };
            resolvers.entry(fulfills).or_insert(FulfilledBy {
                cid: n.cid.clone(),
                depth: n.depth,
                op: n.body.op.clone(),
            });
        }

        let mut submitted = 0usize;
        let mut open = 0usize;
        let mut resolved = 0usize;
        let mut refs = Vec::with_capacity(intents.len());
        for n in intents.iter() {
            submitted += 1;
            let proven = node_is_proven(n);
            let fulfilled_by = proven.then(|| resolvers.get(&n.cid).cloned()).flatten();
            let status = if fulfilled_by.is_some() {
                resolved += 1;
                IntentStatus::Resolved
            } else {
                open += usize::from(proven);
                IntentStatus::Open
            };
            let capability = n
                .audit
                .as_ref()
                .map(|a| a.triplet.capability.clone())
                .unwrap_or_default();
            let snapshot = n
                .audit
                .as_ref()
                .map(|a| a.triplet.policy_snapshot.clone())
                .unwrap_or_default();
            refs.push(IntentRef {
                cid: n.cid.clone(),
                depth: n.depth,
                target: n.body.target.clone(),
                desire: n
                    .body
                    .payload
                    .get("desire")
                    .and_then(serde_json::Value::as_str)
                    .unwrap_or("(no desire field)")
                    .to_string(),
                context: n
                    .body
                    .payload
                    .get("context")
                    .cloned()
                    .unwrap_or(serde_json::Value::Null),
                weight: n
                    .body
                    .payload
                    .get("weight")
                    .and_then(serde_json::Value::as_u64)
                    .unwrap_or(0),
                signer: n.signer.clone(),
                capability,
                snapshot,
                provenance_ok: proven,
                status,
                fulfilled_by,
            });
        }

        IntentView {
            submitted,
            open,
            resolved,
            pending_count: open,
            intents: refs,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::crypto::new_signing_key;
    use crate::policy::{policy_from_toml, PolicySnapshot};

    const GENESIS: &str = r#"
name = "genesis-intent-unit"
version = 1

[[rules]]
allow = true
capability = "read:*:*"

[[rules]]
allow = true
capability = "write:intent:*"

[[rules]]
allow = true
capability = "write:note:*"

[[rules]]
allow = false
capability = "admin:*:*"
"#;

    fn boot() -> (BraidEngine, Capability, Capability) {
        let path = format!(
            "/tmp/opencode/braid-intent-unit-{}-{}.jsonl",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        );
        let _ = std::fs::remove_file(&path);
        let sk = new_signing_key();
        let engine_id = crate::crypto::pub_key_hex(&ed25519_dalek::VerifyingKey::from(&sk));
        let mut engine = BraidEngine::new(&path, sk).expect("engine boots");
        engine.register_snapshot(PolicySnapshot {
            cid: "snap-genesis".into(),
            signer: engine_id,
            signature: String::new(),
            policy: policy_from_toml(GENESIS).expect("genesis"),
        });
        let read = Capability::new("read", "*", "*");
        let intent = Capability::new("write", "intent", "*");
        (engine, read, intent)
    }

    #[test]
    fn desires_commit_as_proven_open_nodes() {
        let (mut engine, read, intent) = boot();
        let r = IntentStrand::submit(
            &mut engine, &intent, "snap-genesis",
            "the sundial resonates at exactly one address",
            "place/intent-sundial",
            serde_json::json!({ "strand": "m12" }),
            1,
        ).expect("intent commits");
        assert!(r.ok && r.precommit_verified);

        let v = IntentStrand::from_ledger(&engine, &read, "snap-genesis");
        assert_eq!(v.submitted, 1);
        assert_eq!(v.open, 1);
        assert_eq!(v.resolved, 0);
        assert_eq!(v.pending_count, 1);
        assert_eq!(v.intents.len(), 1);
        let i = &v.intents[0];
        assert_eq!(i.cid, r.cid);
        assert!(i.provenance_ok, "a committed intent is a proven node");
        assert_eq!(i.status, IntentStatus::Open);
        assert_eq!(i.desire, "the sundial resonates at exactly one address");
        assert_eq!(i.target, "place/intent-sundial");
        assert_eq!(i.weight, 1);
        assert_eq!(i.capability, "write:intent:*");
        assert_eq!(i.snapshot, "snap-genesis");
        assert!(i.fulfilled_by.is_none());
    }

    #[test]
    fn a_later_proven_write_with_fulfills_resolves_the_intent() {
        let (mut engine, read, intent) = boot();
        let submitted = IntentStrand::submit(
            &mut engine, &intent, "snap-genesis",
            "place the sundial",
            "place/intent-sundial",
            serde_json::Value::Null,
            1,
        ).expect("intent commits");

        // The fulfilling work is an ordinary note node that references the
        // intent by cid. It is real motion, not pretend execution.
        let note = Capability::new("write", "note", "*");
        let payload = IntentStrand::intentional(serde_json::json!({ "content": "sundial placed" }), &submitted.cid);
        let done = engine.write(&note, "snap-genesis", "note", "place/intent-sundial", payload).expect("resolve commits");
        assert_ne!(done.cid, submitted.cid);

        let v = IntentStrand::from_ledger(&engine, &read, "snap-genesis");
        assert_eq!(v.submitted, 1);
        assert_eq!(v.open, 0);
        assert_eq!(v.resolved, 1);
        assert_eq!(v.pending_count, 0);
        let i = &v.intents[0];
        assert_eq!(i.status, IntentStatus::Resolved);
        let fb = i.fulfilled_by.as_ref().expect("has fulfiller");
        assert_eq!(fb.cid, done.cid);
        assert_eq!(fb.depth, done.depth);
        assert_eq!(fb.op, "note");
    }

    #[test]
    fn an_unproven_resolver_never_resolves_an_intent() {
        // The write path always binds an audit strand, so nothing committed
        // through the engine is unsigned. But the projection must also not
        // credit an injected / tampered resolver: a raw node without an audit
        // strand that points `fulfills` at an intent leaves the intent OPEN —
        // resolution is only ever claimed by PROVEN work.
        let (mut engine, read, intent) = boot();
        let submitted = IntentStrand::submit(
            &mut engine, &intent, "snap-genesis",
            "place the sundial",
            "place/intent-sundial",
            serde_json::Value::Null,
            1,
        ).expect("intent commits");

        // Inject an unsigned node by hand (the tamper case the fact gate
        // excludes): it references the intent but carries no audit strand.
        let prev = engine.log.head().map(|n| n.cid.clone());
        let (_b, raw) = crate::storage::Node::new(
            prev,
            "note",
            "place/intent-sundial",
            serde_json::json!({ "content": "fake fulfill", "fulfills": submitted.cid }),
            "forged-signer",
        );
        let (raw_cid, _) = engine.log.append(raw);
        assert!(raw_cid.len() >= 8);

        let v = IntentStrand::from_ledger(&engine, &read, "snap-genesis");
        assert_eq!(v.submitted, 1, "the intent is still the only write:intent node");
        assert_eq!(v.open, 1, "the forged resolver is not proven — intent stays open");
        assert_eq!(v.resolved, 0);
        assert!(v.intents[0].fulfilled_by.is_none());
        assert!(v.intents[0].provenance_ok);
    }
}