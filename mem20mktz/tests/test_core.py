"""Core organ tests: real attest crypto, pricing math, resource market,
genome lab / seeding, UCG-backed capability + bundle flows, the inference
market, and the journaled-trade exit path (executed trade == a braid node)."""
from __future__ import annotations

import pytest
from .conftest import requires_ucg

from mem20mktz import braid_hook
from mem20mktz.attest import generate_keypair, sign, verify
from mem20mktz.bundle import BundleError, ServiceBundlingEngine
from mem20mktz.capability_market import CapabilityMarketError, CapabilityMarketplace
from mem20mktz.genome import GenomeError, ModelGenomeLab, seed_default_genomes
from mem20mktz.inference_market import InferenceMarketplace
from mem20mktz.pricing import AdaptivePricingBrain
from mem20mktz.resource_market import ResourceExchangeMarket, ResourceMarketError
from mem20mktz.trade import ResourceExchange, TradeError
from mem20mktz.ucg_client import UCGClient


# --- attest (real Ed25519) ---------------------------------------------
def test_attest_sign_verify_real():
    kp = generate_keypair()
    assert {"private", "public"} <= set(kp)
    sig = sign(kp["private"], b"real message")
    assert verify(kp["public"], b"real message", sig) is True
    assert verify(kp["public"], b"tampered", sig) is False


# --- pricing ------------------------------------------------------------
def test_pricing_cost_floor_enforced(store):
    brain = AdaptivePricingBrain(store=store)
    bundle = {"models": [{"model_id": "m", "cost_per_call": 0.001}], "capabilities": []}
    q = brain.quote(bundle, margin=0.2)
    assert q["price"] >= 0.001 * 1.2 - 1e-9
    assert q["explanation"]


def test_pricing_respects_ceiling(store):
    brain = AdaptivePricingBrain(store=store)
    bundle = {"models": [{"model_id": "m", "cost_per_call": 0.001}], "capabilities": []}
    q = brain.quote(bundle, margin=0.2, reference_price=0.0013)
    assert q["price"] <= 0.0013 + 1e-9
    assert q["price"] >= 0.0012 - 1e-9


def test_pricing_empty_bundle_cost_signal(store):
    # documented behaviour: a bundle without cost items still prices from a
    # real cost signal (0.01 floor) with an honest explanation
    brain = AdaptivePricingBrain(store=store)
    q = brain.quote({"models": [], "capabilities": []}, margin=0.2)
    assert q["price"] >= 0.01
    assert q["explanation"]


# --- genome lab ---------------------------------------------------------
def test_genome_seed_seeds_empty_store(store):
    out = seed_default_genomes(store=store)
    assert len(out) >= 1
    assert all("model_id" in g for g in out)
    lab = ModelGenomeLab(store=store)
    assert lab.get(out[0]["model_id"])["model_id"] == out[0]["model_id"]


def test_genome_seed_is_idempotent(store):
    f = seed_default_genomes(store=store)
    s = seed_default_genomes(store=store)
    assert len(f) == len(s) >= 1


def test_genome_register_validation(store):
    lab = ModelGenomeLab(store=store)
    with pytest.raises(GenomeError):
        lab.register("", "x", "x", "x", [], {}, {}, [], 0.0, 0.5, 1.0)
    with pytest.raises(GenomeError):
        lab.register("g.x", "", "x", "x", [], {}, {}, [], 0.0, 0.5, 1.0)
    with pytest.raises(GenomeError):
        lab.register("g.x", "x", "x", "x", [], {}, {}, [], -1.0, 0.5, 1.0)


def test_genome_best_match(store):
    seed_default_genomes(store=store)
    lab = ModelGenomeLab(store=store)
    best = lab.best_match("code", max_cost=None, min_quality=0.0, prefer="quality")
    assert best is not None and best["model_id"]


# --- resource market ----------------------------------------------------
def test_resource_offer_take_roundtrip(store):
    mkt = ResourceExchangeMarket(store=store)
    off = mkt.offer("token", 100.0, 0.01, "seller-a")
    assert off["status"] == "open"
    trade = mkt.take(off["offer_id"], "buyer-b", 10.0)
    assert trade["status"] == "settled"
    assert trade["qty"] == 10.0
    assert [t["offer_id"] for t in mkt.trades()] == [off["offer_id"]]


def test_resource_take_unknown_offer(store):
    mkt = ResourceExchangeMarket(store=store)
    with pytest.raises(ResourceMarketError):
        mkt.take("offer-does-not-exist", "b", 1.0)


# --- capability market (live UCG) ---------------------------------------
@requires_ucg
def test_capability_publish_buy_real_node(store):
    ucg = UCGClient()
    nodes = ucg.query("", active_only=False)
    cap_id = next((c["id"] for c in nodes if c.get("id", "").startswith("cap.")), None)
    assert cap_id, "UCG has no capability nodes"

    mkt = CapabilityMarketplace(ucg, store=store)
    listing = mkt.publish(cap_id, price=0.01, seller="tester")
    assert listing["cap_id"] == cap_id and listing["status"] == "active"
    trade = mkt.buy(listing["listing_id"], buyer="tester-buyer")
    assert trade["status"] == "settled"
    assert trade["cap_id"] == cap_id


