//! braid_core — the Braid substrate (m1).
//!
//! One consciousness, three doors. The substrate is HER — one running
//! process. Single write authority: every mutation enters through
//! `engine.write` (braid_write). Single read authority: every query enters
//! through `engine.read` / `engine.get` (braid_read).

pub mod context;
pub mod crypto;
pub mod engine;
pub mod intent;
pub mod policy;
pub mod storage;

pub use context::{BraidContext, MockContext};
pub use engine::{AuditStrand, BraidEngine, BraidedTriplet, WriteReceipt};
pub use intent::{FulfilledBy, IntentRef, IntentStatus, IntentStrand, IntentView};
pub use policy::{Capability, Policy, PolicyRule, PolicySnapshot};
pub use storage::{BraidLog, Node, NodeBody};

pub const VERSION: &str = env!("CARGO_PKG_VERSION");