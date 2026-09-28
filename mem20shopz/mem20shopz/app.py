"""The storefront service: catalog pages, checkout, and the Stripe webhook."""

from __future__ import annotations

import os
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from . import catalog, checkout, config, webhooks
from .__init__ import __version__
from .events import EventStore
from .webhooks import SIGNATURE_HEADER, WebhookError

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
EVENT_DB = os.environ.get("MEM20SHOP_EVENTS_DB", "/opt/mem20/store/shop/events.sqlite3")

app = FastAPI(
    title="mem20 shop",
    version=__version__,
    description="Storefront for the mem20 estate. Stripe Checkout, verified webhooks, one-time provisioning.",
)

_store: EventStore | None = None


def store() -> EventStore:
    global _store
    if _store is None:
        _store = EventStore(EVENT_DB)
    return _store


# --- public catalog -------------------------------------------------------


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "service": "mem20-shop", "version": __version__}


@app.get("/api/readiness")
def readiness() -> dict[str, Any]:
    """What the shop can and cannot do right now, and exactly why.

    Reported plainly so an operator can tell "not set up yet" from "broken".
    """
    return {
        **checkout.readiness(),
        "catalog": catalog.summary(),
        "events": webhooks.status(store()),
    }


@app.get("/api/catalog")
def get_catalog() -> dict[str, Any]:
    return {
        "currency": catalog.CURRENCY,
        "groups": catalog.groups(),
        "summary": catalog.summary(),
        "mode": config.mode(),
    }


@app.post("/api/checkout")
def post_checkout(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:  # noqa: B008
    """Create a Stripe Checkout Session. Refuses anything not fully configured."""
    sku_id = str(payload.get("sku_id", ""))
    base = str(payload.get("base_url", "")).rstrip("/")
    if not base:
        base = os.environ.get("MEM20SHOP_PUBLIC_URL", "http://127.0.0.1:8891")
    try:
        return checkout.create_session(
            sku_id=sku_id,
            success_url=f"{base}/checkout/success",
            cancel_url=f"{base}/checkout/cancel",
            quantity=int(payload.get("quantity", 1) or 1),
            customer_email=str(payload.get("email", "") or ""),
        )
    except checkout.CheckoutError as exc:
        # 409 rather than 500: the request was understood and deliberately
        # refused, which is a different thing from the service being broken.
        raise HTTPException(status_code=409, detail=str(exc)) from exc


# --- webhook --------------------------------------------------------------


@app.post("/api/webhooks/stripe")
async def stripe_webhook(request: Request) -> JSONResponse:
    """Stripe event intake.

    The raw body is required: the signature is computed over the exact bytes
    Stripe sent, so a re-serialised JSON body would not verify.
    """
    payload = await request.body()
    signature = request.headers.get(SIGNATURE_HEADER)
    try:
        report = webhooks.handle(payload, signature, store())
    except WebhookError as exc:
        # 400: we are telling Stripe we will not act on this. Refusing loudly is
        # what surfaces a misconfigured secret instead of silently dropping sales.
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    return JSONResponse(report)


@app.get("/api/webhooks/status")
def webhook_status() -> dict[str, Any]:
    return webhooks.status(store())


# --- storefront pages -----------------------------------------------------


def _page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(
        f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{title}</title>
<link rel="stylesheet" href="/static/style.css" />
</head>
<body>
<header class="bar">
  <span class="brand">mem20<span class="dim">.shop</span></span>
  <span class="dim mono" id="mode"></span>
</header>
{body}
<script src="/static/app.js"></script>
</body>
</html>"""
    )


def _index_html() -> str:
    path = os.path.join(STATIC_DIR, "index.html")
    with open(path, encoding="utf-8") as handle:
        return handle.read()


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    # A real standalone document, not a server-side skeleton: the page is
    # self-updating in the browser, so the markup only has to establish structure.
    return HTMLResponse(_index_html())


@app.get("/checkout/success", response_class=HTMLResponse)
def checkout_success() -> HTMLResponse:
    return _page(
        "Thank you",
        """<main class="wrap narrow">
<h1>Thank you</h1>
<p>Your payment is with Stripe. Provisioning runs from a verified webhook, not from this
page, so you will get your account even if you close the tab now.</p>
<p class="dim">If provisioning is still in dry-run mode, nothing has been created yet —
that is a deliberate setting, not a fault.</p>
</main>""",
    )


@app.get("/checkout/cancel", response_class=HTMLResponse)
def checkout_cancel() -> HTMLResponse:
    return _page(
        "Cancelled",
        """<main class="wrap narrow">
<h1>Cancelled</h1>
<p>Nothing was charged. The catalog is still here when you are ready.</p>
<p><a href="/">Back to the catalog</a></p>
</main>""",
    )


if os.path.isdir(STATIC_DIR):  # pragma: no cover - trivial wiring
    from fastapi.staticfiles import StaticFiles

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