@requires_ucg
def test_capability_publish_unknown_node_rejected(store):
    mkt = CapabilityMarketplace(UCGClient(), store=store)
    with pytest.raises(CapabilityMarketError):
        mkt.publish("cap.definitely-not-a-real-node", price=1.0)


# --- bundling -----------------------------------------------------------
def test_bundle_compose_unknown_model_rejected(store):
    lab = ModelGenomeLab(store=store)
    ucg = UCGClient()
    cap_mkt = CapabilityMarketplace(ucg, store=store)
    eng = ServiceBundlingEngine(lab, cap_mkt, store=store)
    with pytest.raises(BundleError):
        eng.compose("bad", model_ids=["genome.not-registered"], cap_ids=[])


def test_bundle_compose_and_price_models_only(store):
    # models-only compose does not touch UCG, so it is hermetic
    seed_default_genomes(store=store)
    lab = ModelGenomeLab(store=store)
    cap_mkt = CapabilityMarketplace(UCGClient(), store=store)
    brain = AdaptivePricingBrain(store=store)
    eng = ServiceBundlingEngine(lab, cap_mkt, brain, store=store)
    b = eng.compose("test bundle", model_ids=["genome.litellm.fast"], cap_ids=[])
    assert b["bundle_id"].startswith("bundle-")
    assert b["models"][0]["model_id"] == "genome.litellm.fast"
    priced = eng.price(b["bundle_id"], margin=0.2)
    assert priced["price"] is not None and priced["price"] > 0


@requires_ucg
def test_bundle_compose_with_real_cap_node(store):
    seed_default_genomes(store=store)
    ucg = UCGClient()
    nodes = ucg.query("", active_only=False)
    cap_id = next((c["id"] for c in nodes if c.get("id", "").startswith("cap.")), None)
    assert cap_id, "UCG has no capability nodes"
    lab = ModelGenomeLab(store=store)
    cap_mkt = CapabilityMarketplace(ucg, store=store)
    eng = ServiceBundlingEngine(lab, cap_mkt, store=store)
    b = eng.compose("cap bundle", model_ids=["genome.litellm.fast"],
                    cap_ids=[cap_id], target="ar-training")
    assert b["capabilities"][0]["cap_id"] == cap_id


# --- inference market ---------------------------------------------------
def test_inference_list_match_transact(store):
    seed_default_genomes(store=store)
    lab = ModelGenomeLab(store=store)
    mkt = InferenceMarketplace(lab, store=store)
    mkt.list_model("genome.litellm.fast", price=0.0005, min_quality=0.5,
                   available=2)
    match = mkt.match("write some code", capabilities=["code"], prefer="cost")
    assert match and match["model_id"] == "genome.litellm.fast"
    trade = mkt.transact(match["listing_id"], "buyer-x", units=2, settled=True)
    assert trade["status"] == "settled"
    assert trade["units"] == 2


# --- journaled trade (the exit test) ------------------------------------
def test_trade_execute_journaled_is_a_braid_node(store, monkeypatch):
    if not braid_hook.braid_ok():
        pytest.skip("braid ledger unreachable for journaled path")
    monkeypatch.setenv("MEM20_MKTZ_STORE", store)

    brain = AdaptivePricingBrain(store=store)
    ex = ResourceExchange(brain, store=store)
    bundle = {"models": [{"model_id": "m", "cost_per_call": 0.0002}], "capabilities": []}
    trade = ex.execute("agent-t", bundle, margin=0.2, reference_price=0.5,
                       wallet=0.05, journal=True)
    assert trade["status"] == "executed"
    prov = trade["provenance"]
    assert prov["ok"] is True
    cid = prov["cid"]
    assert cid.startswith("br")
    assert braid_hook.prove_cid(cid) is True
    node = braid_hook.lookup(cid)
    assert node.get("cid") == cid
    head = braid_hook.head_node()
    assert head["cid"] == cid
    assert head["payload"]["kind"] == "trade.settled"


def test_trade_execute_unfunded_raises(store):
    brain = AdaptivePricingBrain(store=store)
    ex = ResourceExchange(brain, store=store)
    bundle = {"models": [{"model_id": "m", "cost_per_call": 0.01}], "capabilities": []}
    with pytest.raises(TradeError):
        ex.execute("agent-poor", bundle, margin=0.2, wallet=0.001, journal=False)


def test_trade_local_no_journal_still_records(store):
    brain = AdaptivePricingBrain(store=store)
    ex = ResourceExchange(brain, store=store)
    bundle = {"models": [{"model_id": "m", "cost_per_call": 0.0002}], "capabilities": []}
    trade = ex.execute("agent-l", bundle, margin=0.2, wallet=0.05, journal=False)
    assert trade["status"] == "executed"
    assert "provenance" not in trade
    assert ex.get(trade["trade_id"])["trade_id"] == trade["trade_id"]