"""Creating Stripe Checkout sessions, server-side only.

The secret key never leaves this process: the browser gets a publishable key and
a redirect URL, nothing more. A SKU that is not genuinely configured is refused
here, at the last point before money moves, rather than relying on the storefront
to have hidden the button.
"""

from __future__ import annotations

import logging
from typing import Any

import stripe

from . import catalog, config

log = logging.getLogger("mem20shopz.checkout")


class CheckoutError(Exception):
    """The purchase cannot proceed."""


def _client() -> stripe.StripeClient:
    key = config.require_secret()
    return stripe.StripeClient(api_key=key)


def create_session(
    sku_id: str,
    success_url: str,
    cancel_url: str,
    quantity: int = 1,
    customer_email: str = "",
) -> dict[str, Any]:
    """Create a Checkout Session for a configured SKU.

    Raises CheckoutError for an unknown SKU, an unconfigured price, or a missing
    Stripe secret. All three are refusals; none of them falls through to a
    free or zero-value session.
    """
    sku = catalog.get_sku(sku_id)
    if sku is None:
        raise CheckoutError(f"no such SKU: {sku_id}")
    if not sku.configured:
        raise CheckoutError(
            f"{sku.id} is not purchasable: {sku.unconfigured_reason() or 'price not set'}"
        )
    if quantity < 1:
        raise CheckoutError("quantity must be at least 1")

    try:
        client = _client()
    except config.ConfigurationError as exc:
        raise CheckoutError(str(exc)) from exc

    payload: dict[str, Any] = {
        "mode": "subscription" if sku.kind == catalog.SUBSCRIPTION else "payment",
        "line_items": [{"price": sku.price_id, "quantity": quantity}],
        "success_url": success_url,
        "cancel_url": cancel_url,
        # Echoed back on the webhook so provisioning knows what was bought.
        "metadata": {"sku_id": sku.id, "sku_kind": sku.kind},
    }
    if customer_email:
        payload["customer_email"] = customer_email

    try:
        session = client.checkout.sessions.create(**payload)
    except Exception as exc:
        log.exception("stripe checkout session creation failed for %s", sku.id)
        raise CheckoutError(f"Stripe rejected the session: {type(exc).__name__}: {exc}") from exc

    return {
        "id": session.id,
        "url": session.url,
        "sku_id": sku.id,
        "mode": payload["mode"],
        "stripe_mode": config.mode(),
        "amount_cents": sku.amount_cents,
        "currency": catalog.CURRENCY,
    }


def readiness() -> dict[str, Any]:
    return config.describe(catalog_configured=catalog.is_configured())
