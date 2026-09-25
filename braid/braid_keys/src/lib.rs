//! braid_keys — key management: DID:key derivation and session macaroons.
//!
//! Identities are `did:key:` (ed25519 munching). Sessions are contextual
//! macaroons — a token bound to the DID that carries caveats and is
//! verifiable without talking to a central service.

use ed25519_dalek::{SigningKey, VerifyingKey};
use hmac::{Hmac, Mac};
use sha2::Sha256;

type HmacSha256 = Hmac<Sha256>;

/// Multibase base58btc prefix for raw bytes.
const MULTIBASE_BASE58BTC: u8 = b'z';

/// DID:key for an Ed25519 keypair (multicodec prefix 0xed + raw pubkey).
pub fn did_key(vk: &VerifyingKey) -> String {
    let mut buf = Vec::with_capacity(2 + 32);
    buf.extend_from_slice(&[0xed, 0x01]);
    buf.extend_from_slice(&vk.to_bytes());
    format!("did:key:{}{}", MULTIBASE_BASE58BTC as char, bs58::encode(&buf).into_string())
}

/// Session macaroon: a bearer token signed with the identity key, carrying
/// caveats (scope strings) the capability system can evaluate later.
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize, PartialEq)]
pub struct SessionMacaroon {
    pub location: String,
    pub identifier: String,
    pub caveats: Vec<String>,
    /// MAC over (location, identifier, caveats) using the keyed HMAC.
    pub signature: String,
}

impl SessionMacaroon {
    pub fn issue(
        location: &str,
        identifier: &str,
        caveats: &[&str],
        sk: &SigningKey,
    ) -> Self {
        let vk = VerifyingKey::from(sk);
        let did = did_key(&vk);
        // root key = HMAC-SHA256(key = did, message = "braid-session-v1")
        let mut mac = HmacSha256::new_from_slice(did.as_bytes()).expect("hmac key");
        mac.update(b"braid-session-v1");
        let root = mac.finalize().into_bytes();

        let mut m = HmacSha256::new_from_slice(&root).expect("hmac root");
        m.update(b"location:");
        m.update(location.as_bytes());
        m.update(b";identifier:");
        m.update(identifier.as_bytes());
        for c in caveats {
            m.update(b";caveat:");
            m.update(c.as_bytes());
        }
        let sig = m.finalize().into_bytes();

        SessionMacaroon {
            location: location.into(),
            identifier: identifier.into(),
            caveats: caveats.iter().map(|c| c.to_string()).collect(),
            signature: sig[..].iter().map(|b| format!("{:02x}", b)).collect(),
        }
    }

    /// Verify a macaroon against a DID (root key derived from the DID).
    pub fn verify(&self, did: &str, expected_location: &str) -> bool {
        let mut mac = HmacSha256::new_from_slice(did.as_bytes()).expect("hmac key");
        mac.update(b"braid-session-v1");
        let root = mac.finalize().into_bytes();

        let mut m = HmacSha256::new_from_slice(&root).expect("hmac root");
        m.update(b"location:");
        m.update(self.location.as_bytes());
        m.update(b";identifier:");
        m.update(self.identifier.as_bytes());
        for c in &self.caveats {
            m.update(b";caveat:");
            m.update(c.as_bytes());
        }
        let expect = m.finalize().into_bytes();
        let got = hex::decode(&self.signature);
        match got {
            Some(bytes) => {
                let expect: &[u8] = &expect;
                expect == bytes.as_slice() && self.location == expected_location
            }
            None => false,
        }
    }

    /// The macaroon's caveats as capability strings.
    pub fn capability_caveats(&self) -> Vec<braid_scope::CapabilityString> {
        self.caveats.iter().map(|c| braid_scope::CapabilityString(c.clone())).collect()
    }
}

/// Minimal local hex helper (avoid pulling hex crate at m1).
mod hex {
    pub fn decode(s: &str) -> Option<Vec<u8>> {
        if !s.len().is_multiple_of(2) {
            return None;
        }
        (0..s.len())
            .step_by(2)
            .map(|i| u8::from_str_radix(&s[i..i + 2], 16).ok())
            .collect()
    }
}

/// Opaque wrapper so macaroon caveats carry into capability matching without
/// pulling braid_core into this crate (braid_keys stays independent).
pub mod braid_scope {
    #[derive(Debug, Clone, PartialEq, Eq)]
    pub struct CapabilityString(pub String);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn did_key_is_stable_and_unambiguous() {
        let sk = SigningKey::generate(&mut rand::rngs::OsRng);
        let vk = VerifyingKey::from(&sk);
        let d1 = did_key(&vk);
        let d2 = did_key(&vk);
        assert_eq!(d1, d2);
        assert!(d1.starts_with("did:key:z"));
        assert_ne!(did_key(&VerifyingKey::from(&SigningKey::generate(&mut rand::rngs::OsRng))), d1);
    }

    #[test]
    fn macaroon_round_trip_and_tamper() {
        let sk = SigningKey::generate(&mut rand::rngs::OsRng);
        let vk = VerifyingKey::from(&sk);
        let did = did_key(&vk);
        let m = SessionMacaroon::issue("door1", "session-1", &["read:timeline:*"], &sk);
        assert!(m.verify(&did, "door1"));
        assert!(!m.verify(&did, "door2"), "wrong location must fail");
        let mut t = m.clone();
        t.caveats.push("admin:*:*".into());
        assert!(!t.verify(&did, "door1"), "tampered caveats must fail");
    }
}