//! m10 — the rib: the braid_drive data-plane, mounted onto the wire.
//!
//! Every milestone before m10 drove the engine in-process. The rib pulls the
//! SAME m3 workload (200 concurrent writes from 8 strands, interleaved) out of
//! the tool-plane and pushes every write through a REAL wire
//! (`POST /v1/op` against the ONE listener). The audit m3 ran over the live
//! ledger is then re-run OVER the wire: prove every committed CID back to
//! genesis, plus a health tick and the door registry, all at the SAME address.
//! "rib" = a full data-plane workload instantiated onto the wire; a rib has no
//! side-channel — it writes and audits through the same envelope any door
//! uses.

use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

use braid_keys::SessionMacaroon;
use serde::Serialize;

use braid_wire::{http_post_raw, WireOp, WireRequest, WireResponse};

/// One rib: a data-plane wire address plus the write token its strands drive.
#[derive(Clone)]
pub struct WireRib {
    pub url: String,
    pub write_token: SessionMacaroon,
}

/// Outcomes of a concurrent wire drive.
#[derive(Debug, Clone, Serialize)]
pub struct RigOutcome {
    pub submitted: usize,
    pub ok: usize,
    pub failed: usize,
    pub cids: Vec<String>,
}

impl RigOutcome {
    pub fn all_ok(&self) -> bool {
        self.ok == self.submitted && self.failed == 0
    }
}

/// Per-node proof evidence returned from the wire.
#[derive(Debug, Clone, Serialize)]
pub struct CidProof {
    pub cid: String,
    pub verified: bool,
    pub spine_hops: u64,
}

/// The m3 audit re-run OVER the wire (m10 acceptance evidence).
#[derive(Debug, Clone, Serialize)]
pub struct WireAudit {
    pub node_count: usize,
    pub all_proven: bool,
    pub healthy: bool,
    pub registry_seen: bool,
    pub clean: bool,
    pub per_cid: Vec<CidProof>,
}

impl WireRib {
    pub fn new(url: &str, write_token: SessionMacaroon) -> Self {
        Self { url: url.to_string(), write_token }
    }

    fn post(&self, req: &WireRequest) -> WireResponse {
        let body = serde_json::to_string(req).unwrap_or_default();
        http_post_raw(&self.url, "/v1/op", &body).unwrap_or_else(WireResponse::err)
    }

    /// Drive the braid across the wire: `strands` threads × `per_strand`
    /// interleaved writes, exactly the m3 workload shape — but every braided
    /// triplet is bound by the REAL server at the ONE address, under real
    /// HTTP concurrency.
    pub fn rig_write(
        &self,
        strands: usize,
        per_strand: usize,
        op: &str,
        target_prefix: &str,
    ) -> RigOutcome {
        let deadline = Instant::now() + Duration::from_secs(60);
        let written = Arc::new(Mutex::new(Vec::<(usize, usize, String)>::new()));
        let mut handles = Vec::new();

        for s in 0..strands {
            let rib = Self { url: self.url.clone(), write_token: self.write_token.clone() };
            let written = written.clone();
            let op = op.to_string();
            let prefix = target_prefix.to_string();
            handles.push(thread::spawn(move || {
                let mut ok = 0usize;
                for i in 0..per_strand {
                    if Instant::now() > deadline {
                        break;
                    }
                    let req = WireRequest::new(
                        "wire-rib",
                        rib.write_token.clone(),
                        WireOp::Write {
                            snapshot: String::new(),
                            op: op.clone(),
                            target: format!("{}/{}-{}", prefix, s, i),
                            payload: serde_json::json!({
                                "strand": s,
                                "seq": i,
                                "source": "braid_drive wire rib",
                            }),
                        },
                    );
                    let r = rib.post(&req);
                    if r.ok {
                        ok += 1;
                        if let Some(cid) = r.data.get("cid").and_then(|c| c.as_str()) {
                            written.lock().unwrap().push((s, i, cid.to_string()));
                        }
                    }
                }
                ok
            }));
        }

        let mut ok = 0usize;
        for h in handles {
            ok += h.join().unwrap_or(0);
        }

        let mut track = written.lock().unwrap().clone();
        track.sort_by_key(|(s, i, _)| (*s, *i));
        let cids: Vec<String> = track.into_iter().map(|(_, _, c)| c).collect();
        RigOutcome {
            submitted: strands * per_strand,
            ok,
            failed: strands * per_strand - ok,
            cids,
        }
    }

    /// Re-run the m3 audit OVER the wire: prove every written CID back to
    /// genesis at the ONE address, plus a health tick and the (read-gated)
    /// door registry. `read_token` is the doorway the audit walks through —
    /// an audit is a read, never a raw log walk.
    pub fn audit_over_wire(
        &self,
        read_token: &SessionMacaroon,
        cids: &[String],
    ) -> WireAudit {
        let mut per_cid = Vec::with_capacity(cids.len());
        let mut proven = 0usize;
        for cid in cids {
            let r = self.post(&WireRequest::new(
                "wire-rib-audit",
                read_token.clone(),
                WireOp::Prove { cid: cid.clone() },
            ));
            let verified = r.data.get("verified").and_then(|v| v.as_bool()).unwrap_or(false);
            if verified {
                proven += 1;
            }
            per_cid.push(CidProof {
                cid: cid.clone(),
                verified,
                spine_hops: r
                    .data
                    .get("spine_hops")
                    .and_then(|h| h.as_u64())
                    .unwrap_or(0),
            });
        }

        let healthy = self
            .post(&WireRequest::new(
                "wire-rib-audit",
                read_token.clone(),
                WireOp::Health,
            ))
            .ok;
        let reg = self.post(&WireRequest::new(
            "wire-rib-audit",
            read_token.clone(),
            WireOp::Registry,
        ));
        let registry_seen = reg.ok && reg.data.get("default_snapshot").is_some();

        let all_proven = proven == cids.len() && !cids.is_empty();
        WireAudit {
            node_count: cids.len(),
            all_proven,
            healthy,
            registry_seen,
            clean: all_proven && healthy && registry_seen,
            per_cid,
        }
    }
}