"""Stripe configuration, read from the environment and failing closed.

The rule this module exists to enforce: with no Stripe secret there is no
checkout. A missing key must never fall through to "let the sale through for
free", because that is the one failure mode that costs real money.

Nothing here prints a key. ``describe()`` reports only whether each key is
present, which prefix it carries, and which mode the service is in.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

SECRETS_FILE = "/opt/mem20/secrets/.env"

ENV_SECRET = "STRIPE_SECRET_KEY"
ENV_PUBLISHABLE = "STRIPE_PUBLISHABLE_KEY"
ENV_WEBHOOK = "STRIPE_WEBHOOK_SECRET"
ENV_MODE = "STRIPE_MODE"


class ConfigurationError(RuntimeError):
    """Raised when the service is asked to do something it cannot do safely."""


def _from_env_file(key: str) -> str:
    """Read one key from the estate secrets file without echoing it."""
    try:
        with open(SECRETS_FILE, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                name, _, value = line.partition("=")
                if name.strip() == key:
                    return value.strip().strip('"').strip("'")
    except OSError:
        return ""
    return ""


def _value(key: str) -> str:
    return (os.environ.get(key) or _from_env_file(key) or "").strip()


def secret_key() -> str:
    return _value(ENV_SECRET)


def publishable_key() -> str:
    return _value(ENV_PUBLISHABLE)


def webhook_secret() -> str:
    return _value(ENV_WEBHOOK)


def mode() -> str:
    """``live`` or ``test``, derived from the key prefix unless overridden.

    The prefix is the source of truth because it is the thing Stripe itself
    guarantees. An explicit ``STRIPE_MODE`` can narrow it but can never promote
    a test key to live, so a mis-set variable cannot point a real storefront at
    test keys while claiming to be live.
    """
    override = (os.environ.get(ENV_MODE) or "").strip().lower()
    key = secret_key()
    actual = "live" if key.startswith(("sk_live_", "rk_live_")) else "test"
    if override in {"live", "test"} and override != actual:
        # Refuse to let a declaration outrank the key it describes.
        return actual
    return override if override in {"live", "test"} else actual


def is_live() -> bool:
    return mode() == "live"


@dataclass(frozen=True)
class Readiness:
    """What the service can and cannot do right now."""

    mode: str
    secret_present: bool
    publishable_present: bool
    webhook_present: bool
    catalog_configured: bool

    @property
    def can_sell(self) -> bool:
        return self.secret_present and self.catalog_configured

    @property
    def can_provision(self) -> bool:
        """Auto-provisioning needs a verified webhook secret, always.

        Without it we cannot tell a genuine payment event from a forged one, so
        a real sale would never be trusted to create an account. Shipping the
        sale without this check would be the actual vulnerability.
        """
        return self.webhook_present

    def blocking_reasons(self) -> list[str]:
        reasons: list[str] = []
        if not self.secret_present:
            reasons.append(f"{ENV_SECRET} is not set")
        if not self.webhook_present:
            reasons.append(f"{ENV_WEBHOOK} is not set (auto-provisioning stays disabled)")
        if not self.catalog_configured:
            reasons.append("catalog has no configured prices")
        return reasons

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "live": self.mode == "live",
            "secret_present": self.secret_present,
            "publishable_present": self.publishable_present,
            "webhook_present": self.webhook_present,
            "catalog_configured": self.catalog_configured,
            "can_sell": self.can_sell,
            "can_provision": self.can_provision,
            "blocking_reasons": self.blocking_reasons(),
        }


def require_secret() -> str:
    key = secret_key()
    if not key:
        raise ConfigurationError(
            f"{ENV_SECRET} is not set; refusing to create a checkout session. "
            f"Add it to {SECRETS_FILE}."
        )
    return key


def require_webhook_secret() -> str:
    secret = webhook_secret()
    if not secret:
        raise ConfigurationError(
            f"{ENV_WEBHOOK} is not set; refusing to trust webhook events. "
            f"Add it to {SECRETS_FILE}."
        )
    return secret


def describe(catalog_configured: bool = False) -> dict[str, Any]:
    """A status payload safe to hand to the browser. Contains no key material."""
    return Readiness(
        mode=mode(),
        secret_present=bool(secret_key()),
        publishable_present=bool(publishable_key()),
        webhook_present=bool(webhook_secret()),
        catalog_configured=catalog_configured,
    ).as_dict()
