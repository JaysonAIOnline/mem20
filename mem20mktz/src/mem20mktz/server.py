"""server — real HTTP API for the mem30 marketplace organs.

Every endpoint calls a real package function against the real state planes
(and the real braid ledger for journal lookups). No canned responses: errors
from the underlying organs surface as 4xx/5xx with the real message. The app
is built by `create_app(store=...)` so tests can point every plane at a temp
store without touching production state.
"""
from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from . import braid_hook
from .bundle import BundleError, ServiceBundlingEngine
from .capability_market import CapabilityMarketError, CapabilityMarketplace
from .descriptor import all_descriptors, known_ids
from .genome import ModelGenomeLab, seed_default_genomes
from .inference_market import InferenceMarketError, InferenceMarketplace
from .pricing import AdaptivePricingBrain, PricingError
from .resource_market import ResourceExchangeMarket, ResourceMarketError
from .service import MarketService
from .trade import ResourceExchange, TradeError
from .ucg_client import UCGClient, UCGUnavailable

MKTZ_STORE = os.environ.get("MEM20_MKTZ_STORE", "").strip() or None


class GenomeRegister(BaseModel):
    model_id: str
    name: str
    provider: str
    endpoint: str
    capabilities: list[str] = []
    behavior_traits: dict[str, Any] = {}
    limits: dict[str, Any] = {}
    adapters: list[str] = []
    cost_per_call: float
    quality: float
    latency_ms: float
    energy_units: float = 0.1
    visibility: str = "local"


class QuoteRequest(BaseModel):
    bundle: dict[str, Any]
    margin: float = Field(0.2, ge=0.0)
    policy: str = "fair"
    reference_price: float | None = None


class OfferRequest(BaseModel):
    kind: str
    units: float
    unit_price: float
    seller: str


class TakeRequest(BaseModel):
    offer_id: str
    buyer: str
    qty: float


class ListModelRequest(BaseModel):
    model_id: str
    price: float = Field(ge=0.0)
    min_quality: float = 0.0
    available: int = 1
    visibility: str = "paid"


class MatchRequest(BaseModel):
    task: str
    capabilities: list[str] = []
    max_price: float | None = None
    min_quality: float = 0.0
    prefer: str = "quality"


class TransactRequest(BaseModel):
    listing_id: str
    buyer: str
    units: int = 1
    settled: bool = False


class TradeExecuteRequest(BaseModel):
    buyer: str
    bundle: dict[str, Any]
    margin: float = Field(0.2, ge=0.0)
    reference_price: float | None = None
    wallet: float | None = None
    journal: bool = True


class CapabilityPublish(BaseModel):
    cap_id: str
    price: float = Field(ge=0.0)
    currency: str = "token"
    reserve: float = Field(0.0, ge=0.0)
    commission: float = Field(0.0, ge=0.0, le=1.0)
    seller: str = "mem30"
    status: str = "active"


class CapabilityBuy(BaseModel):
    listing_id: str
    buyer: str
    qty: int = Field(1, ge=1)


class BundleCompose(BaseModel):
    name: str
    model_ids: list[str] = []
    cap_ids: list[str] = []
    description: str = ""
    target: str = "composite"
    owner: str = "mem30"


class BundlePrice(BaseModel):
    margin: float = Field(0.2, ge=0.0)
    policy: str = "fair"


class Genomes(BaseModel):
    genomes: list[str] = []


