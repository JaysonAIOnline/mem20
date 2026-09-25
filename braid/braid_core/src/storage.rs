//! Braid storage: append-only Merkle-DAG log with proofs.
//!
//! Every record is a node in a Merkle DAG. A node binds to its parent by CID:
//!   node = { cid: br<payload>, prev: <parent cid | null>, kind/data/triplet ... }
//! The meaning of `prev` is "what this node extends", exactly like a DAG
//! branch that can fork. The witness view asks for the Merkle angle: how many
//! hops back to genesis this node sits at — that is the "proof".

use std::collections::HashMap;
use std::fs::{File, OpenOptions};
use std::io::{BufRead, BufReader, Write};
use std::path::Path;

use serde::{Deserialize, Serialize};

use crate::crypto::cid;

/// Canonical JSON body handed to content addressing. Kept separate from the
/// serialized node so the CID is computed over fields BEFORE `cid` exists.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NodeBody {
    pub prev: Option<String>,
    pub op: String,
    pub target: String,
    pub payload: serde_json::Value,
}

/// A committed node in the braid.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Node {
    pub cid: String,
    #[serde(flatten)]
    pub body: NodeBody,
    /// Hops back to genesis (computed at commit; mirrors proof spine length).
    pub depth: u64,
    pub signer: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub audit: Option<crate::engine::AuditStrand>,
}

impl Node {
    pub fn new(prev: Option<String>, op: &str, target: &str,
               payload: serde_json::Value, signer: &str) -> (NodeBody, Self) {
        let body = NodeBody {
            prev,
            op: op.into(),
            target: target.into(),
            payload,
        };
        let cid = cid_from_body(&body);
        let depth = 0; // set by the log on append
        let node = Node {
            cid,
            body: body.clone(),
            depth,
            signer: signer.into(),
            audit: None,
        };
        (body, node)
    }
}

pub fn cid_from_body(body: &NodeBody) -> String {
    // canonical serialization (serde on the struct, not a Value) for stability
    let canonical = serde_json::to_string(body).expect("serialize body");
    cid(canonical.as_bytes())
}

/// Append-only Merkle-DAG storage backend (JSON Lines file on disk).
pub struct BraidLog {
    pub nodes: HashMap<String, Node>,
    parents: HashMap<String, Option<String>>,
    path: std::path::PathBuf,
}

impl BraidLog {
    /// Open (create if missing) a braid log at `path`.
    pub fn open(path: impl AsRef<Path>) -> Result<Self, String> {
        let p = path.as_ref().to_path_buf();
        if let Some(dir) = p.parent() {
            std::fs::create_dir_all(dir).map_err(|e| format!("create dir: {e}"))?;
        }
        let mut log = BraidLog {
            nodes: HashMap::new(),
            parents: HashMap::new(),
            path: p.clone(),
        };
        if p.exists() {
            let f = File::open(&path).map_err(|e| format!("open log: {e}"))?;
            let reader = BufReader::new(f);
            for (i, line) in reader.lines().enumerate() {
                let line = line.map_err(|e| format!("read log line {i}: {e}"))?;
                if line.trim().is_empty() {
                    continue;
                }
                let node: Node =
                    serde_json::from_str(&line).map_err(|e| format!("parse line {i}: {e}"))?;
                let prev = node.body.prev.clone();
                log.parents.insert(node.cid.clone(), prev);
                log.nodes.insert(node.cid.clone(), node);
            }
        }
        Ok(log)
    }

    /// Append a node; returns its CID and the new depth.
    pub fn append(&mut self, node: Node) -> (String, u64) {
        let depth = node.body.prev.as_ref().map_or(0, |p| {
            self.nodes.get(p).map(|n| n.depth + 1).unwrap_or(1)
        });
        let mut node = node;
        node.depth = depth;
        let cid = node.cid.clone();
        self.parents.insert(cid.clone(), node.body.prev.clone());
        self.nodes.insert(cid.clone(), node.clone());

        // persist
        let mut f = OpenOptions::new()
            .create(true)
            .append(true)
            .open(&self.path)
            .expect("open log append");
        let line = serde_json::to_string(&node).expect("serialize node");
        let _ = writeln!(f, "{line}");

        (cid, depth)
    }

