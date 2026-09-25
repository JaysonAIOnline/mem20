//! U2 — the three door views, shaped from the SAME committed nodes.
//!
//! There is one substrate (HER) and three views onto it:
//! - door1 lumen = WITNESS (what happened — user-facing timeline)
//! - door2 axiom = STRUCTURE (how the substrate hangs together — DAG/spine)
//! - door3 HER   = CONVERSATION (the running window the human talks through)

use serde::Serialize;

use braid_core::storage::{BraidLog, Node};

/// ONE read: every door reads committed nodes; only the VIEW differs.
#[derive(Debug, Serialize)]
pub struct NodeView {
    pub cid: String,
    pub depth: u64,
    pub op: String,
    pub target: String,
    pub payload: serde_json::Value,
}

impl NodeView {
    pub fn from(n: &Node) -> Self {
        Self {
            cid: n.cid.clone(),
            depth: n.depth,
            op: n.body.op.clone(),
            target: n.body.target.clone(),
            payload: n.body.payload.clone(),
        }
    }
}

/// door1 lumen — WITNESS view: ordered timeline of what happened. No internals
/// beyond identifiers; this is the "story so far" a witness would swear to.
#[derive(Debug, Serialize)]
pub struct LumenView {
    pub door: &'static str,
    pub kind: &'static str, // "witness"
    pub timeline: Vec<NodeView>,
}

impl LumenView {
    pub fn of(nodes: &[Node]) -> Self {
        let mut v: Vec<NodeView> = nodes.iter().map(NodeView::from).collect();
        v.sort_by_key(|n| n.depth);
        Self {
            door: "door1",
            kind: "witness",
            timeline: v,
        }
    }
}

/// door2 axiom — STRUCTURE view: the DAG as edges, the Merkle-angle spine to
/// genesis, and honest integrity stats (no hidden internals, no fudge).
#[derive(Debug, Serialize)]
pub struct AxiomView {
    pub door: &'static str,
    pub kind: &'static str, // "structure"
    pub node_count: usize,
    pub head: Option<String>,
    pub edges: Vec<(String, String)>, // (child, parent)
    pub spine_to_genesis: Vec<String>, // cid chain head -> genesis
    pub verified: bool,
}

impl AxiomView {
    /// Build the full structure view: edges from prev links, plus the spine
    /// from `head` back to genesis, and a whole-log integrity check.
    pub fn of(log: &BraidLog) -> Self {
        let mut nodes: Vec<&Node> = log.nodes.values().collect();
        nodes.sort_by_key(|n| n.depth);
        let node_count = nodes.len();

        let mut edges = Vec::new();
        for n in &nodes {
            if let Some(prev) = &n.body.prev {
                edges.push((n.cid.clone(), prev.clone()));
            }
        }

        let mut spine = Vec::new();
        if let Some(head) = log.head() {
            let mut cur = Some(head.cid.clone());
            while let Some(cid) = cur {
                spine.push(cid.clone());
                cur = log.get(&cid).and_then(|n| n.body.prev.clone());
            }
        }

        let verified = log.verify_whole_log();
        AxiomView {
            door: "door2",
            kind: "structure",
            node_count,
            head: log.head().map(|h| h.cid.clone()),
            edges,
            spine_to_genesis: spine,
            verified,
        }
    }
}

/// door3 HER — CONVERSATION view: the window the human talks through. HER and
/// the human are BOTH writers (write authority is single, but the window
/// interleaves human + HER strands as one ordered conversation log).
#[derive(Debug, Serialize)]
pub struct HerWindowView {
    pub door: &'static str,
    pub kind: &'static str, // "conversation"
    pub last_cid: Option<String>,
    pub conversation: Vec<NodeView>,
}

impl HerWindowView {
    pub fn of(nodes: &[Node]) -> Self {
        let mut v: Vec<NodeView> = nodes.iter().map(NodeView::from).collect();
        v.sort_by_key(|n| n.depth);
        let last = v.last().map(|n| n.cid.clone()).or_else(|| nodes.first().map(|n| n.cid.clone()));
        Self {
            door: "door3",
            kind: "conversation",
            last_cid: last,
            conversation: v,
        }
    }
}