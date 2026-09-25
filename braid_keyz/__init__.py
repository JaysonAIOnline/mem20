"""braid_keyz — key management for the braid signer.

Three layered guarantees over the persistent Ed25519 signer seed:

  1. binding  — environment-bound seal: signer.sealed is ChaCha20-Poly1305
                wrapped under a scrypt key derived from the local machine
                identity (+ optional passphrase). Copied to another host the
                bytes unseal to nothing. Honest scope: defeats casual key-file
                exfiltration; it is NOT a TPM attestation.
  2. threshold — Shamir K-of-N split of the 32-byte seed: no single share is
                the key; K shares reconstruct it.
  3. rotation  — chain-anchored key rotation: `key:rotate` nodes authored by an
                already-authorized signer authorize a new one. The bridge gate
                refuses any signer outside the lineage.

Every function fails closed; nothing here fabricates a key that was not
materially recovered.
"""

from .binding import (
    seal_signer,
    unseal_signer,
    SEALED_SIGNER_PATH,
    machine_identity,
)
from .threshold import (
    split_seed,
    join_shares,
    write_threshold_shares,
    read_threshold_shares,
)
from .rotation import (
    authorized_signer_set,
    is_authorized_signer,
    commit_rotation,
    rotation_history,
    ROTATION_OP,
)

__all__ = [
    "seal_signer",
    "unseal_signer",
    "SEALED_SIGNER_PATH",
    "machine_identity",
    "split_seed",
    "join_shares",
    "write_threshold_shares",
    "read_threshold_shares",
    "authorized_signer_set",
    "is_authorized_signer",
    "commit_rotation",
    "rotation_history",
    "ROTATION_OP",
]