def create_app(store: str | None = None) -> FastAPI:
    app = FastAPI(title="mem20mktz", version="0.1.0",
                  description="mem30 marketplace organs HTTP API")

    lab = ModelGenomeLab(store=store)
    brain = AdaptivePricingBrain(store=store)
    resource = ResourceExchangeMarket(store=store)
    inference = InferenceMarketplace(lab, store=store)
    exchange = ResourceExchange(brain, store=store)
    ucg = UCGClient()
    capability = CapabilityMarketplace(ucg, store=store)
    bundler = ServiceBundlingEngine(lab, capability, brain, store=store)

    def _err(e: Exception) -> HTTPException:
        return HTTPException(status_code=400, detail=str(e))

    @app.get("/health")
    def health() -> dict[str, Any]:
        svc = MarketService()
        report = svc.health()
        report["braid_ok"] = braid_hook.braid_ok()
        return report

    @app.get("/descriptors")
    def descriptors() -> dict[str, Any]:
        return {"descriptors": all_descriptors(), "count": len(known_ids())}

    # --- genome lab -----------------------------------------------------
    @app.post("/genomes/seed")
    def genomes_seed() -> dict[str, Any]:
        out = seed_default_genomes(store=store, lab=lab)
        return {"seeded": [g["model_id"] for g in out], "count": len(out)}

    @app.get("/genomes")
    def genomes_list(visibility: str | None = None) -> dict[str, Any]:
        return {"genomes": lab.list(visibility=visibility)}

    @app.get("/genomes/{model_id}")
    def genomes_get(model_id: str) -> dict[str, Any]:
        try:
            return {"genome": lab.get(model_id)}
        except Exception as e:
            raise _err(e)

    @app.post("/genomes")
    def genomes_register(body: GenomeRegister) -> dict[str, Any]:
        try:
            g = lab.register(**body.model_dump())
            return {"registered": g}
        except Exception as e:
            raise _err(e)

    # --- pricing --------------------------------------------------------
    @app.post("/pricing/quote")
    def pricing_quote(body: QuoteRequest) -> dict[str, Any]:
        try:
            return {"quote": brain.quote(body.bundle, margin=body.margin,
                                         policy=body.policy,
                                         reference_price=body.reference_price)}
        except PricingError as e:
            raise _err(e)

    @app.get("/pricing/decisions")
    def pricing_decisions(bundle_id: str | None = None) -> dict[str, Any]:
        return {"decisions": brain.decisions(bundle_id=bundle_id)}

    # --- resource market ------------------------------------------------
    @app.get("/resource/offers")
    def resource_offers(kind: str | None = None) -> dict[str, Any]:
        return {"listings": resource.listings(kind=kind)}

    @app.post("/resource/offers")
    def resource_offer(body: OfferRequest) -> dict[str, Any]:
        try:
            return {"offer": resource.offer(body.kind, body.units, body.unit_price, body.seller)}
        except ResourceMarketError as e:
            raise _err(e)

    @app.post("/resource/take")
    def resource_take(body: TakeRequest) -> dict[str, Any]:
        try:
            return {"trade": resource.take(body.offer_id, body.buyer, body.qty)}
        except ResourceMarketError as e:
            raise _err(e)

    @app.get("/resource/trades")
    def resource_trades() -> dict[str, Any]:
        return {"trades": resource.trades()}

    # --- inference market -----------------------------------------------
    @app.get("/inference/listings")
    def inference_listings() -> dict[str, Any]:
        return {"listings": inference.listings()}

    @app.post("/inference/list-model")
    def inference_list_model(body: ListModelRequest) -> dict[str, Any]:
        try:
            return {"listing": inference.list_model(
                body.model_id, body.price, min_quality=body.min_quality,
                available=body.available, visibility=body.visibility)}
        except InferenceMarketError as e:
            raise _err(e)

    @app.post("/inference/match")
    def inference_match(body: MatchRequest) -> dict[str, Any]:
        try:
            return {"match": inference.match(body.task, capabilities=body.capabilities,
                                             max_price=body.max_price,
                                             min_quality=body.min_quality,
                                             prefer=body.prefer)}
        except InferenceMarketError as e:
            raise _err(e)

    @app.post("/inference/transact")
    def inference_transact(body: TransactRequest) -> dict[str, Any]:
        try:
            return {"trade": inference.transact(body.listing_id, body.buyer,
                                                units=body.units, settled=body.settled)}
        except InferenceMarketError as e:
            raise _err(e)

    @app.get("/inference/trades")
    def inference_trades(buyer: str | None = None) -> dict[str, Any]:
        return {"trades": inference.trades(buyer=buyer)}

    # --- capability market (UCG-backed) ----------------------------------
    @app.get("/capability/nodes")
    def capability_nodes() -> dict[str, Any]:
        try:
            return {"nodes": ucg.query("", active_only=False)}
        except UCGUnavailable as e:
            raise HTTPException(status_code=502, detail=str(e)) from e

    @app.get("/capability/listings")
    def capability_listings(cap_id: str | None = None) -> dict[str, Any]:
        return {"listings": capability.listings(cap_id=cap_id)}

    @app.get("/capability/listings/{listing_id}")
    def capability_listing(listing_id: str) -> dict[str, Any]:
        try:
            return {"listing": capability.get_listing(listing_id)}
        except CapabilityMarketError as e:
            raise _err(e)

    @app.post("/capability/publish")
    def capability_publish(body: CapabilityPublish) -> dict[str, Any]:
        try:
            return {"listing": capability.publish(
                body.cap_id, body.price, currency=body.currency,
                reserve=body.reserve, commission=body.commission,
                seller=body.seller, status=body.status)}
        except (CapabilityMarketError, UCGUnavailable) as e:
            detail = str(e)
            raise HTTPException(status_code=502 if isinstance(e, UCGUnavailable) else 400,
                                detail=detail) from e

    @app.post("/capability/buy")
    def capability_buy(body: CapabilityBuy) -> dict[str, Any]:
        try:
            return {"trade": capability.buy(body.listing_id, body.buyer, qty=body.qty)}
        except CapabilityMarketError as e:
            raise _err(e)

    @app.get("/capability/trades")
    def capability_trades(buyer: str | None = None) -> dict[str, Any]:
        return {"trades": capability.trades(buyer=buyer)}

    @app.post("/capability/simulate")
    def capability_simulate() -> dict[str, Any]:
        return capability.simulate()

    # --- service bundling (UCG-backed) -----------------------------------
    @app.post("/bundle/compose")
    def bundle_compose(body: BundleCompose) -> dict[str, Any]:
        try:
            return {"bundle": bundler.compose(
                body.name, body.model_ids, body.cap_ids,
                description=body.description, target=body.target, owner=body.owner)}
        except (BundleError, UCGUnavailable) as e:
            detail = str(e)
            raise HTTPException(status_code=502 if isinstance(e, UCGUnavailable) else 400,
                                detail=detail) from e

    @app.post("/bundle/ar-training")
    def bundle_ar_training(vision: str | None = None, coder: str | None = None,
                           strong: str | None = None) -> dict[str, Any]:
        try:
            return {"bundle": bundler.compose_ar_training_offer(
                vision_model=vision, coder_model=coder, strong_model=strong)}
        except (BundleError, UCGUnavailable) as e:
            detail = str(e)
            raise HTTPException(status_code=502 if isinstance(e, UCGUnavailable) else 400,
                                detail=detail) from e

    @app.get("/bundle")
    def bundle_list() -> dict[str, Any]:
        return {"bundles": bundler.list()}

    @app.get("/bundle/{bundle_id}")
    def bundle_get(bundle_id: str) -> dict[str, Any]:
        try:
            return {"bundle": bundler.get(bundle_id)}
        except BundleError as e:
            raise _err(e)

    @app.post("/bundle/{bundle_id}/price")
    def bundle_price(bundle_id: str, body: BundlePrice) -> dict[str, Any]:
        try:
            return {"bundle": bundler.price(bundle_id, margin=body.margin, policy=body.policy)}
        except BundleError as e:
            raise _err(e)

    @app.delete("/bundle/{bundle_id}")
    def bundle_delete(bundle_id: str) -> dict[str, Any]:
        return {"deleted": bundler.delete(bundle_id)}

    # --- resource exchange (journaled trades) ---------------------------
    @app.post("/trade/quote")
    def trade_quote(body: QuoteRequest) -> dict[str, Any]:
        try:
            return {"quote": exchange.quote(body.bundle, margin=body.margin,
                                            reference_price=body.reference_price)}
        except (PricingError, TradeError) as e:
            raise _err(e)

    @app.post("/trade/execute")
    def trade_execute(body: TradeExecuteRequest) -> dict[str, Any]:
        try:
            trade = exchange.execute(body.buyer, body.bundle, margin=body.margin,
                                     reference_price=body.reference_price,
                                     wallet=body.wallet, journal=body.journal)
            return {"trade": trade}
        except (PricingError, TradeError, braid_hook.BraidUnavailable) as e:
            detail = str(e)
            status = 502 if isinstance(e, braid_hook.BraidUnavailable) else 400
            raise HTTPException(status_code=status, detail=detail) from e

    @app.get("/trades")
    def trade_all(buyer: str | None = None) -> dict[str, Any]:
        return {"trades": exchange.all(buyer=buyer)}

    @app.get("/trades/{trade_id}")
    def trade_get(trade_id: str) -> dict[str, Any]:
        try:
            return {"trade": exchange.get(trade_id)}
        except TradeError as e:
            raise _err(e)

    # --- braid journal --------------------------------------------------
    @app.get("/journal/tail")
    def journal_tail() -> dict[str, Any]:
        try:
            return {"head": braid_hook.head_node()}
        except braid_hook.BraidUnavailable as e:
            raise HTTPException(status_code=502, detail=str(e)) from e

    @app.get("/journal/node")
    def journal_node(cid: str = Query(...)) -> dict[str, Any]:
        try:
            return {"node": braid_hook.lookup(cid), "proved": braid_hook.prove_cid(cid)}
        except braid_hook.BraidUnavailable as e:
            raise HTTPException(status_code=404 if "no node" in str(e) else 502,
                                detail=str(e)) from e

    @app.get("/journal/prove")
    def journal_prove(cid: str = Query(...)) -> dict[str, Any]:
        try:
            return {"cid": cid, "proved": braid_hook.prove_cid(cid)}
        except braid_hook.BraidUnavailable as e:
            raise HTTPException(status_code=502, detail=str(e)) from e

    return app


app: FastAPI = create_app(store=MKTZ_STORE)