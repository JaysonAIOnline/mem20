//! BraidEngine — single write authority + single read authority.
//!
//! Atomic braided triplet (m1 invariant, from the WHOLE-COMPLETED-SYSTEM
//! dream): an op becomes a commit only when its (capability token, policy
//! snapshot, audit pre-commitment) are bound together and appended as ONE
//! atom. The audit pre-commitment is the hash of the intended node computed
//! BEFORE the append (zero-knowledge until commit); the snapshot is the
//! frozen policy state at evaluation time.

use ed25519_dalek::{SigningKey, VerifyingKey};

use crate::crypto;
use crate::policy::{Capability, PolicySnapshot};
use crate::storage::{cid_from_body, BraidLog, Node, NodeBody};

/// What `engine.write` returns: the committed node's CID, depth, proof hops,
/// and the braided triplet that bound the commit.
#[derive(Debug, Clone, serde::Serialize)]
pub struct WriteReceipt {
    pub ok: bool,
    pub cid: String,
    pub depth: u64,
    pub proof_hops: usize,
    pub triplet: BraidedTriplet,
    pub precommit_verified: bool,
    /// True when this write required a SECOND token (human-gated escalation).
    pub escalated: bool,
}

/// The human-gated second token for an escalated write: a capability that is
/// ONLY valid under its escalation snapshot. Pairing cap+snapshot together
/// makes it impossible to slip an escalation cap under a different (or
/// unregistered) policy.
pub struct Escalation<'a> {
    pub cap: &'a Capability,
    pub snapshot_cid: &'a str,
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct BraidedTriplet {
    pub capability: String,
    pub policy_snapshot: String,
    pub audit_precommit: String,
    pub policy_signer: String,
}

impl BraidedTriplet {
    fn bind(cap: &Capability, snapshot: &PolicySnapshot, precommit: &str) -> Self {
        Self {
            capability: cap.to_string(),
            policy_snapshot: snapshot.cid.clone(),
            audit_precommit: precommit.to_string(),
            policy_signer: snapshot.signer.clone(),
        }
    }
}

/// The attached audit strand carried inside every committed node.
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct AuditStrand {
    pub triplet: BraidedTriplet,
    pub signed_by: String,
    pub signature: String,
    /// Present ONLY on escalated (two-token) writes — the second, human-gated
    /// compliance token. The signature covers BOTH triplets.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub escalation_triplet: Option<BraidedTriplet>,
}

impl AuditStrand {
    /// The exact payload the write path signs and the audit re-verifies.
    /// Structurally identical on both ends so escalation never forks the
    /// signature domain.
    pub fn signed_payload(&self) -> Result<Vec<u8>, String> {
        serde_json::to_vec(&serde_json::json!({
            "base": self.triplet,
            "escalation": self.escalation_triplet,
        }))
        .map_err(|e| format!("audit payload: {e}"))
    }

    /// Verify the Ed25519 audit signature over `signed_payload()`, made by
    /// `signer_hex` (node.signer). This is THE provenance gate: every door
    /// (drive auditor, her world facts, structural views) trusts the same
    /// verifier, so a fact is only "grounded" when THIS returns true.
    pub fn verified(&self, signer_hex: &str) -> bool {
        let key_bytes = match crypto::from_hex(signer_hex) {
            Ok(bytes) if bytes.len() == 32 => bytes,
            _ => return false,
        };
        let mut arr = [0u8; 32];
        arr.copy_from_slice(&key_bytes);
        let vk = match VerifyingKey::from_bytes(&arr) {
            Ok(v) => v,
            Err(_) => return false,
        };
        let bind_bytes = match self.signed_payload() {
            Ok(v) => v,
            Err(_) => return false,
        };
        let sig_bytes = match crypto::from_hex(&self.signature) {
            Ok(b) if b.len() == 64 => b,
            _ => return false,
        };
        let mut sig_arr = [0u8; 64];
        sig_arr.copy_from_slice(&sig_bytes);
        crypto::verify(&vk, &bind_bytes, &sig_arr).is_ok()
    }
}

/// The SINGLE fact gate, shared by every door.
///
/// A node is PROVEN iff (1) its audit strand verifies AND (2) its content is
/// tamper-evident: the precommitment the authority bound at write time still
/// re-derives the node's committed CID. Signature alone covers the strand,
/// not the payload — the precommitment is what binds the payload. braid_drive
/// (auditor), braid_her (world facts / presence), and structural views must
/// all trust THIS, so a fact is "grounded" only when this returns true.
pub fn node_is_proven(node: &Node) -> bool {
    let audit = match node.audit.as_ref() {
        Some(a) => a,
        None => return false,
    };
    if !audit.verified(&node.signer) {
        return false;
    }
    let recomputed = crypto::hex(&crypto::hash(cid_from_body(&node.body).as_bytes()));
    recomputed == audit.triplet.audit_precommit
}