    pub fn get(&self, cid: &str) -> Option<&Node> {
        self.nodes.get(cid)
    }

    pub fn head(&self) -> Option<&Node> {
        // deepest committed node (ties -> lexicographically largest cid)
        self.nodes
            .values()
            .max_by(|a, b| a.depth.cmp(&b.depth).then_with(|| a.cid.cmp(&b.cid)))
    }

    pub fn genesis(&self) -> Option<&Node> {
        self.nodes.values().find(|n| n.body.prev.is_none())
    }

    /// Merkle angle proof: CID spine from `cid` back to genesis (inclusive).
    pub fn proof(&self, cid: &str) -> Vec<String> {
        let mut spine = Vec::new();
        let mut cur = self.nodes.get(cid).map(|n| n.cid.clone());
        let mut guard = 0;
        while let Some(id) = cur {
            spine.push(id.clone());
            cur = self.parents.get(&id).cloned().flatten();
            guard += 1;
            if guard > 1_000_000 {
                break;
            }
        }
        spine
    }

    pub fn len(&self) -> usize {
        self.nodes.len()
    }

    pub fn is_empty(&self) -> bool {
        self.nodes.is_empty()
    }

    /// Verify a stored node's CID was really derived from its body.
    pub fn verify(&self, cid: &str) -> bool {
        match self.nodes.get(cid) {
            Some(node) => {
                // rebuild body-only and compare CID
                let rebuilt = cid_from_body(&NodeBody {
                    prev: node.body.prev.clone(),
                    op: node.body.op.clone(),
                    target: node.body.target.clone(),
                    payload: node.body.payload.clone(),
                });
                rebuilt == *cid
            }
            None => false,
        }
    }

    /// All nodes, ordered by depth then cid (stable append order).
    pub fn items(&self) -> Vec<Node> {
        let mut v: Vec<Node> = self.nodes.values().cloned().collect();
        v.sort_by(|a, b| a.depth.cmp(&b.depth).then_with(|| a.cid.cmp(&b.cid)));
        v
    }

    /// Whole-log integrity: every node's CID re-derives from its body AND
    /// every non-genesis node's `prev` points at an existing node.
    pub fn verify_whole_log(&self) -> bool {
        let mut valid_cids = true;
        for node in self.nodes.values() {
            if !self.verify(&node.cid) {
                valid_cids = false;
                break;
            }
        }
        if !valid_cids {
            return false;
        }
        for node in self.nodes.values() {
            if let Some(prev) = &node.body.prev {
                if !self.nodes.contains_key(prev) {
                    return false;
                }
            }
        }
        true
    }

    /// Iterator hook used by read/audit paths.
    pub fn items_for_audit(&self) -> Vec<Node> {
        self.items()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tmp() -> String {
        format!("/tmp/opencode/braid-test-{}.jsonl", std::process::id())
    }

    #[test]
    fn append_and_proof_spine() {
        let path = tmp();
        let _ = std::fs::remove_file(&path);
        let mut log = BraidLog::open(&path).unwrap();

        let mk = |prev: Option<String>, op: &str, payload: serde_json::Value| {
            Node::new(prev, op, "note", payload, "alice")
        };

        let (_b0, n0) = mk(None, "write:note", serde_json::json!({"t": "genesis"}));
        let (c0, d0) = log.append(n0);
        assert_eq!(d0, 0);

        let (_b1, n1) = mk(Some(c0.clone()), "write:note", serde_json::json!({"t": "two"}));
        let (c1, d1) = log.append(n1);
        assert_eq!(d1, 1);

        let (_b2, n2) = mk(Some(c1.clone()), "write:note", serde_json::json!({"t": "three"}));
        let (c2, d2) = log.append(n2);
        assert_eq!(d2, 2);

        let spine = log.proof(&c2);
        assert_eq!(spine.len(), 3); // three hops: c2 -> c1 -> c0
        assert_eq!(spine[0], c2);
        assert_eq!(spine[2], c0);

        assert!(log.verify(&c2));
        assert_eq!(log.head().unwrap().cid, c2);

        let _ = std::fs::remove_file(&path);
    }
}