//! braid_ui_bridge — ONE router every door consumes.
//!
//! m2: the three doors (door1 lumen, door2 axiom, door3 HER) go live against
//! the same braid through a single Frontdoor router and ONE wire. Auth is
//! injected (macaroon rides every request — no second auth island); the view
//! (witness / structure / conversation) is shaped at the router, not in UI
//! code.

pub mod api;
pub mod auth;
pub mod frontdoor;
pub mod godmode;
pub mod shell;

pub use api::{AxiomView, HerWindowView, LumenView, NodeView};
pub use auth::{may_use, scope_of, verify_macaroon, VerifiedScope};
pub use frontdoor::{handler_from, register_snapshot, Door, DoorRegistration, Router};
pub use godmode::{door2_shell, mount_planned_surfaces, GodmodeTokens};
pub use shell::{door1_shell, door3_audio_shell, door3_intent_shell, door3_shell, door3_spatial_shell, door3_terminal_shell, Door1Surface};

pub const VERSION: &str = env!("CARGO_PKG_VERSION");