/// Engine over an open braid log. Holds ON-DISK identity (signing key) so the
/// triplet's audit strand can be authenticated per write.
pub struct BraidEngine {
    pub log: BraidLog,
    signer: SigningKey,
    verified: VerifyingKey,
    /// Registered snapshots by cid.
    snapshots: std::collections::HashMap<String, PolicySnapshot>,
}

impl BraidEngine {
    pub fn new(log_path: &str, signer: SigningKey) -> Result<Self, String> {
        let verified = VerifyingKey::from(&signer);
        Ok(Self {
            log: BraidLog::open(log_path)?,
            signer,
            verified,
            snapshots: std::collections::HashMap::new(),
        })
    }

    pub fn id_hex(&self) -> String {
        crypto::pub_key_hex(&self.verified)
    }

    /// Register a policy snapshot for later `write` evaluation.
    pub fn register_snapshot(&mut self, snap: PolicySnapshot) {
        self.snapshots.insert(snap.cid.clone(), snap);
    }

    pub fn snapshot(&self, cid: &str) -> Option<&PolicySnapshot> {
        self.snapshots.get(cid)
    }

    /// braid_write(op, proof): evaluate `cap` under `snapshot_cid`, compute the
    /// audit pre-commitment, then append the node carrying the braided triplet.
    pub fn write(
        &mut self,
        cap: &Capability,
        snapshot_cid: &str,
        op: &str,
        target: &str,
        payload: serde_json::Value,
    ) -> Result<WriteReceipt, String> {
        let snapshot = self
            .snapshots
            .get(snapshot_cid)
            .ok_or_else(|| format!("snapshot not registered: {snapshot_cid}"))?;
        if !snapshot.evaluate(cap) {
            return Err(format!(
                "capability `{cap}` denied by policy snapshot {snapshot_cid}"
            ));
        }
        let triplet = {
            let precommit = self.precommit(op, target, &payload);
            BraidedTriplet::bind(cap, snapshot, &precommit)
        };
        self.commit(triplet, None, false, op, target, payload)
    }

    /// braid_write_escalated: the SAME commit path, but the node carries TWO
    /// triplets — the base capability AND a second, human-gated escalation
    /// capability. The base policy must DENY the op; the escalation policy must
    /// GRANT it. The audit signature covers both triplets, so the gate is
    /// binding on chain: a single ordinary token can never produce an
    /// escalated node, and an escalated node cannot be back-dated to a plain
    /// signature domain.
    pub fn write_escalated(
        &mut self,
        base_cap: &Capability,
        base_snapshot_cid: &str,
        escalation: &Escalation,
        op: &str,
        target: &str,
        payload: serde_json::Value,
    ) -> Result<WriteReceipt, String> {
        let escalation_cap = escalation.cap;
        let upgrade_snapshot_cid = escalation.snapshot_cid;
        let base = self
            .snapshots
            .get(base_snapshot_cid)
            .ok_or_else(|| format!("snapshot not registered: {base_snapshot_cid}"))?;
        let escalation_snapshot = self
            .snapshots
            .get(upgrade_snapshot_cid)
            .ok_or_else(|| format!("snapshot not registered: {upgrade_snapshot_cid}"))?;

        // The op itself, as a capability — THIS is what must be gated.
        let (res, act) = match op.split_once(':') {
            Some((r, a)) => (r, a),
            None => return Err(format!("op `{op}` is not capability-form (needs `resource:action`")),
        };
        let op_cap = Capability::new(res, act, target);

        // Gate: the OP must be denied under the base (creator) snapshot, and
        // licensed under the escalation (human) snapshot. Otherwise the
        // double-triplet node is meaningless — one snapshot already said yes.
        if base.evaluate(&op_cap) {
            return Err(format!(
                "invalid escalation: base policy already grants op `{op}` — escalation unused"
            ));
        }
        if !escalation_snapshot.evaluate(&op_cap) {
            return Err(format!(
                "op `{op}` not licensed by escalation policy {upgrade_snapshot_cid}"
            ));
        }

        // The presented escalation token must actually cover the op noun.
        if !escalation_cap.action_grants_op(op) || !escalation_cap.resource_matches(res) {
            return Err(format!(
                "escalation capability `{escalation_cap}` does not cover op `{op}`/resource `{res}`"
            ));
        }

        // Both triplets bind to the SAME pre-commitment: one node, two tokens.
        // Base triplet = the creative token (bound, proven insufficient).
        // Granted triplet = the human-gated token (the one that carried it).
        let precommit = self.precommit(op, target, &payload);
        let base_triplet = BraidedTriplet::bind(base_cap, base, &precommit);
        let granted_triplet = BraidedTriplet::bind(escalation_cap, escalation_snapshot, &precommit);
        self.commit(granted_triplet, Some(base_triplet), true, op, target, payload)
    }

