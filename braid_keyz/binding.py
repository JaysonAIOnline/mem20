"""Environment-bound key sealing for the braid signer.

Honest scope: this is software binding, not a TPM attestation.  A /etc/machine-id
is a filesystem value, not a hardware root of trust; a cloned OS image carries
machine-id with it.  What this DOES do is make a bare copy of `signer.sealed`
(to another machine, or to a directory whose machine identity was not captured)
unseal to nothing.  It defeats casual key-file exfiltration and accidental
misplacement, nothing more.  Documented deliberately, not dressed up.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Optional, Union

from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

SealPath = Union[str, Path]

MACHINE_ID_PATH = os.environ.get("BRAID_KEYZ_MACHINE_ID_PATH", "/etc/machine-id")
SEALED_SIGNER_PATH = os.environ.get(
    "BRAID_KEYZ_SEALED_PATH",
    os.path.join(os.environ.get("MEM20_BRAID_DIR", "/opt/mem20/store/braid"), "signer.sealed"),
)
_BINDING_CONTEXT = b"braid-keyz/binding/v1"


class BindingError(RuntimeError):
    """Raised when a seal cannot be unsealed or a seal would be unsafe."""


def machine_identity() -> bytes:
    """Stable bytes fingerprinting this machine identity.

    Uses /etc/machine-id when present; otherwise the first 64 hex chars of the
    node's hostname is a weaker-but-deterministic fallback.  Never raises if the
    value is present; forges NO identity from nothing.
    """
    try:
        with open(MACHINE_ID_PATH, "r", encoding="utf-8") as fh:
            ident = fh.read().strip()
        if ident:
            return ident.encode("utf-8")
    except OSError:
        pass
    try:
        import socket

        return socket.gethostname().encode("utf-8")[:64]
    except OSError:
        raise BindingError("no machine identity available (machine-id and hostname both unreadable)")


def _derive_key(machine: bytes, passphrase: Optional[str]) -> bytes:
    """scrypt channel-mixing of machine identity + passphrase into a 32-byte key."""
    salt = hashlib.blake2b(
        machine + b"|" + _BINDING_CONTEXT + b"|braid-keyz-salt-v1",
        digest_size=16,
    ).digest()
    password = machine + (b"\x00" + passphrase.encode("utf-8") if passphrase else b"")
    return hashlib.scrypt(
        password=password,
        salt=salt,
        n=2**14,
        r=8,
        p=1,
        maxmem=128 * 1024 * 1024,
        dklen=32,
    )


def seal_signer(
    signer_hex: str,
    path: SealPath = SEALED_SIGNER_PATH,
    passphrase: Optional[str] = None,
    machine: Optional[bytes] = None,
) -> None:
    """Seal a signer hex string into an environment-bound ChaCha20-Poly1305 file.

    The sealed file stores: nonce, ciphertext (Poly1305 tag included), and the
    machine identity hash the key was derived under.  Unsealing re-derives the
    key from the CURRENT machine identity + passphrase; a mismatch is not
    decryptable (AEAD auth fails) — never partially returned.
    """
    if not signer_hex or not isinstance(signer_hex, str) or not signer_hex.strip():
        raise BindingError("refusing to seal an empty signer")
    if passphrase is not None and passphrase == "":
        raise BindingError("passphrase must be None or non-empty")

    machine = machine if machine is not None else machine_identity()
    key = _derive_key(machine, passphrase)
    nonce = os.urandom(12)
    aad = b"braid|" + _BINDING_CONTEXT + b"|" + machine
    ciphertext = ChaCha20Poly1305(key).encrypt(nonce, signer_hex.strip().encode("utf-8"), aad)

    header = {
        "v": 1,
        "machine_hash": hashlib.blake2b(machine, digest_size=16).hexdigest(),
        "bound": passphrase is not None,
        "nonce": nonce.hex(),
        "ciphertext": ciphertext.hex(),  # includes the 16-byte Poly1305 tag
    }
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(header, sort_keys=True), encoding="utf-8")
    os.replace(tmp, target)
    os.chmod(target, 0o600)


def unseal_signer(
    path: SealPath = SEALED_SIGNER_PATH,
    passphrase: Optional[str] = None,
    machine: Optional[bytes] = None,
) -> str:
    """Recover the signer from a sealed file.

    Fails closed on: missing file, malformed header, machine mismatch, wrong /
    missing passphrase, or any AEAD auth failure.  All failures raise
    BindingError; no partial bytes are ever returned.
    """
    p = Path(path)
    if not p.exists():
        raise BindingError(f"no sealed signer at {p}")
    try:
        header = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise BindingError(f"sealed signer unreadable at {p}: {e}")

    if header.get("v") != 1:
        raise BindingError(f"unsupported seal version: {header.get('v')!r}")
    if isinstance(header.get("ciphertext"), str) and header["ciphertext"]:
        ciphertext = bytes.fromhex(header["ciphertext"])
    else:
        # legacy in-place format: base64 ciphertext
        import base64

        try:
            ciphertext = base64.b64decode(header.get("ciphertext", "") or "")
        except Exception as e:
            raise BindingError(f"bad ciphertext in seal: {e}")
    if not ciphertext:
        raise BindingError("seal contains no ciphertext")

    try:
        nonce = bytes.fromhex(header["nonce"])
    except (KeyError, ValueError) as e:
        raise BindingError(f"bad nonce in seal: {e}")
    if len(nonce) != 12:
        raise BindingError(f"bad nonce length: {len(nonce)} (expected 12)")

    machine = machine if machine is not None else machine_identity()
    stored_machine_hash = header.get("machine_hash", "")
    current_hash = hashlib.blake2b(machine, digest_size=16).hexdigest()
    if stored_machine_hash and stored_machine_hash != current_hash:
        raise BindingError(
            "seal was created under a different machine identity "
            "(machine_hash mismatch) — copied key is inert here"
        )
    if bool(header.get("bound")) != (passphrase is not None):
        raise BindingError(
            f"passphrase required/forbidden mismatch: seal is "
            f"{'bound' if header.get('bound') else 'unbound'}"
        )

    key = _derive_key(machine, passphrase)
    aad = b"braid|" + _BINDING_CONTEXT + b"|" + machine
    try:
        plaintext = ChaCha20Poly1305(key).decrypt(nonce, ciphertext, aad)
    except Exception:
        raise BindingError(
            "AEAD authentication failed — wrong machine identity, wrong "
            "passphrase, or tampered seal.  NO key material recovered."
        )
    signer = plaintext.decode("utf-8").strip()
    if not signer:
        raise BindingError("unsealed to an empty signer — refusing")
    return signer