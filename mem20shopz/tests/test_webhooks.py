"""Tests for the payment path.

Signatures here are produced by the real Stripe SDK's own
``generate_signature_header``, so these exercise the same HMAC construction
Stripe uses rather than a hand-rolled approximation of it.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest
import stripe

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

WEBHOOK_SECRET = "whsec_test_secret_for_offline_verification"


@pytest.fixture(autouse=True)
def shop_env(monkeypatch, tmp_path):
    """Isolate every test from the real estate secrets and the real event store."""
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_placeholder")
    monkeypatch.setenv("STRIPE_PUBLISHABLE_KEY", "pk_test_placeholder")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", WEBHOOK_SECRET)
    monkeypatch.delenv("STRIPE_MODE", raising=False)
    monkeypatch.setattr("mem20shopz.config.SECRETS_FILE", str(tmp_path / "absent.env"))

    from mem20shopz import app, events, provisioning

    # register() mutates a module-level list by design, so snapshot it: without
    # this a test that registers a handler silently changes every later test.
    original_handlers = list(provisioning._HANDLERS)
    monkeypatch.setattr(provisioning, "_HANDLERS", original_handlers)

    store = events.EventStore(str(tmp_path / "events.sqlite3"))
    monkeypatch.setattr(app, "_store", store)
    return store


def signed(payload: dict, secret: str = WEBHOOK_SECRET, timestamp: int | None = None) -> tuple[bytes, str]:
    body = json.dumps(payload).encode()
    ts = timestamp if timestamp is not None else int(time.time())
    # generate_signature_header does not decode bytes the way verify_header does,
    # so it must be handed the decoded text or it signs the repr of the bytes.
    header = stripe.WebhookSignature.generate_signature_header(body.decode(), secret, ts)
    return body, header


def completed_event(event_id: str = "evt_test_1", email: str = "buyer@example.test", amount: int = 4900) -> dict:
    return {
        "id": event_id,
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_123",
                "customer": "cus_test_123",
                "customer_details": {"email": email},
                "amount_total": amount,
                "currency": "usd",
                "metadata": {"sku_id": "foundation-single", "sku_kind": "one_time"},
            }
        },
    }


# --- signature verification ------------------------------------------------


def test_valid_signature_is_accepted(shop_env):
    from mem20shopz import webhooks

    body, header = signed(completed_event())
    report = webhooks.handle(body, header, shop_env)
    assert report["ok"] is True
    assert report["event_id"] == "evt_test_1"


def test_missing_signature_header_is_refused(shop_env):
    from mem20shopz import webhooks

    body, _ = signed(completed_event())
    with pytest.raises(webhooks.WebhookError):
        webhooks.handle(body, None, shop_env)
    assert shop_env.count() == 0, "a refused webhook must not be recorded"


def test_signature_from_the_wrong_secret_is_refused(shop_env):
    from mem20shopz import webhooks

    body, header = signed(completed_event(), secret="whsec_a_different_secret")
    with pytest.raises(webhooks.WebhookError):
        webhooks.handle(body, header, shop_env)
    assert shop_env.count() == 0


def test_tampered_body_is_refused(shop_env):
    """Editing the payload after signing must invalidate it."""
    from mem20shopz import webhooks

    body, header = signed(completed_event(amount=4900))
    tampered = body.replace(b'"amount_total": 4900', b'"amount_total": 1')
    assert tampered != body
    with pytest.raises(webhooks.WebhookError):
        webhooks.handle(tampered, header, shop_env)


def test_garbage_signature_is_refused(shop_env):
    from mem20shopz import webhooks

    body, _ = signed(completed_event())
    with pytest.raises(webhooks.WebhookError):
        webhooks.handle(body, "t=1,v1=deadbeef", shop_env)


def test_stale_timestamp_is_refused(shop_env):
    """An old but correctly signed payload is a replay, and is refused."""
    from mem20shopz import webhooks

    old = int(time.time()) - 4000
    body, header = signed(completed_event(), timestamp=old)
    with pytest.raises(webhooks.WebhookError):
        webhooks.handle(body, header, shop_env)


def test_missing_webhook_secret_refuses_everything(shop_env, monkeypatch):
    """With no secret we cannot tell a real payment from a forged one.

    This is the case that must never fall open.
    """
    from mem20shopz import webhooks

    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    body, header = signed(completed_event())
    with pytest.raises(webhooks.WebhookError):
        webhooks.handle(body, header, shop_env)
    assert shop_env.count() == 0


def test_verify_itself_raises_when_the_secret_is_missing(monkeypatch):
    """Pin verify()'s own contract, not just handle()'s.

    handle() would refuse a nameless event anyway, so testing only handle() lets
    a broken verify() hide behind that second check. This asserts the refusal
    happens at the point where trust is decided.
    """
    from mem20shopz import config, webhooks

    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    monkeypatch.setattr(config, "SECRETS_FILE", "/nonexistent.env")

    body, header = signed(completed_event())
    with pytest.raises(webhooks.WebhookError) as exc:
        webhooks.verify(body, header)
    assert "WEBHOOK" in str(exc.value)


def test_non_json_payload_is_refused(shop_env):
    from mem20shopz import webhooks

    body, header = signed_completed_raw(b"not json at all")
    with pytest.raises(webhooks.WebhookError):
        webhooks.handle(body, header, shop_env)


def signed_completed_raw(body: bytes) -> tuple[bytes, str]:
    header = stripe.WebhookSignature.generate_signature_header(
        body.decode("utf-8", "replace"), WEBHOOK_SECRET, int(time.time())
    )
    return body, header


# --- idempotency -----------------------------------------------------------


def test_replayed_event_provisions_exactly_once(shop_env):
    from mem20shopz import provisioning, webhooks

    calls: list[str] = []
    provisioning.register("counter", lambda req: calls.append(req.event_id) or "counted")

    body, header = signed(completed_event())
    first = webhooks.handle(body, header, shop_env)
    second = webhooks.handle(body, header, shop_env)

    assert first["action"] == "provisioned"
    assert second["action"] == "duplicate-refused"
    assert calls == ["evt_test_1"], "a redelivered event must not provision twice"
    assert shop_env.count() == 1


def test_different_event_ids_each_provision(shop_env):
    from mem20shopz import provisioning, webhooks

    calls: list[str] = []
    provisioning.register("counter", lambda req: calls.append(req.event_id) or "counted")

    for index in range(3):
        body, header = signed(completed_event(event_id=f"evt_{index}"))
        webhooks.handle(body, header, shop_env)

    assert sorted(calls) == ["evt_0", "evt_1", "evt_2"]


def test_unrelated_event_types_are_acknowledged_but_provision_nothing(shop_env):
    from mem20shopz import provisioning, webhooks

    calls: list[str] = []
    provisioning.register("counter", lambda req: calls.append(req.event_id) or "counted")

    body, header = signed({"id": "evt_x", "type": "invoice.paid", "data": {"object": {}}})
    report = webhooks.handle(body, header, shop_env)

    assert report["action"] == "ignored"
    assert calls == []


def test_event_without_an_id_is_refused(shop_env):
    """Without an id we cannot de-duplicate, so we must not act on it."""
    from mem20shopz import webhooks

    event = completed_event()
    del event["id"]
    body, header = signed(event)
    with pytest.raises(webhooks.WebhookError):
        webhooks.handle(body, header, shop_env)


def test_idempotency_survives_a_restart(shop_env, tmp_path):
    """A redelivery after a restart must still be refused.

    This is the whole reason the store is on disk rather than in memory.
    """
    from mem20shopz import events, provisioning, webhooks

    path = str(tmp_path / "durable.sqlite3")
    calls: list[str] = []
    provisioning.register("counter", lambda req: calls.append(req.event_id) or "counted")

    body, header = signed(completed_event())
    first_store = events.EventStore(path)
    webhooks.handle(body, header, first_store)

    # A brand new store object, as a restarted process would build.
    second_store = events.EventStore(path)
    report = webhooks.handle(body, header, second_store)

    assert report["action"] == "duplicate-refused"
    assert calls == ["evt_test_1"]


# --- provisioning ----------------------------------------------------------


def test_default_provisioning_is_dry_run(shop_env):
    from mem20shopz import provisioning

    assert provisioning.is_dry_run() is True
    request = provisioning.ProvisionRequest(
        event_id="evt_1",
        event_type="checkout.session.completed",
        session_id="cs_1",
        customer_email="a@example.test",
        sku_id="foundation-single",
    )
    result = provisioning.provision(request)
    assert result.provisioned is False
    assert result.handler == "dry-run"
    assert any("would create account" in step for step in result.steps)


def test_a_failing_handler_does_not_stop_the_others(shop_env):
    from mem20shopz import provisioning

    def boom(_request):
        raise RuntimeError("handler exploded")

    provisioning.register("boom", boom)
    provisioning.register("after", lambda req: "second step ran")

    result = provisioning.provision(
        provisioning.ProvisionRequest(
            event_id="evt_1", event_type="t", session_id="cs_1"
        )
    )
    assert any("FAILED RuntimeError" in step for step in result.steps)
    assert any("second step ran" in step for step in result.steps)