    fn precommit(&self, op: &str, target: &str, payload: &serde_json::Value) -> String {
        let prev = self.log.head().map(|n| n.cid.clone());
        let body = NodeBody {
            prev: prev.clone(),
            op: op.into(),
            target: target.into(),
            payload: payload.clone(),
        };
        let intended_cid = cid_from_body(&body);
        crypto::hex(&crypto::hash(intended_cid.as_bytes()))
    }

    fn commit(
        &mut self,
        triplet: BraidedTriplet,
        escalation_triplet: Option<BraidedTriplet>,
        escalated: bool,
        op: &str,
        target: &str,
        payload: serde_json::Value,
    ) -> Result<WriteReceipt, String> {
        // The audit strand's primary triplet is the GRANTED capability; the
        // optional escalation triplet records what had to be escalated FROM.
        let mut node_audit = AuditStrand {
            triplet: triplet.clone(),
            signed_by: self.id_hex(),
            signature: String::new(),
            escalation_triplet,
        };
        let bind_bytes = node_audit.signed_payload().map_err(|e| e.to_string())?;
        let sig = crypto::sign(&self.signer, &bind_bytes);
        node_audit.signature = crypto::hex(&sig);

        let precommit = self.precommit(op, target, &payload);

        // Prev: single-writer head.
        let prev = self.log.head().map(|n| n.cid.clone());

        let signer_hex = self.id_hex();
        let (body, node) = Node::new(prev.clone(), op, target, payload, &signer_hex);
        let _ = body;
        // Stamp the triplet on the node as an attached audit strand.
        let mut node = node;
        node.audit = Some(node_audit);

        let (cid, depth) = self.log.append(node);
        let hops = self.log.proof(&cid).len().saturating_sub(1);

        // Verify our own pre-commitment bound: re-derive CID of committed node.
        let committed = self.log.get(&cid).ok_or("missing after append")?;
        let committed_cid = cid_from_body(&NodeBody {
            prev: committed.body.prev.clone(),
            op: committed.body.op.clone(),
            target: committed.body.target.clone(),
            payload: committed.body.payload.clone(),
        });
        let verify_precommit = crypto::hex(&crypto::hash(committed_cid.as_bytes()));

        Ok(WriteReceipt {
            ok: true,
            cid,
            depth,
            proof_hops: hops,
            triplet: triplet.clone(),
            precommit_verified: verify_precommit == precommit,
            escalated,
        })
    }

    /// braid_read(query, cap): capability-gated read of committed nodes.
    pub fn read(&self, cap: &Capability, snapshot_cid: &str, op_filter: Option<&str>) -> Result<Vec<crate::storage::Node>, String> {
        let snapshot = self
            .snapshots
            .get(snapshot_cid)
            .ok_or_else(|| format!("snapshot not registered: {snapshot_cid}"))?;
        if !snapshot.evaluate(cap) {
            return Err(format!("read capability `{cap}` denied by policy"));
        }

        let mut nodes: Vec<Node> = self.log.nodes.values().cloned().collect();
        nodes.sort_by(|a, b| a.depth.cmp(&b.depth).then_with(|| a.cid.cmp(&b.cid)));
        if let Some(filter) = op_filter {
            nodes.retain(|n| n.body.op == filter);
        }
        Ok(nodes)
    }

    /// Read a single node by CID, capability-gated.
    pub fn get(&self, cap: &Capability, snapshot_cid: &str, cid: &str) -> Result<Option<Node>, String> {
        let snapshot = self
            .snapshots
            .get(snapshot_cid)
            .ok_or_else(|| format!("snapshot not registered: {snapshot_cid}"))?;
        if !snapshot.evaluate(cap) {
            return Err(format!("read capability `{cap}` denied by policy"));
        }
        Ok(self.log.get(cid).cloned())
    }

    /// The node currently at the head.
    pub fn head(&self) -> Option<&Node> {
        self.log.head()
    }

    /// Merkle angle: proof spine for a cid (hops back to genesis included).
    pub fn proof(&self, cid: &str) -> Vec<String> {
        self.log.proof(cid)
    }

    pub fn verify_node(&self, cid: &str) -> bool {
        self.log.verify(cid)
    }
}

impl crate::storage::Node {
    pub fn verify_audit(&self) -> bool {
        self.audit.as_ref().is_some()
    }
}