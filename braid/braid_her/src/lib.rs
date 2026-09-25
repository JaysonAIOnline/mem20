//! braid_her — door3 (quest3d V-WORLD). The spatial walk-in on PROVEN facts.
//!
//! m5 core = world facts ARE grounded ledger facts. A fact enters the world
//! only when its audit signature verifies (`AuditStrand::verified`); every
//! `WorldNode` ships its on-chain provenance so the walk-in carries its own
//! proof. The window (D3.1) is a resonance stream over the braid spine, not
//! chat bubbles; presence (D3.4) is derived from ledger identities, never
//! configuration.
//!
//! All reads pass through `braid_read` — one read authority, one cap gate.

pub mod presence;
pub mod window;
pub mod world;

pub use presence::{AgentPresence, Presence};
pub use window::{Echo, ResonanceWindow};
pub use world::{FactProvenance, WorldNode, WorldScene};