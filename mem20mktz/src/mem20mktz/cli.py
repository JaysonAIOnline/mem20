"""cli — `fs-mkt` command surface for the mem30 marketplace organs.

Every subcommand calls a real function in this package against the real
state planes, the live Universal Capability Graph, and the real braid ledger
for journaled work. Nothing here prints canned values: a command either does
real work and prints the real result, or exits non-zero with the real error.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from . import __version__, braid_hook
from .bundle import BundleError, ServiceBundlingEngine
from .capability_market import CapabilityMarketError, CapabilityMarketplace
from .descriptor import all_descriptors, known_ids
from .genome import ModelGenomeLab, seed_default_genomes
from .inference_market import InferenceMarketplace
from .pricing import AdaptivePricingBrain, PricingError
from .resource_market import ResourceExchangeMarket
from .service import MarketService
from .trade import ResourceExchange, TradeError
from .ucg_client import UCGClient, UCGUnavailable

MKTZ_STORE = os.environ.get("MEM20_MKTZ_STORE", "").strip() or None


def _store() -> str | None:
    return os.environ.get("MEM20_MKTZ_STORE", "").strip() or None


def _emit(obj: Any) -> None:
    print(json.dumps(obj, indent=2, default=str))


def _load_json(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"invalid JSON: {e}") from e
    if not isinstance(value, dict):
        raise TypeError("expected a JSON object")
    return value


def _require_bundle(args: argparse.Namespace) -> dict[str, Any]:
    if args.from_genomes:
        lab = ModelGenomeLab(store=_store())
        models = []
        for mid in args.from_genomes:
            g = lab.get(mid)
            models.append({
                "model_id": g["model_id"],
                "name": g["name"],
                "cost_per_call": g["cost_per_call"],
            })
        return {
            "bundle_id": f"cli-{'-'.join(args.from_genomes)[:40]}",
            "target": "cli-bundle",
            "description": "bundle composed from real registered model genomes",
            "models": models,
            "capabilities": [],
        }
    if not args.bundle:
        raise ValueError(
            "a bundle is required: pass --bundle '<json>' or --from-genomes <model_id> ..."
        )
    return _load_json(args.bundle)


# --- command implementations -------------------------------------------
def cmd_health(args: argparse.Namespace) -> int:
    svc = MarketService()
    report = svc.health()
    report["braid_ok"] = braid_hook.braid_ok()
    _emit(report)
    return 0


def cmd_descriptors(args: argparse.Namespace) -> int:
    _emit({"descriptors": all_descriptors(), "count": len(known_ids())})
    return 0


def cmd_genome(args: argparse.Namespace) -> int:
    lab = ModelGenomeLab(store=_store())
    if args.genome_cmd == "seed":
        out = seed_default_genomes(store=_store())
        _emit({"seeded": [g["model_id"] for g in out], "count": len(out)})
    elif args.genome_cmd == "register":
        g = lab.register(
            model_id=args.model_id, name=args.name, provider=args.provider,
            endpoint=args.endpoint, capabilities=args.capabilities,
            behavior_traits=args.behavior_traits, limits=args.limits,
            adapters=args.adapters, cost_per_call=args.cost_per_call,
            quality=args.quality, latency_ms=args.latency_ms,
            energy_units=args.energy_units, visibility=args.visibility,
        )
        _emit({"registered": g})
    elif args.genome_cmd == "get":
        _emit({"genome": lab.get(args.model_id)})
    elif args.genome_cmd == "list":
        _emit({"genomes": lab.list(visibility=args.visibility), "count": len(lab.list(visibility=args.visibility))})
    elif args.genome_cmd == "search":
        _emit({"matches": lab.search(args.query), "count": len(lab.search(args.query))})
    elif args.genome_cmd == "best-match":
        _emit({"best": lab.best_match(args.capability, max_cost=args.max_cost,
                                       min_quality=args.min_quality, prefer=args.prefer)})
    else:
        raise ValueError(f"unknown genome subcommand {args.genome_cmd!r}")
    return 0


def cmd_pricing(args: argparse.Namespace) -> int:
    brain = AdaptivePricingBrain(store=_store())
    if args.pricing_cmd == "quote":
        bundle = _require_bundle(args)
        quote = brain.quote(bundle, margin=args.margin, policy=args.policy,
                            reference_price=args.reference)
        _emit({"quote": quote})
    elif args.pricing_cmd == "decisions":
        _emit({"decisions": brain.decisions(bundle_id=args.bundle_id)})
    else:
        raise ValueError(f"unknown pricing subcommand {args.pricing_cmd!r}")
    return 0


def cmd_resource(args: argparse.Namespace) -> int:
    mkt = ResourceExchangeMarket(store=_store())
    if args.resource_cmd == "offer":
        _emit({"offer": mkt.offer(args.kind, args.units, args.unit_price, args.seller)})
    elif args.resource_cmd == "listings":
        _emit({"listings": mkt.listings(kind=args.kind)})
    elif args.resource_cmd == "take":
        _emit({"trade": mkt.take(args.offer_id, args.buyer, args.qty)})
    elif args.resource_cmd == "trades":
        _emit({"trades": mkt.trades()})
    else:
        raise ValueError(f"unknown resource subcommand {args.resource_cmd!r}")
    return 0


def cmd_inference(args: argparse.Namespace) -> int:
    lab = ModelGenomeLab(store=_store())
    mkt = InferenceMarketplace(lab, store=_store())
    if args.inference_cmd == "list":
        _emit({"listings": mkt.listings(), "count": len(mkt.listings())})
    elif args.inference_cmd == "list-model":
        _emit({"listing": mkt.list_model(args.model_id, args.price,
                                         min_quality=args.min_quality,
                                         available=args.available,
                                         visibility=args.visibility)})
    elif args.inference_cmd == "match":
        _emit({"match": mkt.match(args.task, capabilities=args.caps,
                                  max_price=args.max_price, min_quality=args.min_quality,
                                  prefer=args.prefer)})
    elif args.inference_cmd == "transact":
        _emit({"trade": mkt.transact(args.listing_id, args.buyer, units=args.units,
                                     settled=args.settled)})
    elif args.inference_cmd == "settle":
        _emit({"trade": mkt.settle(args.order_id)})
    elif args.inference_cmd == "trades":
        _emit({"trades": mkt.trades(buyer=args.buyer)})
    else:
        raise ValueError(f"unknown inference subcommand {args.inference_cmd!r}")
    return 0


def cmd_trade(args: argparse.Namespace) -> int:
    brain = AdaptivePricingBrain(store=_store())
    ex = ResourceExchange(brain, store=_store())
    if args.trade_cmd == "quote":
        bundle = _require_bundle(args)
        _emit({"quote": ex.quote(bundle, margin=args.margin, reference_price=args.reference)})
    elif args.trade_cmd == "execute":
        bundle = _require_bundle(args)
        trade = ex.execute(args.buyer, bundle, margin=args.margin,
                           reference_price=args.reference, wallet=args.wallet,
                           journal=not args.no_journal)
        _emit({"trade": trade})
    elif args.trade_cmd == "get":
        _emit({"trade": ex.get(args.trade_id)})
    elif args.trade_cmd == "all":
        _emit({"trades": ex.all(buyer=args.buyer)})
    else:
        raise ValueError(f"unknown trade subcommand {args.trade_cmd!r}")
    return 0


def cmd_journal(args: argparse.Namespace) -> int:
    if args.journal_cmd == "tail":
        _emit({"head": braid_hook.head_node()})
    elif args.journal_cmd == "node":
        _emit({"node": braid_hook.lookup(args.cid),
               "proved": braid_hook.prove_cid(args.cid)})
    elif args.journal_cmd == "prove":
        _emit({"cid": args.cid, "proved": braid_hook.prove_cid(args.cid)})
    else:
        raise ValueError(f"unknown journal subcommand {args.journal_cmd!r}")
    return 0


def cmd_capability(args: argparse.Namespace) -> int:
    mkt = CapabilityMarketplace(UCGClient(), store=_store())
    if args.cap_cmd == "nodes":
        _emit({"nodes": mkt._ucg.query("", active_only=False)})
    elif args.cap_cmd == "listings":
        _emit({"listings": mkt.listings(active_only=not args.all, cap_id=args.cap)})
    elif args.cap_cmd == "get":
        _emit({"listing": mkt.get_listing(args.listing_id)})
    elif args.cap_cmd == "publish":
        _emit({"listing": mkt.publish(args.cap_id, args.price, currency=args.currency,
                                      reserve=args.reserve, commission=args.commission,
                                      seller=args.seller, status=args.status)})
    elif args.cap_cmd == "buy":
        _emit({"trade": mkt.buy(args.listing_id, args.buyer, qty=args.qty)})
    elif args.cap_cmd == "trades":
        _emit({"trades": mkt.trades(buyer=args.buyer)})
    elif args.cap_cmd == "simulate":
        _emit(mkt.simulate())
    else:
        raise ValueError(f"unknown capability subcommand {args.cap_cmd!r}")
    return 0


def cmd_bundle(args: argparse.Namespace) -> int:
    store = _store()
    ucg = UCGClient()
    lab = ModelGenomeLab(store=store)
    cap_mkt = CapabilityMarketplace(ucg, store=store)
    brain = AdaptivePricingBrain(store=store)
    eng = ServiceBundlingEngine(lab, cap_mkt, brain, store=store)
    if args.bundle_cmd == "compose":
        _emit({"bundle": eng.compose(args.name, args.models, args.caps,
                                     description=args.description, target=args.target,
                                     owner=args.owner)})
    elif args.bundle_cmd == "ar-training":
        _emit({"bundle": eng.compose_ar_training_offer(
            vision_model=args.vision, coder_model=args.coder, strong_model=args.strong)})
    elif args.bundle_cmd == "price":
        _emit({"bundle": eng.price(args.bundle_id, margin=args.margin, policy=args.policy)})
    elif args.bundle_cmd == "list":
        _emit({"bundles": eng.list()})
    elif args.bundle_cmd == "get":
        _emit({"bundle": eng.get(args.bundle_id)})
    elif args.bundle_cmd == "delete":
        _emit({"deleted": eng.delete(args.bundle_id)})
    else:
        raise ValueError(f"unknown bundle subcommand {args.bundle_cmd!r}")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from .server import create_app
    uvicorn.run(create_app(store=_store()), host=args.host, port=args.port, log_level="warning")
    return 0


# --- argument surface ---------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="fs-mkt",
        description="mem30 marketplace organs: genome, pricing, inference, resource, "
                    "bundle state, braid-journaled trades, and the HTTP API.",
    )
    p.add_argument("--version", action="version", version=f"fs-mkt {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("health", help="real health: descriptors, UCG client, braid ledger")
    sub.add_parser("descriptors", help="the six real marketplace descriptors")

    # genome
    g = sub.add_parser("genome", help="Model Genome Lab (RM-061)")
    gg = g.add_subparsers(dest="genome_cmd", required=True)
    _ = gg.add_parser("seed", help="seed the lab with the real local model estate")
    r = gg.add_parser("register", help="register a genome (real validation)")
    r.add_argument("model_id")
    r.add_argument("--name", required=True)
    r.add_argument("--provider", required=True)
    r.add_argument("--endpoint", required=True)
    r.add_argument("--capabilities", nargs="+", default=[])
    r.add_argument("--behavior-traits", default="{}")
    r.add_argument("--limits", default="{}")
    r.add_argument("--adapters", nargs="+", default=[])
    r.add_argument("--cost-per-call", type=float, required=True)
    r.add_argument("--quality", type=float, required=True)
    r.add_argument("--latency-ms", type=float, required=True)
    r.add_argument("--energy-units", type=float, default=0.1)
    r.add_argument("--visibility", choices=["local", "peer", "paid"], default="local")
    getp = gg.add_parser("get", help="get one genome")
    getp.add_argument("model_id")
    listp = gg.add_parser("list", help="list genomes")
    listp.add_argument("--visibility", choices=["local", "peer", "paid"])
    s = gg.add_parser("search", help="search genomes by capability token")
    s.add_argument("query")
    bm = gg.add_parser("best-match", help="best genome for a capability under constraints")
    bm.add_argument("capability")
    bm.add_argument("--max-cost", type=float)
    bm.add_argument("--min-quality", type=float, default=0.0)
    bm.add_argument("--prefer", choices=["quality", "cost", "cost_quality"], default="quality")

    # pricing
    px = sub.add_parser("pricing", help="Adaptive Pricing Brain (RM-015)")
    pp = px.add_subparsers(dest="pricing_cmd", required=True)
    pq = pp.add_parser("quote", help="price a bundle from its real cost stack")
    _bundle_args(pq)
    pq.add_argument("--margin", type=float, default=0.2)
    pq.add_argument("--policy", choices=["cost_plus", "fair", "value"], default="fair")
    pq.add_argument("--reference", type=float)
    pd = pp.add_parser("decisions", help="recorded pricing decisions")
    pd.add_argument("--bundle-id")

    # resource
    res = sub.add_parser("resource", help="Resource Exchange Market (RM-012)")
    rs = res.add_subparsers(dest="resource_cmd", required=True)
    ro = rs.add_parser("offer", help="list a resource offer")
    ro.add_argument("kind", choices=["token", "compute", "seat", "credit", "bandwidth"])
    ro.add_argument("units", type=float)
    ro.add_argument("unit_price", type=float)
    ro.add_argument("seller")
    rl = rs.add_parser("listings", help="open offers")
    rl.add_argument("--kind", choices=["token", "compute", "seat", "credit", "bandwidth"])
    rt = rs.add_parser("take", help="fill an offer at ask")
    rt.add_argument("offer_id")
    rt.add_argument("buyer")
    rt.add_argument("qty", type=float)
    _ = rs.add_parser("trades", help="settled resource trades")

    # inference
    inf = sub.add_parser("inference", help="Adaptive Inference Marketplace (RM-070)")
    ii = inf.add_subparsers(dest="inference_cmd", required=True)
    ii.add_parser("list", help="active inference listings")
    lm = ii.add_parser("list-model", help="list a real registered genome at a price")
    lm.add_argument("model_id")
    lm.add_argument("price", type=float)
    lm.add_argument("--min-quality", type=float, default=0.0)
    lm.add_argument("--available", type=int, default=1)
    lm.add_argument("--visibility", choices=["local", "free", "paid", "peer"], default="paid")
    mt = ii.add_parser("match", help="match a task to real active listings")
    mt.add_argument("task")
    mt.add_argument("--caps", nargs="+", default=[])
    mt.add_argument("--max-price", type=float)
    mt.add_argument("--min-quality", type=float, default=0.0)
    mt.add_argument("--prefer", choices=["quality", "cost", "cost_quality"], default="quality")
    tx = ii.add_parser("transact", help="settle a purchase of a listing")
    tx.add_argument("listing_id")
    tx.add_argument("buyer")
    tx.add_argument("--units", type=int, default=1)
    tx.add_argument("--settled", action="store_true")
    st = ii.add_parser("settle", help="ack an in-flight order")
    st.add_argument("order_id")
    itr = ii.add_parser("trades", help="inference trades")
    itr.add_argument("--buyer")

    # capability
    cap = sub.add_parser("capability", help="Capability Marketplace (RM-010) on the live UCG")
    cc = cap.add_subparsers(dest="cap_cmd", required=True)
    cc.add_parser("nodes", help="all UCG capability nodes (RM-001 graph)")
    cl = cc.add_parser("listings", help="capability listings")
    cl.add_argument("--cap")
    cl.add_argument("--all", action="store_true", help="include inactive listings")
    cg = cc.add_parser("get", help="get one listing")
    cg.add_argument("listing_id")
    cp = cc.add_parser("publish", help="list a real UCG capability at a price")
    cp.add_argument("cap_id")
    cp.add_argument("price", type=float)
    cp.add_argument("--currency", default="token")
    cp.add_argument("--reserve", type=float, default=0.0)
    cp.add_argument("--commission", type=float, default=0.0)
    cp.add_argument("--seller", default="mem30")
    cp.add_argument("--status", default="active")
    cb = cc.add_parser("buy", help="buy a listing")
    cb.add_argument("listing_id")
    cb.add_argument("buyer")
    cb.add_argument("--qty", type=int, default=1)
    ctr = cc.add_parser("trades", help="capability trades")
    ctr.add_argument("--buyer")
    cc.add_parser("simulate", help="run the six runtime scenarios against real listings")

    # bundle
    bu = sub.add_parser("bundle", help="Service Bundling Engine (RM-087)")
    bs = bu.add_subparsers(dest="bundle_cmd", required=True)
    bc = bs.add_parser("compose", help="compose a bundle from real genomes + UCG nodes")
    bc.add_argument("name")
    bc.add_argument("--models", nargs="+", default=[])
    bc.add_argument("--caps", nargs="+", default=[])
    bc.add_argument("--description", default="")
    bc.add_argument("--target", default="composite")
    bc.add_argument("--owner", default="mem30")
    ba = bs.add_parser("ar-training", help="factory: the Phase-2 AR-training offer")
    ba.add_argument("--vision")
    ba.add_argument("--coder")
    ba.add_argument("--strong")
    bp = bs.add_parser("price", help="price an existing bundle via the pricing brain")
    bp.add_argument("bundle_id")
    bp.add_argument("--margin", type=float, default=0.2)
    bp.add_argument("--policy", choices=["cost_plus", "fair", "value"], default="fair")
    _ = bs.add_parser("list", help="list bundles")
    bg = bs.add_parser("get", help="get one bundle")
    bg.add_argument("bundle_id")
    bd = bs.add_parser("delete", help="delete a bundle")
    bd.add_argument("bundle_id")

    # trade
    tr = sub.add_parser("trade", help="Resource Exchange execution with braid journaling")
    ts = tr.add_subparsers(dest="trade_cmd", required=True)
    tq = ts.add_parser("quote", help="quote a bundle for a trade")
    _bundle_args(tq)
    tq.add_argument("--margin", type=float, default=0.2)
    tq.add_argument("--reference", type=float)
    te = ts.add_parser("execute", help="escrow + settle + journal to braid (real commit)")
    te.add_argument("buyer")
    _bundle_args(te)
    te.add_argument("--margin", type=float, default=0.2)
    te.add_argument("--reference", type=float)
    te.add_argument("--wallet", type=float)
    te.add_argument("--no-journal", action="store_true",
                   help="skip the braid journal write (local-only record)")
    tg = ts.add_parser("get", help="get one trade record")
    tg.add_argument("trade_id")
    ta = ts.add_parser("all", help="all trade records")
    ta.add_argument("--buyer")

    # journal
    j = sub.add_parser("journal", help="braid ledger journal lookup")
    js = j.add_subparsers(dest="journal_cmd", required=True)
    js.add_parser("tail", help="head node of the real braid ledger")
    jn = js.add_parser("node", help="read + prove one braid node")
    jn.add_argument("cid")
    jp = js.add_parser("prove", help="prove a cid against the braid ledger")
    jp.add_argument("cid")

    # serve
    sv = sub.add_parser("serve", help="run the real HTTP API")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8785)
    return p


def _bundle_args(bp: argparse.ArgumentParser) -> None:
    bp.add_argument("--bundle", help="bundle as JSON (models[] cost_per_call, capabilities[])")
    bp.add_argument("--from-genomes", nargs="+",
                    help="build the bundle from real registered genomes (model_ids)")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        handler = {
            "health": cmd_health,
            "descriptors": cmd_descriptors,
            "genome": cmd_genome,
            "pricing": cmd_pricing,
            "resource": cmd_resource,
            "inference": cmd_inference,
            "capability": cmd_capability,
            "bundle": cmd_bundle,
            "trade": cmd_trade,
            "journal": cmd_journal,
            "serve": cmd_serve,
        }[args.cmd]
        return handler(args)
    except (ValueError, PricingError, TradeError, CapabilityMarketError,
            BundleError, UCGUnavailable, braid_hook.BraidUnavailable) as e:
        print(f"fs-mkt: error: {e}", file=sys.stderr)
        return 1
    except Exception as e:  # noqa: BLE001 - CLI must surface any real store/ledger error
        print(f"fs-mkt: error: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())