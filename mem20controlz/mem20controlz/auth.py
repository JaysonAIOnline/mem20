"""Single-admin authentication for the control plane.

Two independent layers, either of which admits the request:

1. **Cloudflare Access** — when the control plane sits behind the Access proxy,
   it injects a verified identity header. That header is only trusted when
   ``CONTROL_TRUST_CF_ACCESS`` is on, because a client can otherwise forge it.
2. **Admin password** — an HMAC-signed session cookie issued after a password
   check. The signing secret comes from the estate secrets file, never from a
   literal in this source.

Password comparison is constant-time. A missing secret disables password login
rather than falling open, and says so.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Any

from mem20ops.cloudflare import load_env_file

SECRETS_FILE = "/opt/mem20/secrets/.env"
COOKIE_NAME = "mem20_control_session"
SESSION_TTL_SECONDS = 12 * 3600
CF_IDENTITY_HEADERS = (
    "cf-access-authenticated-user-email",
    "x-authenticated-user-email",
)


def _secret(env_file: str | None = None) -> str:
    for key in ("MEM20_CONTROL_SECRET", "CONTROL_SESSION_SECRET"):
        value = os.environ.get(key)
        if value:
            return value
    return load_env_file(env_file or SECRETS_FILE).get("MEM20_CONTROL_SECRET", "")


def _password(env_file: str | None = None) -> str:
    for key in ("MEM20_CONTROL_PASSWORD", "CONTROL_ADMIN_PASSWORD"):
        value = os.environ.get(key)
        if value:
            return value
    return load_env_file(env_file or SECRETS_FILE).get("MEM20_CONTROL_PASSWORD", "")


def _trust_cf_access() -> bool:
    return os.environ.get("CONTROL_TRUST_CF_ACCESS", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _sign(payload: str, secret: str) -> str:
    digest = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{digest}"


def _verify(token: str, secret: str) -> dict[str, Any] | None:
    if not token or "." not in token:
        return None
    payload, _, signature = token.rpartition(".")
    expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        issued = float(payload)
    except ValueError:
        return None
    if time.time() - issued > SESSION_TTL_SECONDS:
        return None
    return {"issued": issued, "expires": issued + SESSION_TTL_SECONDS}


def check_password(candidate: str) -> bool:
    """Constant-time admin password check; empty configured password denies."""
    configured = _password()
    if not configured or not candidate:
        return False
    return hmac.compare_digest(configured.encode(), candidate.encode())


def issue_session() -> str | None:
    """Mint a signed session cookie, or None when no secret is configured."""
    secret = _secret()
    if not secret:
        return None
    return _sign(str(time.time()), secret)


def session_valid(token: str | None) -> bool:
    secret = _secret()
    if not secret or not token:
        return False
    return _verify(token, secret) is not None


def identity_from_headers(headers: Any) -> str | None:
    """Cloudflare Access identity, only when explicitly trusted."""
    if not _trust_cf_access():
        return None
    for name in CF_IDENTITY_HEADERS:
        value = headers.get(name)
        if value:
            return value.strip()
    return None


def auth_status() -> dict[str, Any]:
    """Describe the configured auth posture for the UI. Never leaks the secret."""
    return {
        "password_configured": bool(_password()),
        "secret_configured": bool(_secret()),
        "trust_cf_access": _trust_cf_access(),
        "cf_identity_headers": list(CF_IDENTITY_HEADERS),
        "session_ttl_s": SESSION_TTL_SECONDS,
        "policy": (
            "admitted by Cloudflare Access identity (when trusted) or a valid "
            "admin session cookie; both layers are optional and independently sufficient"
        ),
    }
