//! Braid crypto: Ed25519 identity, BLAKE3-256 content addressing, CIDs.

use ed25519_dalek::{Signature, Signer, SigningKey, Verifier, VerifyingKey};
use rand::rngs::OsRng;

const TAG: &[u8] = b"braid/1";

/// BLAKE3-256 over a tagged message — the braid's content address hash.
pub fn hash_tagged(message: &[u8]) -> [u8; 32] {
    let mut hasher = blake3::Hasher::new();
    hasher.update(TAG);
    hasher.update(message);
    hasher.finalize().into()
}

/// BLAKE3-256 (bare) — used for signing commitments and pre-commitments.
pub fn hash(message: &[u8]) -> [u8; 32] {
    blake3::hash(message).into()
}

/// Content identifier: `br` + hex(BLAKE3-256).
pub fn cid(payload: &[u8]) -> String {
    format!("br{}", hex(hash_tagged(payload).as_ref()))
}

pub fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{:02x}", b)).collect()
}

pub fn from_hex(s: &str) -> Result<Vec<u8>, String> {
    if !s.len().is_multiple_of(2) {
        return Err("odd-length hex".into());
    }
    (0..s.len())
        .step_by(2)
        .map(|i| {
            u8::from_str_radix(&s[i..i + 2], 16)
                .map_err(|e| format!("bad hex at {i}: {e}"))
        })
        .collect()
}

/// Generate a fresh Ed25519 identity.
pub fn new_signing_key() -> SigningKey {
    SigningKey::generate(&mut OsRng)
}

/// Sign a raw byte payload. Returns the 64-byte signature.
pub fn sign(sk: &SigningKey, payload: &[u8]) -> [u8; 64] {
    let sig: Signature = sk.sign(payload);
    sig.to_bytes()
}

/// Verify an Ed25519 signature. Returns Ok(()) on valid, Err on mismatch.
pub fn verify(vk: &VerifyingKey, payload: &[u8], sig: &[u8; 64]) -> Result<(), String> {
    let sig = Signature::from_bytes(sig);
    vk.verify(payload, &sig).map_err(|e| format!("bad signature: {e}"))
}

/// Stable hex of the public key — identity reference between records.
pub fn pub_key_hex(vk: &VerifyingKey) -> String {
    hex(&vk.to_bytes())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sign_and_verify_round_trip() {
        let sk = new_signing_key();
        let vk = VerifyingKey::from(&sk);
        let payload = b"braid-triplet-1";
        let sig = sign(&sk, payload);
        assert!(verify(&vk, payload, &sig).is_ok());
        let mut bad = sig;
        bad[0] ^= 0xff;
        assert!(verify(&vk, payload, &bad).is_err());
    }

    #[test]
    fn cid_is_stable_and_prefixed() {
        let a = cid(b"hello");
        let b = cid(b"hello");
        assert_eq!(a, b);
        assert!(a.starts_with("br"));
        assert_eq!(a.len(), 2 + 64);
        assert_ne!(cid(b"hello!"), a);
    }
}