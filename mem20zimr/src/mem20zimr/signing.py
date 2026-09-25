from __future__ import annotations
import hashlib, hmac, json, zipfile
from pathlib import Path


def canonical_payload(manifest: dict) -> bytes:
    clean = {k: v for k, v in manifest.items() if k not in {"signature", "digest"}}
    return json.dumps(clean, sort_keys=True, separators=(",", ":")).encode()


def file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def bundle_digest(bundle: Path) -> str:
    h = hashlib.sha256()
    with zipfile.ZipFile(bundle) as z:
        for name in sorted(n for n in z.namelist() if n != "manifest.json"):
            h.update(name.encode())
            h.update(z.read(name))
    return h.hexdigest()


def sign_manifest(manifest: dict, secret: str) -> str:
    return hmac.new(secret.encode(), canonical_payload(manifest), hashlib.sha256).hexdigest()


def verify_manifest(manifest: dict, secret: str, bundle: Path) -> None:
    expected = sign_manifest(manifest, secret)
    if not hmac.compare_digest(expected, manifest.get("signature", "")):
        raise ValueError("invalid manifest signature")
    actual_digest = bundle_digest(bundle)
    if not hmac.compare_digest(actual_digest, manifest.get("digest", "")):
        raise ValueError("bundle digest mismatch")
