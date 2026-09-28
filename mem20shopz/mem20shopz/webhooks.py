"""Stripe webhook intake: verify first, then provision exactly once.

The order here is the security property. Nothing is parsed into a trusted shape
and nothing is provisioned until the signature has been checked against the
webhook secret. An unsigned or tampered body is rejected before it can reach
any handler, and a replayed event id is refused before it can provision twice.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import stripe

from . import config, provisioning
from .events import EventStore
from .provisioning import ProvisionRequest

log = logging.getLogger("mem20shopz.webhooks")

SIGNATURE_HEADER = "stripe-signature"
TOLERANCE_SECONDS = 300

# Only these events provision anything. Everything else is acknowledged and
# ignored, so a new Stripe event type cannot silently start creating accounts.
PROVISIONING_EVENTS = {"checkout.session.completed"}


class WebhookError(Exception):
    """The payload was not trustworthy. Never provision on this."""


def verify(payload: bytes, signature_header: str | None) -> dict[str, Any]:
    """Verify the Stripe signature and return the decoded event.

    Raises WebhookError for a missing header, a missing secret, a bad signature,
    or a timestamp outside the tolerance. Each of those is a refusal, not a
    fallback: there is no "unsigned but probably fine" path.
    """
    if not signature_header:
        raise WebhookError("no Stripe-Signature header")
    try:
        secret = config.require_webhook_secret()
    except config.ConfigurationError as exc:
        # Fail closed. Without the secret we cannot tell a real payment from a
        # forged one, so trusting the body would let anyone provision for free.
        raise WebhookError(str(exc)) from exc

    try:
        # The SDK does the verifying and returns a Stripe Event object. We
        # deliberately parse the verified bytes ourselves afterwards rather than
        # reading that object: the raw body is exactly what Stripe signed, so
        # there is no gap between what was checked and what we act on.
        stripe.Webhook.construct_event(
            payload, signature_header, secret, tolerance=TOLERANCE_SECONDS
        )
    except ValueError as exc:
        raise WebhookError(f"payload was not valid JSON: {exc}") from exc
    except stripe.error.SignatureVerificationError as exc:
        raise WebhookError(f"signature verification failed: {exc}") from exc

    try:
        return json.loads(payload)
    except (ValueError, UnicodeDecodeError) as exc:
        raise WebhookError(f"verified payload was not decodable: {exc}") from exc


def _request_from_event(event: dict[str, Any]) -> ProvisionRequest:
    obj = event.get("data", {}).get("object", {}) or {}
    customer_details = obj.get("customer_details") or {}
    return ProvisionRequest(
        event_id=str(event.get("id", "")),
        event_type=str(event.get("type", "")),
        session_id=str(obj.get("id", "")),
        customer_email=str(customer_details.get("email") or obj.get("customer_email") or ""),
        customer_id=str(obj.get("customer") or ""),
        sku_id=str((obj.get("metadata") or {}).get("sku_id", "")),
        amount_cents=obj.get("amount_total"),
        currency=str(obj.get("currency", "")),
        mode=config.mode(),
        raw=obj,
    )


def handle(payload: bytes, signature_header: str | None, store: EventStore) -> dict[str, Any]:
    """Verify, de-duplicate, provision. Returns a report safe to log."""
    event = verify(payload, signature_header)
    event_id = str(event.get("id", ""))
    event_type = str(event.get("type", ""))

    if not event_id:
        raise WebhookError("event has no id; cannot de-duplicate safely")

    if event_type not in PROVISIONING_EVENTS:
        if store.mark(event_id, event_type, "ignored"):
            return {"ok": True, "event_id": event_id, "event_type": event_type, "action": "ignored"}
        return {
            "ok": True,
            "event_id": event_id,
            "event_type": event_type,
            "action": "duplicate-ignored",
        }

    # Claim the event before doing the work. If the process dies mid-provision
    # the event stays claimed, so the retry is refused rather than doubling up.
    if not store.mark(event_id, event_type, "claimed"):
        prior = store.already_processed(event_id) or {}
        return {
            "ok": True,
            "event_id": event_id,
            "event_type": event_type,
            "action": "duplicate-refused",
            "first_seen_outcome": prior.get("outcome"),
            "provisioned": False,
        }

    request = _request_from_event(event)
    result = provisioning.provision(request)
    store.mark(event_id, event_type, "provisioned" if result.provisioned else "dry-run")
    return {
        "ok": True,
        "event_id": event_id,
        "event_type": event_type,
        "action": "provisioned" if result.provisioned else "dry-run",
        "provisioned": result.provisioned,
        "handler": result.handler,
        "steps": result.steps,
        "mode": request.mode,
    }


def status(store: EventStore) -> dict[str, Any]:
    return {
        "events_recorded": store.count(),
        "outcomes": store.outcomes(),
        "provisioning_handlers": provisioning.registered_handlers(),
        "dry_run": provisioning.is_dry_run(),
        "webhook_secret_present": bool(config.webhook_secret()),
        "provisioning_event_types": sorted(PROVISIONING_EVENTS),
        "tolerance_seconds": TOLERANCE_SECONDS,
    }


def parse_raw(payload: bytes) -> Any:
    """Decode without verifying. For tests and debugging only, never for routing."""
    return json.loads(payload)
