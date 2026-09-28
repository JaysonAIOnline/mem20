//! Content addressing must survive a write/read cycle for every payload.
//!
//! Regression test for a real defect: serde_json's default float parser is a
//! fast *approximate* `significand as f64 * POW10[exp]`, off by up to 1 ULP.
//! A commit receives its f64 bit-exact from the caller, so the CID is hashed
//! over one set of bytes; a later read recovers the value from decimal text and
//! gets a neighbouring double, so the CID can never be re-derived. Nodes
//! carrying such a float failed `verify()` forever while their content and
//! signature were perfectly intact — 84 of 622 records in the live ledger.
//!
//! The fix is serde_json's `float_roundtrip` feature (correctly-rounded
//! parsing). These tests fail if it is ever dropped.

use braid_core::storage::{BraidLog, Node};

fn tmp_log(tag: &str) -> String {
    let path = format!(
        "/tmp/opencode/braid-canon-{}-{}.jsonl",
        tag,
        std::process::id()
    );
    let _ = std::fs::remove_file(&path);
    path
}

/// Values that the approximate parser gets wrong, taken from the real ledger.
const HARD_FLOATS: &[f64] = &[
    1789913903.6339803,
    1789913903.6334846,
    0.30000000000000004, // 0.1 + 0.2
    0.3333333333333333,  // 1.0 / 3.0
    2.220446049250313e-17, // f64::MIN_POSITIVE / 2
    9007199254740992.0,     // 2^53, the last exactly-representable integer
];

#[test]
fn float_payloads_re_derive_after_a_reload() {
    let path = tmp_log("floats");

    // Write: hand the node a bit-exact f64, exactly as the Python caller does.
    {
        let mut log = BraidLog::open(&path).unwrap();
        let mut prev: Option<String> = None;
        for (i, value) in HARD_FLOATS.iter().enumerate() {
            let (_, node) = Node::new(
                prev.clone(),
                "write:fact",
                &format!("hard:{i}"),
                serde_json::json!({ "at": value, "i": i }),
                "test-signer",
            );
            let (cid, _) = log.append(node);
            prev = Some(cid);
        }
    }

    // Read back cold: every CID must still re-derive from the stored body.
    // This is the exact property that failed before the fix.
    let log = BraidLog::open(&path).unwrap();
    let stored = log.items();
    assert_eq!(stored.len(), HARD_FLOATS.len());
    for (i, value) in HARD_FLOATS.iter().enumerate() {
        let node = &stored[i];
        assert_eq!(node.body.target, format!("hard:{i}"));
        let at = node.body.payload["at"].as_f64().expect("float survived the file");
        assert_eq!(
            at.to_bits(),
            value.to_bits(),
            "float {value:?} lost precision on the way to disk"
        );
        assert!(
            log.verify(&node.cid),
            "float {value:?} did not re-derive after a reload"
        );
    }

    assert!(log.verify_whole_log(), "whole-log integrity must hold");
    let _ = std::fs::remove_file(&path);
}

#[test]
fn whole_log_verifies_after_many_float_writes() {
    let path = tmp_log("chain");
    let mut log = BraidLog::open(&path).unwrap();
    let mut prev: Option<String> = None;
    for i in 0..64 {
        let value = 1789913903.6339803_f64 + i as f64;
        let (_, node) = Node::new(
            prev.clone(),
            "write:dream_iteration",
            &format!("dream:{i}"),
            serde_json::json!({
                "artifact": "x".repeat(i + 1),
                "fidelity": 90.5,
                "omission": 0.1 + i as f64,
                "at": value,
            }),
            "test-signer",
        );
        let (cid, _) = log.append(node);
        prev = Some(cid);
    }
    let written = log.items().len();
    assert_eq!(written, 64);
    assert!(
        log.verify_whole_log(),
        "a chain of float-bearing writes must verify in-process"
    );

    // And again after a cold reopen, which is where the defect used to surface.
    drop(log);
    let reopened = BraidLog::open(&path).unwrap();
    assert!(
        reopened.verify_whole_log(),
        "float-bearing chain must still verify after a reload"
    );
    let _ = std::fs::remove_file(&path);
}

#[test]
fn a_plain_integer_payload_is_unaffected() {
    let path = tmp_log("int");
    let mut log = BraidLog::open(&path).unwrap();
    let mut prev: Option<String> = None;
    for i in 0..8 {
        let (_, node) = Node::new(
            prev.clone(),
            "write:fact",
            &format!("n:{i}"),
            serde_json::json!({ "depth": i, "chars": i * 100 }),
            "test-signer",
        );
        let (cid, _) = log.append(node);
        prev = Some(cid);
    }
    drop(log);
    let reopened = BraidLog::open(&path).unwrap();
    assert!(reopened.verify_whole_log());
    let _ = std::fs::remove_file(&path);
}
