//! U3 — auth injection.
//!
//! There is no second auth island: every wire request carries the braid
//! session macaroon, and the router verifies it against the door's registered
//! DID before ANY capability is evaluated. The caveats ARE the capability
//! scopes the engine evaluates — the auth layer and the policy layer share
//! one token.

use braid_core::policy::Capability;
use braid_keys::SessionMacaroon;

/// What a verified request turns into: the door identity that owns the
/// request, plus the capability scope carried inside the macaroon.
#[derive(Debug, Clone)]
pub struct VerifiedScope {
    pub door: String,
    pub location: String,
    pub did: String,
    pub capability: Capability,
}

/// Verify a presented macaroon against a door's registered DID + location.
///
/// Returns `Err` when the token is missing (no second island — the browser/
/// UI path has no anonymous fallback), wrong key, tampered signature, or a
/// misbound location.
pub fn verify_macaroon(
    macaroon: &SessionMacaroon,
    door_did: &str,
    expected_location: &str,
) -> Result<(), String> {
    if macaroon.caveats.is_empty() {
        return Err("macaroon carries no capability caveat — refusing (no anonymous door)".into());
    }
    if !macaroon.verify(door_did, expected_location) {
        return Err("macaroon failed verification against door identity".into());
    }
    Ok(())
}

/// Extract the capability scope a verified macaroon grants. The FIRST caveat
/// names the operation capability; the engine's own policy evaluation is the
/// final gate (macaroon valid != policy allows), so this is scoping, not
/// authorization.
pub fn scope_of(macaroon: &SessionMacaroon, door: &str, did: &str) -> VerifiedScope {
    println!(
        "[braid_ui_bridge] {door} -> macaroon({}) location={} caveats={:?}",
        &did[..did.len().min(24)],
        macaroon.location,
        macaroon.caveats
    );
    VerifiedScope {
        door: door.into(),
        location: macaroon.location.clone(),
        did: did.into(),
        capability: Capability::parse(&macaroon.caveats[0]),
    }
}

/// True when the door is allowed to USE the road (auth) and the requested op
/// is inside the token's capability (the policy layer re-checks against the
/// frozen snapshot at write time — never trust a live token alone).
pub fn may_use(scope: &VerifiedScope, requested: &str) -> bool {
    let requested_cap = Capability::parse(requested);
    scope.capability.grants(&requested_cap)
}

#[cfg(test)]
mod tests {
    use super::*;
    use braid_keys::did_key;
    use ed25519_dalek::SigningKey;
    use rand::rngs::OsRng;

    #[test]
    fn macaroon_verifies_and_scopes() {
        let sk = SigningKey::generate(&mut OsRng);
        let did = did_key(&ed25519_dalek::VerifyingKey::from(&sk));
        let m = SessionMacaroon::issue("door1", "s1", &["read:timeline:*"], &sk);

        verify_macaroon(&m, &did, "door1").expect("valid mac verifies");
        let scope = scope_of(&m, "door1", &did);
        assert!(may_use(&scope, "read:timeline"), "granted read");
        assert!(!may_use(&scope, "write:note"), "token does not grant write");
    }

    #[test]
    fn tampered_or_wrong_identity_is_refused() {
        let sk = SigningKey::generate(&mut OsRng);
        let did = did_key(&ed25519_dalek::VerifyingKey::from(&sk));
        let m = SessionMacaroon::issue("door1", "s1", &["read:timeline:*"], &sk);

        // wrong location
        assert!(verify_macaroon(&m, &did, "door2").is_err());
        // foreign did
        let sk2 = SigningKey::generate(&mut OsRng);
        let did2 = did_key(&ed25519_dalek::VerifyingKey::from(&sk2));
        assert!(verify_macaroon(&m, &did2, "door1").is_err());
        // tampered caveat
        let mut mt = m.clone();
        mt.caveats[0] = "write:note:*".into();
        assert!(verify_macaroon(&mt, &did, "door1").is_err());
    }
}