"""The shop catalog: five groups, one-time and subscription pricing.

Prices are data, and this module treats unpriced data as a hard error rather
than a zero. A SKU with no configured amount cannot be bought, and the storefront
says so instead of quietly selling something for the wrong number.

Each SKU carries a ``price_id`` - the Stripe Price it bills against. Until a real
Stripe Price exists, the SKU stays unconfigured: it renders with its name and
description, and checkout refuses it with a reason.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CURRENCY = "usd"
CATALOG_PATH = Path(__file__).with_name("catalog.json")

ONE_TIME = "one_time"
SUBSCRIPTION = "subscription"

# The five catalog groups. Display-only metadata; the sellable items live under
# "skus" in catalog.json.
GROUPS = (
    {"id": "foundations", "title": "Foundations", "blurb": "Ship your first mem20 service."},
    {"id": "operations", "title": "Operations", "blurb": "Run and observe it in production."},
    {"id": "intelligence", "title": "Intelligence", "blurb": "Memory, cognition and agents."},
    {"id": "creative", "title": "Creative", "blurb": "3D, game and generative pipelines."},
    {"id": "support", "title": "Support", "blurb": "Hands-on help from the people who built it."},
)


class CatalogError(ValueError):
    """The catalog on disk does not make sense."""


@dataclass(frozen=True)
class Sku:
    id: str
    group: str
    name: str
    description: str
    kind: str = ONE_TIME
    price_id: str = ""
    amount_cents: int | None = None
    features: tuple[str, ...] = field(default_factory=tuple)

    @property
    def configured(self) -> bool:
        """Sellable only with both a Stripe Price and a real amount.

        Both are required. A price id with no amount would bill the wrong figure,
        and an amount with no price id cannot be charged at all.
        """
        return bool(self.price_id) and isinstance(self.amount_cents, int) and self.amount_cents > 0

    def price_label(self) -> str:
        if not self.configured:
            return "price not set"
        amount = self.amount_cents or 0
        if self.kind == SUBSCRIPTION:
            return f"${amount / 100:,.2f}/mo"
        return f"${amount / 100:,.2f}"

    def unconfigured_reason(self) -> str:
        if not self.price_id:
            return "no Stripe Price is linked to this SKU yet"
        if not isinstance(self.amount_cents, int) or self.amount_cents <= 0:
            return "no price amount is configured for this SKU"
        return ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "group": self.group,
            "name": self.name,
            "description": self.description,
            "kind": self.kind,
            "price_id": self.price_id,
            "amount_cents": self.amount_cents,
            "currency": CURRENCY,
            "configured": self.configured,
            "price_label": self.price_label(),
            "unconfigured_reason": self.unconfigured_reason(),
            "features": list(self.features),
        }


def _load() -> list[Sku]:
    if not CATALOG_PATH.exists():
        return []
    try:
        raw = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CatalogError(f"{CATALOG_PATH} is not valid JSON: {exc}") from exc

    known = {g["id"] for g in GROUPS}
    skus: list[Sku] = []
    for entry in raw.get("skus", []):
        missing = [f for f in ("id", "group", "name") if not entry.get(f)]
        if missing:
            raise CatalogError(f"SKU {entry!r} is missing {', '.join(missing)}")
        if entry["group"] not in known:
            raise CatalogError(f"SKU {entry['id']!r} has unknown group {entry['group']!r}")
        kind = entry.get("kind", ONE_TIME)
        if kind not in (ONE_TIME, SUBSCRIPTION):
            raise CatalogError(f"SKU {entry['id']!r} has unknown kind {kind!r}")
        amount = entry.get("amount_cents")
        if amount is not None and not isinstance(amount, int):
            raise CatalogError(f"SKU {entry['id']!r} amount_cents must be an integer")
        skus.append(
            Sku(
                id=entry["id"],
                group=entry["group"],
                name=entry["name"],
                description=entry.get("description", ""),
                kind=kind,
                price_id=entry.get("price_id", "") or "",
                amount_cents=amount,
                features=tuple(entry.get("features", [])),
            )
        )
    return skus


def all_skus() -> list[Sku]:
    return sorted(_load(), key=lambda s: (s.group, s.id))


def get_sku(sku_id: str) -> Sku | None:
    return next((s for s in all_skus() if s.id == sku_id), None)


def groups() -> list[dict[str, Any]]:
    """The five groups, each with its SKUs and how many are actually sellable."""
    skus = all_skus()
    out: list[dict[str, Any]] = []
    for group in GROUPS:
        members = [s for s in skus if s.group == group["id"]]
        out.append(
            {
                **group,
                "skus": [s.as_dict() for s in members],
                "count": len(members),
                "configured_count": sum(1 for s in members if s.configured),
            }
        )
    return out


def is_configured() -> bool:
    """True when at least one SKU is genuinely sellable."""
    return any(s.configured for s in all_skus())


def summary() -> dict[str, Any]:
    skus = all_skus()
    return {
        "currency": CURRENCY,
        "groups": len(GROUPS),
        "skus": len(skus),
        "configured": sum(1 for s in skus if s.configured),
        "unconfigured": sum(1 for s in skus if not s.configured),
        "subscriptions": sum(1 for s in skus if s.kind == SUBSCRIPTION),
        "sellable": is_configured(),
    }
