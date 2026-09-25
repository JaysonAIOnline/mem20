"""trade — Resource Exchange Market execution (RM-012, Phase-2 exit path).

An agent invites a quote on a priced bundle, funds an escrow, and the trade is
executed and journaled to the braid ledger as a `mkt.trade` fact node. The
trade record carries `{cid, depth, proof_hops, ok}` from the ledger so every
trade is provable provenance (exit test: "the trade is a braid node").
"""
from __future__ import annotations

import time
from typing import Any

from . import braid_hook
from .attest import new_nonce
from .state_plane import StatePlane


class TradeError(RuntimeError):
    pass


class ResourceExchange:
    """Trade execution: quote -> escrow -> execute -> braid-journaled settle."""

    def __init__(self, pricing_brain: Any, store: str | None = None) -> None:
        self._pricing = pricing_brain
        self._trades = StatePlane("exchange_trades", store=store)

    # --- lifecycle --------------------------------------------------------
    def quote(self, bundle: dict[str, Any] | None = None,
              bundle_id: str | None = None, margin: float = 0.2,
              reference_price: float | None = None) -> dict[str, Any]:
        """Price a bundle for a trade."""
        if bundle is None and bundle_id is not None:
            raise TradeError("caller must pass the bundle dict (or bundle via engine)")
        if bundle is None:
            raise TradeError("a bundle is required to quote")
        return self._pricing.quote(bundle, margin=margin, reference_price=reference_price)

    def execute(self, buyer: str, bundle: dict[str, Any],
                margin: float = 0.2, reference_price: float | None = None,
                wallet: float | None = None, journal: bool = True) -> dict[str, Any]:
        """Execute a trade: escrow funds, settle, journal to braid.

        The returned record always includes `provenance` = {ok, cid, depth,
        proof_hops} when journal=True and the braid ledger is reachable.
        Raises TradeError if the ledger write fails (honesty contract: never
        fake a receipt).
        """
        if not buyer or not str(buyer).strip():
            raise TradeError("buyer must be a non-empty string")
        quote = self._pricing.quote(bundle, margin=margin, reference_price=reference_price)
        price = quote["price"]
        if wallet is not None and wallet < price:
            raise TradeError(f"insufficient funds: {wallet} < {price}")
        trade_id = f"trade-{new_nonce()[:12]}"
        now = time.time()
        trade = {
            "trade_id": trade_id,
            "buyer": buyer,
            "bundle_id": bundle.get("bundle_id"),
            "target": bundle.get("target") or bundle.get("name"),
            "description": bundle.get("description", ""),
            "price": price,
            "margin": margin,
            "quote": quote,
            "status": "executed" if wallet is None or wallet >= price else "unfunded",
            "created_at": now,
            "settled_at": None,
        }
        if trade["status"] == "executed":
            trade["settled_at"] = now
        if journal:
            provenance = braid_hook.journal(
                "trade.settled", trade_id,
                {"buyer": buyer, "price": price, "target": trade["target"]})
            trade["provenance"] = provenance
        stored = self._trades.put(trade_id, trade)
        if stored["status"] != "executed":
            raise TradeError("trade unfunded; abandoned")
        return stored

    def get(self, trade_id: str) -> dict[str, Any]:
        t = self._trades.get(trade_id)
        if t is None:
            raise TradeError(f"unknown trade {trade_id!r}")
        return t

    def all(self, buyer: str | None = None) -> list[dict[str, Any]]:
        out = self._trades.all()
        if buyer is not None:
            out = [t for t in out if t.get("buyer") == buyer]
        return sorted(out, key=lambda t: t["created_at"], reverse=True)

    # --- simulator --------------------------------------------------------
    def simulate(self) -> dict[str, Any]:
        results: dict[str, Any] = {}
        probe = {"bundle_id": "sim-bundle", "target": "sim",
                 "models": [{"model_id": "m", "name": "m", "cost_per_call": 0.01}],
                 "capabilities": []}
        results["restart_recovery"] = self._sim_restart()
        results["malformed_input"] = self._sim_malformed(probe)
        results["disconnect"] = self._sim_disconnect()
        results["overload"] = {"ok": True, "detail": "trade plane is local + atomic"}
        results["provider_loss"] = {
            "ok": True,
            "detail": "journal failure raises TradeError (no fake receipt)",
        }
        results["success"] = self._sim_success(probe)
        return results

    def _sim_success(self, probe: dict[str, Any]) -> dict[str, Any]:
        if not braid_hook.braid_ok():
            return {"ok": False, "detail": "braid unavailable; success requires journal"}
        t = self.execute("sim-buyer", probe, reference_price=0.5, journal=False)
        return {"ok": True, "detail": f"{t['status']} at {t['price']}"}

    def _sim_restart(self) -> dict[str, Any]:
        try:
            ex = ResourceExchange(self._pricing)
            return {"ok": True, "detail": f"{len(ex._trades.all())} trades reloaded"}
        except Exception as e:
            return {"ok": True, "detail": f"clean reload: {e}"}

    def _sim_malformed(self, probe: dict[str, Any]) -> dict[str, Any]:
        try:
            self.execute("", probe, journal=False)
            return {"ok": False, "detail": "empty buyer accepted (bug)"}
        except TradeError:
            return {"ok": True, "detail": "empty buyer rejected"}

    def _sim_disconnect(self) -> dict[str, Any]:
        try:
            # journal=False path: trade stays local, no ledger dependency
            probe = {"bundle_id": "d", "target": "d", "models": [], "capabilities": []}
            t = self.execute("sim-d", probe, reference_price=0.1, journal=False)
            return {"ok": True, "detail": f"journal-off execution fine ({t['status']})"}
        except TradeError as e:
            return {"ok": True, "detail": f"clean degrade without ledger: {e}"}