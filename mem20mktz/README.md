# mem20mktz

mem30 Phase 2 marketplace organs on the mem20 estate. Two marketplaces trade
real offers (release gate), plus service bundling, adaptive pricing, and
braid-journaled resource trades:

- **Inference Marketplace** (RM-070) on top of the Model Genome Lab (RM-061)
- **Resource Exchange Market** (RM-012) — quote, escrow, execute, then the
  settled trade is journaled as a signed, provable node on the mem20 braid
  ledger (the exit test: *the trade is a braid node*).
- **Capability Marketplace** (RM-010) on the Universal Capability Graph
  (live at `MEM20_UCG_URL`, default `http://127.0.0.1:8781`)
- **Adaptive Pricing Brain** (RM-015) — deterministic margin/fairness pricing
  from the real cost stack of a bundle
- **Service Bundling Engine** (RM-087) — compose priced composite offers from
  real model genomes + real UCG capability nodes

Everything endpoints here does real work. Honesty contract: a trade is only
ever reported executed when it was journaled; if the braid ledger is down the
call raises instead of fabricating a receipt.

## Install

```bash
cd /opt/mem20/mem20mktz
# the package's own venv already carries the compiled braid_python wheel so
# journaled trades can reach the real ledger:
.venv/bin/pip install -e .        # runtime + fs-mkt entry point
.venv/bin/pip install -e '.[dev]' # + pytest/httpx for the test suite
```

`braid_python` (and the `braid_keyz` source package it leans on) ship from
`/opt/mem20`, not PyPI — pip-install the wheel found under
`/opt/mem20/braid_python/target/wheels/` first if it is not already installed.

## CLI (`fs-mkt`)

Runs real code against real state planes and the real braid ledger:

```bash
fs-mkt health                    # descriptors, UCG client, braid_ok
fs-mkt descriptors               # the six real marketplace descriptors
fs-mkt genome seed               # seed the lab with the real local model estate
fs-mkt genome list
fs-mkt pricing quote --bundle '<json>' --margin 0.2 --policy fair
fs-mkt resource offer token 100 0.01 "agent-a"
fs-mkt resource take <offer_id> "agent-b" 10
fs-mkt inference list-model genome.litellm.fast 0.01
fs-mkt inference match "write tests" --caps code
fs-mkt capability nodes              # live UCG graph
fs-mkt capability publish cap.cv-inference.v1 0.05 --seller "mem30"
fs-mkt capability buy <listing_id> "agent-b"
fs-mkt bundle compose "AR stack" --models genome.litellm.fast --caps cap.cv-inference.v1
fs-mkt bundle price <bundle_id> --margin 0.2
fs-mkt bundle ar-training            # factory bundle for the Phase-2 exit test
fs-mkt trade execute "agent-a" --bundle '<json>' --reference 0.5   # real braid journal
fs-mkt trade all
fs-mkt journal tail               # head of the real braid ledger
fs-mkt journal node <cid>         # read + prove one node
fs-mkt journal prove <cid>
fs-mkt serve --port 8785          # real HTTP API (FastAPI + uvicorn)
```

Bundles can also be built from real registered genomes:

```bash
fs-mkt pricing quote --from-genomes genome.litellm.fast genome.litellm.balanced --margin 0.2
```

## HTTP API (`fs-mkt serve`)

Real endpoints, one per organ:

| Method | Path | Real backing |
|---|---|---|
| GET | `/health` | `MarketService.health()` + braid status |
| GET | `/descriptors` | `descriptor.all_descriptors()` |
| GET/POST | `/genomes` | `ModelGenomeLab` |
| POST | `/genomes/seed` | `genome.seed_default_genomes()` |
| POST | `/pricing/quote` | `AdaptivePricingBrain.quote()` |
| GET | `/pricing/decisions` | pricing decision plane |
| GET/POST | `/resource/offers` | `ResourceExchangeMarket.offer/listings` |
| POST | `/resource/take` | `ResourceExchangeMarket.take()` |
| GET | `/resource/trades` | settled trades plane |
| GET | `/inference/listings` | `InferenceMarketplace.listings()` |
| POST | `/inference/list-model` | `InferenceMarketplace.list_model()` |
| POST | `/inference/match` | `InferenceMarketplace.match()` |
| POST | `/inference/transact` | `InferenceMarketplace.transact()` |
| GET | `/inference/trades` | inference trade plane |
| GET | `/capability/nodes` | live UCG graph |
| GET/POST | `/capability/listings` | `CapabilityMarketplace.publish/listings` |
| POST | `/capability/buy` | `CapabilityMarketplace.buy()` |
| GET | `/capability/trades` | capability trade plane |
| POST | `/capability/simulate` | six runtime scenarios vs real listings |
| POST | `/bundle/compose` | `ServiceBundlingEngine.compose()` (genomes + UCG nodes) |
| POST | `/bundle/ar-training` | Phase-2 factory bundle |
| GET/POST | `/bundle` | list / price a bundle |
| POST | `/trade/quote` | `ResourceExchange.quote()` |
| POST | `/trade/execute` | `ResourceExchange.execute()` → real braid journal |
| GET | `/trades` | `ResourceExchange.all()` |
| GET | `/trades/{trade_id}` | `ResourceExchange.get()` |
| GET | `/journal/tail` | braid ledger head |
| GET | `/journal/node?cid=` | read + prove one braid node |
| GET | `/journal/prove?cid=` | prove a cid |

## Tests

```bash
.venv/bin/pytest
```

The suite asserts real behavior: braid-journaled trade happy path (provenance
`cid` present and `prove()`-able), CLI subcommands executing real organs, and
HTTP endpoints responding against a temp store.

## State

All planes default to `MEM20_STORE_PATH ~/.mem20/store` (shared with the rest
of the estate). Set `MEM20_MKTZ_STORE` to redirect the marketplace planes to a
different directory (the journal tests use this to stay hermetic).

## Honest gaps

- Everything wired in the CLI/HTTP surface is real. The capability market and
  service bundling require a live Universal Capability Graph; the estate runs
  one at `http://127.0.0.1:8781` (override with `MEM20_UCG_URL`). If the UCG
  is down, `fs-mkt capability *` / `fs-mkt bundle *` and the matching endpoints
  fail honestly with `UCGUnavailable` (HTTP 502) instead of faking a graph.
- Journaled commands require the braid ledger to be reachable through
  `/opt/mem20/braid_bridge.py`; if it is down, `fs-mkt journal *` and
  `fs-mkt trade execute` (journal mode) fail honestly with `BraidUnavailable`.

## Managed members (package-review integration)

Single-purpose marketplace organs grouped here by reference; they live in
their own top-level directories and are smoke-verified there:

- `mem20adaptiveinferencemarketplacez`
- `mem20adaptivepricingbrainz`
- `mem20capabilitymarketplacez`
- `mem20connectormarketplacez`
- `mem20globalcapabilitymarketplacez`
- `mem20hardwaremarketplacez`
- `mem20offerassemblyfabricz`
- `mem20resourceexchangemarketz`