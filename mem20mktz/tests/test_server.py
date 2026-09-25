"""Server tests: the FastAPI surface runs the real organs against a temp store
and returns the organ's real payload. Journaled trades are real braid nodes."""
from __future__ import annotations

import pytest
from conftest import requires_ucg
from fastapi.testclient import TestClient

from mem20mktz.server import create_app


@pytest.fixture()
def client(env_store):
    return TestClient(create_app(store=env_store))


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["descriptor_count"] == 6
    assert body["ucg_ok"] is True
    assert body["braid_ok"] is True


def test_descriptors(client):
    r = client.get("/descriptors")
    assert r.status_code == 200 and r.json()["count"] == 6


def test_genomes_seed_and_list(client):
    assert client.post("/genomes/seed").json()["count"] >= 1
    r = client.get("/genomes")
    assert r.status_code == 200 and len(r.json()["genomes"]) >= 1


def test_resource_offers_take(client):
    offer = client.post("/resource/offers", json={
        "kind": "compute", "units": 10, "unit_price": 0.5, "seller": "srv"}).json()["offer"]
    assert offer["status"] == "open"
    trade = client.post("/resource/take", json={
        "offer_id": offer["offer_id"], "buyer": "srv-buyer",
        "qty": 3}).json()["trade"]
    assert trade["status"] == "settled"


def test_pricing_quote(client):
    r = client.post("/pricing/quote", json={
        "bundle": {"models": [{"model_id": "m", "cost_per_call": 0.001}],
                   "capabilities": []},
        "margin": 0.2})
    assert r.status_code == 200
    assert r.json()["quote"]["price"] >= 0.0012 - 1e-9


@requires_ucg
def test_capability_publish_buy(client):
    nodes = client.get("/capability/nodes").json()["nodes"]
    assert nodes, "expect live UCG nodes"
    cap_id = nodes[0]["id"]
    pub = client.post("/capability/publish", json={
        "cap_id": cap_id, "price": 0.03, "seller": "srv"}).json()["listing"]
    buy = client.post("/capability/buy", json={
        "listing_id": pub["listing_id"], "buyer": "srv-buyer"}).json()["trade"]
    assert buy["status"] == "settled" and buy["cap_id"] == cap_id


def test_bundle_compose_price(client):
    client.post("/genomes/seed")
    b = client.post("/bundle/compose", json={
        "name": "server bundle", "model_ids": ["genome.litellm.fast"],
        "cap_ids": []}).json()["bundle"]
    assert b["bundle_id"].startswith("bundle-")
    priced = client.post(f"/bundle/{b['bundle_id']}/price", json={"margin": 0.2}).json()["bundle"]
    assert priced["price"] > 0


def test_bundle_ar_training_factory(client):
    client.post("/genomes/seed")
    r = client.post("/bundle/ar-training")
    body = r.json()["bundle"]
    assert body["target"] == "ar-training"


def test_trade_execute_and_journal(client):
    r = client.post("/trade/execute", json={
        "buyer": "srv-bot",
        "bundle": {"models": [{"model_id": "m", "cost_per_call": 0.0002}],
                   "capabilities": []},
        "margin": 0.2, "reference_price": 0.5, "wallet": 0.05})
    assert r.status_code == 200
    trade = r.json()["trade"]
    assert trade["status"] == "executed"
    cid = trade["provenance"]["cid"]
    assert trade["provenance"]["ok"] is True
    prove = client.get(f"/journal/prove?cid={cid}").json()
    assert prove["proved"] is True
    node = client.get(f"/journal/node?cid={cid}").json()
    assert node["node"]["cid"] == cid
    assert client.get("/journal/tail").json()["head"]["cid"] == cid


def test_trade_execute_insufficient_funds(client):
    r = client.post("/trade/execute", json={
        "buyer": "poor-bot",
        "bundle": {"models": [{"model_id": "m", "cost_per_call": 0.01}],
                   "capabilities": []},
        "margin": 0.2, "wallet": 0.0001})
    assert r.status_code == 400
    assert "insufficient funds" in r.json()["detail"]


def test_journal_node_unknown_cid_404(client):
    r = client.get("/journal/node?cid=brffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff")
    assert r.status_code == 404 or r.status_code == 502