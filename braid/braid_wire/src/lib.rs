//! braid_wire — ONE wire protocol for all three doors.
//!
//! Transport framing (HTTP/1.1, websocket-style frames), message contracts
//! (wire envelope with the braided triplet), and a HTTP surface every door
//! consumes through the same router. One wire, three doors, no second auth
//! island (macarons ride every request).

pub mod b64;
pub mod messages;
pub mod protocol;
pub mod server;

pub use messages::{WireOp, WireRequest, WireResponse};
pub use protocol::Frame;
pub use server::{http_get_bytes, http_get_raw, http_post_raw, BraidWireServer, Handler, Shell};

pub const VERSION: &str = env!("CARGO_PKG_VERSION");