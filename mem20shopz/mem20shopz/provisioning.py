"""Auto-provisioning: what happens after a genuine payment.

The default handler is dry-run. It records exactly what it *would* provision and
provisions nothing, which is deliberate: the payment path can be exercised and
tested end to end without a real sale creating a real account somewhere in the
estate.

A live handler is registered explicitly with :func:`register`. Nothing here
guesses which system should receive an account - that is a deployment decision,
so the registry starts empty of real handlers and says so.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("mem20shopz.provisioning")

DRY_RUN = "dry-run"

Handler = Callable[["ProvisionRequest"], Any]

# Ordered, because a purchase may need several things done to it. Real handlers
# are inserted ahead of the dry-run by :func:`register`.
_HANDLERS: list[tuple[str, Handler]] = []


@dataclass
class ProvisionRequest:
    """What a handler is told about a completed purchase."""

    event_id: str
    event_type: str
    session_id: str
    customer_email: str = ""
    customer_id: str = ""
    sku_id: str = ""
    amount_cents: int | None = None
    currency: str = ""
    mode: str = "test"
    raw: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "session_id": self.session_id,
            "customer_email": self.customer_email,
            "customer_id": self.customer_id,
            "sku_id": self.sku_id,
            "amount_cents": self.amount_cents,
            "currency": self.currency,
            "mode": self.mode,
        }


@dataclass
class ProvisionResult:
    provisioned: bool
    handler: str
    detail: str = ""
    steps: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "provisioned": self.provisioned,
            "handler": self.handler,
            "detail": self.detail,
            "steps": self.steps,
        }


def _dry_run(request: ProvisionRequest) -> ProvisionResult:
    steps = [
        f"would create account for {request.customer_email or request.customer_id or 'unknown customer'}",
        f"would attach SKU {request.sku_id or 'unknown'}",
        f"would record receipt for session {request.session_id}",
    ]
    log.info("dry-run provisioning for event %s: %s", request.event_id, steps)
    return ProvisionResult(
        provisioned=False,
        handler=DRY_RUN,
        detail="dry-run: nothing was created",
        steps=steps,
    )


_HANDLERS.append((DRY_RUN, _dry_run))


def register(name: str, handler: Handler) -> None:
    """Add a real handler. Called by a deployment, never by a request."""
    _HANDLERS.insert(0, (name, handler))


def registered_handlers() -> list[str]:
    return [name for name, _ in _HANDLERS]


def is_dry_run() -> bool:
    return registered_handlers() == [DRY_RUN]


def provision(request: ProvisionRequest) -> ProvisionResult:
    """Run every handler in order, collecting what each one did.

    A handler that raises is recorded as a failed step and the rest still run:
    one broken step should not silently swallow the others.
    """
    steps: list[str] = []
    provisioned = False
    handler_name = DRY_RUN
    for name, handler in _HANDLERS:
        handler_name = name
        try:
            result = handler(request)
        except Exception as exc:
            log.exception("provisioning handler %s failed for %s", name, request.event_id)
            steps.append(f"{name}: FAILED {type(exc).__name__}: {exc}")
            continue
        if isinstance(result, ProvisionResult):
            provisioned = provisioned or result.provisioned
            steps.extend(f"{name}: {line}" for line in (result.steps or [result.detail]))
        else:
            provisioned = True
            steps.append(f"{name}: {result}")
    return ProvisionResult(provisioned=provisioned, handler=handler_name, steps=steps)
