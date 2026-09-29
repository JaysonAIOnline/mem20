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


def _from_file_then_env(env_file: str | None, file_key: str, env_keys: tuple[str, ...]) -> str:
    """The secrets file first, the environment second.

    Order matters, and it used to be the other way round, which is a real defect.

    ``llm.py`` performs a dotenv load *at import time* and copies every key it
    finds - not just API keys, despite what its own docstring says - into
    ``os.environ``. Anything that imports it therefore snapshots
    ``/opt/mem20/secrets/.env`` into its process environment, once, at startup.
    This module imports it transitively through ``mem20dreamz``, so preferring
    the environment meant the admin password and the session signing secret were
    frozen at boot: rotating either one in the secrets file appeared to do
    nothing until the unit was restarted, and a rotated secret left old cookies
    verifiable.

    The file is the documented single home for these secrets, so it wins. The
    environment stays a fallback so a deployment with no secrets file - a
    container configured entirely from ``Environment=`` - still works.
    """
    from_file = load_env_file(env_file or SECRETS_FILE).get(file_key, "")
    if from_file:
        return from_file
    for key in env_keys:
        value = os.environ.get(key)
        if value:
            return value
    return ""


def _secret(env_file: str | None = None) -> str:
    return _from_file_then_env(
        env_file, "MEM20_CONTROL_SECRET", ("MEM20_CONTROL_SECRET", "CONTROL_SESSION_SECRET")
    )


def _password(env_file: str | None = None) -> str:
    return _from_file_then_env(
        env_file, "MEM20_CONTROL_PASSWORD", ("MEM20_CONTROL_PASSWORD", "CONTROL_ADMIN_PASSWORD")
    )


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


#: Headers that betray a request which arrived through a proxy. Their presence
#: means the peer socket being loopback says nothing about who is actually asking:
#: a tunnel or reverse proxy terminates on this host and forwards, so the socket
#: is 127.0.0.1 while the caller is somewhere else entirely. Trusting loopback
#: without checking these would turn "local only" into "anyone who can reach the
#: proxy", which is the opposite of the property being relied on.
PROXY_HEADERS = (
    "x-forwarded-for",
    "x-forwarded-host",
    "x-forwarded-proto",
    "x-real-ip",
    "forwarded",
    "cf-connecting-ip",
    "true-client-ip",
    "x-client-ip",
)


def _is_loopback(host: Any) -> bool:
    if not host:
        return False
    candidate = str(host).strip().strip("[]").lower()
    # Strip an IPv4-mapped IPv6 form such as ::ffff:127.0.0.1.
    candidate = candidate.removeprefix("::ffff:")
    return candidate == "::1" or candidate == "localhost" or candidate.startswith("127.")


def _trust_loopback() -> bool:
    """Whether an unauthenticated local caller is admitted. On by default."""
    return os.environ.get("MEM20_CONTROL_TRUST_LOOPBACK", "1").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def local_request_allowed(client_host: Any, headers: Any) -> bool:
    """Admit a request that came from this machine, with no password.

    The owner asked for no login prompt on the box that owns the estate, and that
    is a reasonable thing to want. The trust is derived from a network fact -
    the peer really is a loopback socket - rather than from switching auth off,
    so the moment this service is reachable from anywhere else the password
    applies again on its own. The proxy-header check is what makes that true: a
    request forwarded by a tunnel also arrives on a loopback socket, and without
    it this function would wave through anybody who could reach the tunnel.

    Set ``MEM20_CONTROL_TRUST_LOOPBACK=0`` to require the password everywhere.
    """
    if not _trust_loopback():
        return False
    if not _is_loopback(client_host):
        return False
    for name in PROXY_HEADERS:
        if headers is not None and headers.get(name):
            return False
    return True


def auth_status() -> dict[str, Any]:
    """Describe the configured auth posture for the UI. Never leaks the secret."""
    return {
        "password_configured": bool(_password()),
        "secret_configured": bool(_secret()),
        "trust_cf_access": _trust_cf_access(),
        "trust_loopback": _trust_loopback(),
        "cf_identity_headers": list(CF_IDENTITY_HEADERS),
        "session_ttl_s": SESSION_TTL_SECONDS,
        "policy": (
            "admitted by any of three independent layers: a Cloudflare Access "
            "identity (when trusted), a valid admin session cookie, or a request "
            "that genuinely arrived on a loopback socket with no proxy headers. "
            "The loopback layer stops applying the moment this service is "
            "reachable from off-box, including through a tunnel"
        ),
    }
