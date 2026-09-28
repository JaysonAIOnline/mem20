# mem20shopz

The mem20 storefront: catalog, Stripe Checkout, signature-verified webhooks, and
once-only auto-provisioning.

## Run it

```sh
systemctl status mem20shopz        # 127.0.0.1:8891
systemctl restart mem20shopz
curl -s http://127.0.0.1:8891/api/health
curl -s http://127.0.0.1:8891/api/readiness
```

`python -m mem20shopz --readiness` prints readiness and **exits 1 when the shop
cannot sell**, so it can be used as a gate in a deploy.

## Configuration

Read from the environment, falling back to `/opt/mem20/secrets/.env`.

| Key | Purpose |
| --- | --- |
| `STRIPE_SECRET_KEY` | server-side only; creates Checkout Sessions |
| `STRIPE_PUBLISHABLE_KEY` | safe for the browser |
| `STRIPE_WEBHOOK_SECRET` | verifies that a webhook really came from Stripe |
| `STRIPE_MODE` | optional; may narrow the mode but never promote a test key |

**The mode follows the key prefix, not the variable.** `sk_live_` means live.
Setting `STRIPE_MODE=live` alongside a `sk_test_` key still reports `test`,
because a mis-set variable must not be able to point a real storefront at test
keys while claiming otherwise.

## What fails closed, and why

These are refusals, not fallbacks:

- **No secret key** — no checkout session is created. Never a free one.
- **No webhook secret** — every event is rejected. Without it we cannot tell a
  real payment from a forged one, so trusting the body would let anyone POST a
  fake `checkout.session.completed` and provision themselves an account.
- **No Stripe Price or no amount** — the SKU is not purchasable. A price id with
  no amount could bill the wrong figure; an amount with no price id cannot be
  charged at all. Both are treated as unsellable.
- **Unparseable or unsigned body** — rejected before any handler runs.

## Webhooks

`POST /api/webhooks/stripe` takes the raw body, because the signature is
computed over the exact bytes Stripe sent — a re-serialised body will not verify.

Verification uses the Stripe SDK's `construct_event`, which is constant-time and
rejects timestamps outside a 300s tolerance, so a correctly signed but old
payload is refused as a replay. After verification the payload is parsed from
those same bytes, so there is no gap between what was checked and what is acted
on.

Only `checkout.session.completed` provisions. Every other event type is
acknowledged and ignored, so a new Stripe event cannot quietly start creating
accounts.

## Exactly once

Stripe redelivers, and a redelivery usually arrives after a restart. Event ids
are recorded in SQLite (`/opt/mem20/store/shop/events.sqlite3`) **before**
provisioning runs, and the primary key makes the check-and-claim atomic. A
repeat is refused. A crash mid-provision leaves the event claimed, so the retry
is refused rather than creating a second account for one payment.

## Auto-provisioning

The default handler is **dry-run**: it records what it would do and creates
nothing. That is deliberate — the payment path can be exercised end to end
without a real sale reaching a real system. `provisioning.register()` adds a real
handler at deployment; a handler that raises is recorded as a failed step and the
remaining handlers still run.

`GET /api/webhooks/status` reports the registered handlers, so "is provisioning
real or dry?" is answerable without reading code.

## Catalog

`mem20shopz/catalog.json` holds the SKUs across the five groups, one-time and
subscription. Prices ship **unset**: a SKU is sellable only once both
`price_id` and `amount_cents` are filled in. Until then the storefront shows
"price not set" with the reason, and checkout returns 409. Nothing is guessed.

## Tests

```sh
/root/.venv/bin/python -m pytest tests -q
/root/.venv/bin/ruff check mem20shopz tests
```

42 tests. Webhook signatures are produced by the Stripe SDK's own
`generate_signature_header`, so the tests exercise the same HMAC construction
Stripe uses rather than a hand-rolled approximation. Coverage includes: valid
signature, missing header, wrong secret, tampered body, garbage signature, stale
timestamp, missing secret, replayed event, replay surviving a restart, unrelated
event types, dry-run default, and a failing handler not stopping the rest.

Note: `generate_signature_header` does not decode bytes the way `verify_header`
does, so tests must hand it a decoded string or it signs the repr of the bytes.
