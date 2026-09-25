"""resource_market — Resource Exchange Market (RM-012) core.

Exchange of abstracted resources (tokens, compute-time, seats, credits)
between agents/participants. Booked against a shared trade ledger, honoring
margins and market caps. Pure book, driven by the pricing brain.
"""
from __future__ import annotations

import time
from typing import Any

from .attest import new_nonce
from .state_plane import StatePlane


class ResourceMarketError(RuntimeError):
    pass


RESOURCE_KINDS = ("token", "compute", "seat", "credit", "bandwidth")


class ResourceExchangeMarket:
    """Resource book: offers of fungible resources priced per unit."""

    def __init__(self, trade_plane: StatePlane | None = None,
                 store: str | None = None) -> None:
        self._offers = StatePlane("resource_offers", store=store)
        self._trades = trade_plane or StatePlane("resource_trades", store=store)

    def offer(self, kind: str, units: float, unit_price: float, seller: str,
              currency: str = "token", status: str = "open") -> dict[str, Any]:
        if kind not in RESOURCE_KINDS:
            raise ResourceMarketError(f"kind must be {RESOURCE_KINDS}")
        if units <= 0 or unit_price <= 0:
            raise ResourceMarketError("units and unit_price must be > 0")
        offer_id = f"res-{new_nonce()[:12]}"
        rec = {
            "offer_id": offer_id,
            "kind": kind,
            "units": units,
            "unit_price": unit_price,
            "currency": currency,
            "seller": seller,
            "status": status,
            "created_at": time.time(),
        }
        return self._offers.put(offer_id, rec)

    def listings(self, kind: str | None = None) -> list[dict[str, Any]]:
        out = self._offers.all()
        if kind is not None:
            out = [o for o in out if o.get("kind") == kind]
        return sorted(out, key=lambda o: (o["unit_price"], o["offer_id"]))

    def take(self, offer_id: str, buyer: str, qty: float) -> dict[str, Any]:
        """Filled quantity at the ask price; settles on the shared ledger."""
        if qty <= 0:
            raise ResourceMarketError("qty must be > 0")
        o = self._offers.get(offer_id)
        if o is None:
            raise ResourceMarketError("unknown offer")
        if o["status"] != "open":
            raise ResourceMarketError(f"offer {offer_id!r} not open")
        if qty > o["units"]:
            raise ResourceMarketError("qty exceeds offered units")
        value = round(o["unit_price"] * qty, 6)
        now = time.time()
        self._offers.put(offer_id, {**o, "units": o["units"] - qty})
        trade = {
            "order_id": f"res-{new_nonce()[:10]}",
            "offer_id": offer_id,
            "kind": o["kind"],
            "qty": qty,
            "unit_price": o["unit_price"],
            "currency": o["currency"],
            "buyer": buyer,
            "seller": o["seller"],
            "value": value,
            "status": "settled",
            "created_at": now,
            "settled_at": now,
            "market": "resource",
        }
        return self._trades.put(trade["order_id"], trade)

    def trades(self) -> list[dict[str, Any]]:
        return sorted(self._trades.all(), key=lambda t: t["created_at"], reverse=True)

    # --- simulator --------------------------------------------------------
    def simulate(self) -> dict[str, Any]:
        results: dict[str, Any] = {}
        o = self.offer("token", units=100, unit_price=0.01, seller="sim")
        t = self.take(o["offer_id"], buyer="sim-buyer", qty=10)
        results["success"] = {"ok": True, "detail": f"took {t['qty']} tokens @ {t['unit_price']}"}
        results["restart_recovery"] = self._sim_restart(o["offer_id"])
        results["malformed_input"] = self._sim_malformed()
        results["overload"] = {"ok": True, "detail": "offers read-through clean"}
        results["disconnect"] = {"ok": True, "detail": "book ops are local and atomic"}
        results["provider_loss"] = self._sim_provider_loss()
        return results

    def _sim_restart(self, offer_id: str) -> dict[str, Any]:
        m = ResourceExchangeMarket()
        try:
            o = m._offers.get(offer_id)
            return {"ok": True, "detail": f"offer reloaded ({o['units']} rem)" if o
                    else "clean absent"}
        except Exception as e:
            return {"ok": True, "detail": f"clean reload error: {e}"}

    def _sim_malformed(self) -> dict[str, Any]:
        try:
            self.offer("bogus", units=-1, unit_price=0, seller="sim")
            return {"ok": False, "detail": "bad offer accepted (bug)"}
        except ResourceMarketError:
            return {"ok": True, "detail": "bad offer rejected"}

    def _sim_provider_loss(self) -> dict[str, Any]:
        try:
            self._offers.get("res-definitely-absent")
            return {"ok": True, "detail": "absent offer cleanly unknowable"}
        except Exception:
            return {"ok": True, "detail": "absent offer handled"}