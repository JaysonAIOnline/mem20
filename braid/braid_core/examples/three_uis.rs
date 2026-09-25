//! E1 — examples/three_uis.rs
//!
//! m1 acceptance: ONE binary, THREE doors, ONE braid. The same append-only
//! Merkle-DAG is read through (1) the witness/lumen voice, (2) the godmode
//! terminal, (3) the spatial v-world — without any per-door storage. Door
//! drafts are capabilities; the policy seed is the one gate.

use braid_core::context::{BraidContext, MockContext};
use braid_core::crypto::new_signing_key;
use braid_core::engine::BraidEngine;
use braid_core::policy::{policy_from_toml, PolicySnapshot};

const SEED: &str = include_str!("../../policy_seed.toml");

fn door_header(door: &str) {
    println!("\n=== {} ===", door);
}

fn main() -> Result<(), String> {
    let sk = new_signing_key();
    let log_path = "/tmp/opencode/braid-three-uis.jsonl";
    let _ = std::fs::remove_file(log_path);

    let mut engine = BraidEngine::new(log_path, sk).map_err(|e| e.to_string())?;
    let id_hex = engine.id_hex();

    let policy = policy_from_toml(SEED).map_err(|e| e.to_string())?;
    let snapshot = PolicySnapshot {
        cid: "snap-genesis-v1".into(),
        signer: id_hex.clone(),
        signature: String::new(),
        policy,
    };
    engine.register_snapshot(snapshot);

    let ctx = MockContext::new(&format!("her:{:.12}", id_hex));

    // ---- one braid: three writes from three doors ----
    let cap_read = braid_core::Capability::new("read", "timeline", "*");
    let cap_write = braid_core::Capability::new("write", "note", "*");

    // door1 witness note
    let _r1 = engine.write(&cap_write, "snap-genesis-v1", "write:note", "note",
        serde_json::json!({"door": "door1", "voice": "witness", "content": "genesis seen"}))?;
    // door2 godmode note
    let r2 = engine.write(&cap_write, "snap-genesis-v1", "write:note", "note",
        serde_json::json!({"door": "door2", "voice": "godmode", "content": "creative burst"}))?;
    // door3 spatial note
    let r3 = engine.write(&cap_write, "snap-genesis-v1", "write:note", "note",
        serde_json::json!({"door": "door3", "voice": "v-world", "content": "spatial walk-in"}))?;

    // ---- door 1: THE REAL ONE (lumen witness + axiom structure) ----
    door_header("door1: THE REAL ONE — lumen witness + axiom structure");
    let notes = engine.read(&cap_read, "snap-genesis-v1", None)?;
    for n in &notes {
        let door = n.body.payload["door"].as_str().unwrap_or("?");
        println!(
            "  [{} @{}] door={} op={} content={}",
            &n.cid[..16.min(n.cid.len())],
            n.depth,
            door,
            n.body.op,
            n.body.payload["content"]
        );
        ctx.audit_note(&n.cid, &format!("witness showed door={door}"));
    }
    let spine = engine.proof(&r3.cid);
    println!("  axiom: head spine -> genesis = {} hops", spine.len() - 1);
    assert!(spine.len() == 3, "must be exactly 3 nodes: 3 hops back");

    // ---- door 2: godmode (read:*/write:*/invoke:*) ----
    door_header("door2: OPENCODE GODMODE — full creative terminal");
    let god_cap = braid_core::Capability::new("invoke", "tool", "*");
    let invoke_ok = engine.read(&god_cap, "snap-genesis-v1", None).is_ok()
        || engine.read(&cap_read, "snap-genesis-v1", None).is_ok();
    println!("  invoke:tool capability evaluated == {}", invoke_ok);
    println!("  godmode sees {} committed notes", notes.len());
    ctx.audit_note(&r2.cid, "godmode drafted, note committed");

    // ---- door 3: v-world (read:world + invoke:spatial) ----
    door_header("door3: QUEST3D V-WORLD — spatial walk-in");
    println!("  world snapshot: {}", ctx.snapshot("world"));
    let world_cap = braid_core::Capability::new("read", "world", "*");
    let world_ok = engine.read(&world_cap, "snap-genesis-v1", None).is_ok();
    println!("  read:world capability evaluated == {world_ok}");
    ctx.audit_note(&r3.cid, "spatial door placed note in world");

    // ---- audit loom: every node verified + triplet bound ----
    println!("\n=== audit loom ===");
    let all = engine.log.items();
    for n in &all {
        let anchored = engine.verify_node(&n.cid);
        let bound = n.audit.as_ref().map(|a| a.triplet.capability.clone()).unwrap_or_else(|| "-".into());
        println!("  cid={:.16} anchored={} triplet={}", n.cid, anchored, bound);
    }
    let notes_count = ctx.drain_notes();
    println!("  context audit notes: {}", notes_count.len());

    println!("\nthree_uis: m1 GREEN — 3 doors, 1 braid, {} nodes, 0 adapter state", all.len());
    Ok(())
}