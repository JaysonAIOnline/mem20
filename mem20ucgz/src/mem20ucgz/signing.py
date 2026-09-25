from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any


def canonical_manifest(data: dict[str, Any]) -> bytes:
    excluded = {"signature", "signed", "created_at", "updated_at"}
    payload = {k: v for k, v in data.items() if k not in excluded}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()


def sign_manifest(data: dict[str, Any], key: str) -> str:
    return hmac.new(key.encode(), canonical_manifest(data), hashlib.sha256).hexdigest()


def verify_manifest(data: dict[str, Any], key: str) -> bool:
    signature = data.get("signature")
    if not signature:
        return False
    expected = sign_manifest(data, key)
    return hmac.compare_digest(str(signature), expected)
