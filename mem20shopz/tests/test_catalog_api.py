"""Catalog and HTTP-surface tests.

The important assertions here are the refusals: an unpriced SKU must not be
buyable, and the service must not pretend to be a shop when it cannot take money.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def shop_env(monkeypatch, tmp_path):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_placeholder")
    monkeypatch.setenv("STRIPE_PUBLISHABLE_KEY", "pk_test_placeholder")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.delenv("STRIPE_MODE", raising=False)
    monkeypatch.setattr("mem20shopz.config.SECRETS_FILE", str(tmp_path / "absent.env"))

    from mem20shopz import app, events

    # Point the app at a throwaway store instead of patching the class, so no
    # test can touch the real estate event ledger.
    app._store = events.EventStore(str(tmp_path / "e.sqlite3"))
    return app


@pytest.fixture()
def client(shop_env):
    from fastapi.testclient import TestClient

    return TestClient(shop_env.app)


# --- catalog ---------------------------------------------------------------


def test_five_catalog_groups_exist():
    from mem20shopz import catalog

    assert len(catalog.GROUPS) == 5
    assert len({g["id"] for g in catalog.GROUPS}) == 5


def test_catalog_has_one_time_and_subscription_items():
    from mem20shopz import catalog

    summary = catalog.summary()
    assert summary["skus"] > 0
    assert summary["subscriptions"] > 0
    assert summary["skus"] > summary["subscriptions"], "one-time items should exist too"


def test_every_group_has_at_least_one_sku():
    from mem20shopz import catalog

    for group in catalog.groups():
        assert group["count"] > 0, f"group {group['id']} is empty"


def test_shipped_catalog_has_no_prices_configured():
    """No price is invented, so nothing is sellable until real ones are added."""
    from mem20shopz import catalog

    assert catalog.is_configured() is False
    assert catalog.summary()["configured"] == 0


def test_unconfigured_sku_says_why():
    from mem20shopz import catalog

    sku = catalog.get_sku("foundation-single")
    assert sku is not None
    assert sku.configured is False
    assert sku.price_label() == "price not set"
    assert "Stripe Price" in sku.unconfigured_reason()


def test_price_id_without_an_amount_is_not_sellable():
    """A Stripe Price with no known amount could bill the wrong figure."""
    from mem20shopz import catalog

    sku = catalog.Sku(
        id="x", group="support", name="X", description="", price_id="price_123", amount_cents=None
    )
    assert sku.configured is False
    assert "amount" in sku.unconfigured_reason()


def test_amount_without_a_price_id_is_not_sellable():
    from mem20shopz import catalog

    sku = catalog.Sku(
        id="x", group="support", name="X", description="", price_id="", amount_cents=1000
    )
    assert sku.configured is False
    assert "Stripe Price" in sku.unconfigured_reason()


def test_zero_amount_is_not_sellable():
    """A free SKU must be a deliberate decision, never an omitted one."""
    from mem20shopz import catalog

    sku = catalog.Sku(
        id="x", group="support", name="X", description="", price_id="price_1", amount_cents=0
    )
    assert sku.configured is False


def test_subscription_and_one_time_labels():
    from mem20shopz import catalog

    monthly = catalog.Sku(
        id="m", group="support", name="M", description="", kind=catalog.SUBSCRIPTION,
        price_id="p", amount_cents=1500,
    )
    once = catalog.Sku(
        id="o", group="support", name="O", description="", kind=catalog.ONE_TIME,
        price_id="p", amount_cents=1500,
    )
    assert monthly.price_label() == "$15.00/mo"
    assert once.price_label() == "$15.00"


def test_catalog_rejects_an_unknown_group(tmp_path):
    from mem20shopz import catalog

    bad = tmp_path / "catalog.json"
    bad.write_text(json.dumps({"skus": [{"id": "x", "group": "nope", "name": "X"}]}))
    monkey = catalog.CATALOG_PATH
    catalog.CATALOG_PATH = bad
    try:
        with pytest.raises(catalog.CatalogError):
            catalog.all_skus()
    finally:
        catalog.CATALOG_PATH = monkey


def test_catalog_rejects_malformed_json(tmp_path):
    from mem20shopz import catalog

    bad = tmp_path / "catalog.json"
    bad.write_text("{not json")
    monkey = catalog.CATALOG_PATH
    catalog.CATALOG_PATH = bad
    try:
        with pytest.raises(catalog.CatalogError):
            catalog.all_skus()
    finally:
        catalog.CATALOG_PATH = monkey


# --- config ----------------------------------------------------------------


def test_missing_secret_key_blocks_selling(monkeypatch, tmp_path):
    from mem20shopz import config

    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.setattr(config, "SECRETS_FILE", str(tmp_path / "none.env"))
    with pytest.raises(config.ConfigurationError):
        config.require_secret()


def test_missing_webhook_secret_blocks_provisioning(monkeypatch, tmp_path):
    from mem20shopz import config

    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    monkeypatch.setattr(config, "SECRETS_FILE", str(tmp_path / "none.env"))
    with pytest.raises(config.ConfigurationError):
        config.require_webhook_secret()
    readiness = config.describe()
    assert readiness["can_provision"] is False
    assert any("WEBHOOK" in reason for reason in readiness["blocking_reasons"])


def test_mode_follows_the_key_prefix(monkeypatch):
    from mem20shopz import config

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_abc")
    assert config.mode() == "live"
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_abc")
    assert config.mode() == "test"


def test_mode_override_cannot_promote_a_test_key(monkeypatch):
    """A mis-set variable must not make a test key claim to be live."""
    from mem20shopz import config

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_abc")
    monkeypatch.setenv("STRIPE_MODE", "live")
    assert config.mode() == "test"
    assert config.is_live() is False


def test_describe_never_leaks_key_material(monkeypatch):
    from mem20shopz import config

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_supersecretvalue")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_supersecretvalue")
    blob = json.dumps(config.describe(catalog_configured=True))
    assert "supersecretvalue" not in blob


# --- HTTP ------------------------------------------------------------------


def test_health_is_open(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_catalog_endpoint_lists_groups(client):
    body = client.get("/api/catalog").json()
    assert len(body["groups"]) == 5
    assert body["summary"]["sellable"] is False


def test_readiness_reports_why_it_cannot_sell(client):
    body = client.get("/api/readiness").json()
    assert body["can_sell"] is False
    assert body["catalog"]["configured"] == 0
    assert body["blocking_reasons"]


def test_checkout_refuses_an_unconfigured_sku(client):
    response = client.post("/api/checkout", json={"sku_id": "foundation-single"})
    assert response.status_code == 409
    assert "not purchasable" in response.json()["detail"]


def test_checkout_refuses_an_unknown_sku(client):
    response = client.post("/api/checkout", json={"sku_id": "does-not-exist"})
    assert response.status_code == 409
    assert "no such SKU" in response.json()["detail"]


def test_checkout_refuses_when_no_stripe_key(client, monkeypatch):
    """No key must mean no sale, never a free one."""
    from mem20shopz import catalog, checkout

    sku = catalog.Sku(
        id="real", group="support", name="R", description="", price_id="price_1", amount_cents=500
    )
    monkeypatch.setattr(catalog, "get_sku", lambda _id: sku)
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.setattr(checkout.config, "SECRETS_FILE", "/nonexistent.env")

    with pytest.raises(checkout.CheckoutError) as exc:
        checkout.create_session("real", "https://x/s", "https://x/c")
    assert "STRIPE_SECRET_KEY" in str(exc.value)


def test_checkout_refuses_zero_quantity(client):
    response = client.post(
        "/api/checkout", json={"sku_id": "foundation-single", "quantity": 0}
    )
    assert response.status_code == 409


def test_unsigned_webhook_is_refused_over_http(client):
    response = client.post(
        "/api/webhooks/stripe",
        content=b'{"id":"evt_1","type":"checkout.session.completed","data":{"object":{}}}',
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 400
    assert response.json()["ok"] is False


def test_storefront_page_renders(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "mem20" in response.text


def test_unknown_api_path_is_404(client):
    assert client.get("/api/nope").status_code == 404
