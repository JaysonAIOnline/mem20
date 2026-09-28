"""attest — real cryptographic primitives for the human/device trust bridge.

Uses the `cryptography` Ed25519 implementation and Python `secrets`. No fake
crypto: if the library is missing, these functions raise ImportError rather
than degrade to a simulation.
"""
from __future__ import annotations

import secrets

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

_NONCE_BYTES = 32


def new_credential() -> str:
    """Return a fresh bearer credential (URL-safe token)."""
    return secrets.token_urlsafe(32)


def new_nonce() -> str:
    """Return a fresh attestation challenge nonce."""
    return secrets.token_urlsafe(_NONCE_BYTES)


def generate_keypair() -> dict[str, str]:
    """Bootstrap a fresh Ed25519 keypair. Returns {private, public} hex."""
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key()
    return {
        "private": priv.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        ).hex(),
        "public": pub.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        ).hex(),
    }


def sign(private_hex: str, message: bytes) -> str:
    """Sign a message with the Ed25519 private key (raw hex)."""
    priv = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private_hex))
    return priv.sign(message).hex()


def verify(public_hex: str, message: bytes, signature_hex: str) -> bool:
    """Verify an Ed25519 signature. Returns False (never raises) for bad input."""
    try:
        pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_hex))
        sig = bytes.fromhex(signature_hex)
        pub.verify(sig, message)
        return True
    except Exception:
        return False