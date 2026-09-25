"""CLI tests: every smoke command runs real organs against a temp store and
prints real JSON. braid/journalled subcommands hit the real ledger."""
from __future__ import annotations

import json

import pytest
from conftest import requires_ucg

from mem20mktz import braid_hook
from mem20mktz.cli import main


def run(capsys, argv, store):
    rc = main(argv)
    out = json.loads(capsys.readouterr().out)
    return rc, out


def test_health(env_store, capsys):
    rc, out = run(capsys, ["health"], env_store)
    assert rc == 0
    assert out["descriptor_count"] == 6
    assert out["ucg_ok"] is True
    assert out["braid_ok"] is True


def test_descriptors(env_store, capsys):
    rc, out = run(capsys, ["descriptors"], env_store)
    assert rc == 0
    assert out["count"] == 6


def test_genome_seed_and_list(env_store, capsys):
    rc, out = run(capsys, ["genome", "seed"], env_store)
    assert rc == 0 and out["count"] >= 1
    rc, out = run(capsys, ["genome", "list"], env_store)
    assert rc == 0 and out["count"] >= 1


def test_genome_list_visibility_filter(env_store, capsys):
    rc, out = run(capsys, ["genome", "list", "--visibility", "paid"], env_store)
    assert rc == 0 and out["genomes"] == []


def test_resource_offer_take_cli(env_store, capsys):
    rc, off = run(capsys, ["resource", "offer", "token", "100", "0.01", "seller-cli"], env_store)
    assert rc == 0 and off["offer"]["status"] == "open"
    rc, trade = run(capsys, ["resource", "take", off["offer"]["offer_id"], "buyer-cli", "5"], env_store)
    assert rc == 0 and trade["trade"]["status"] == "settled"


def test_pricing_quote_from_genomes(env_store, capsys):
    run(capsys, ["genome", "seed"], env_store)
    rc, out = run(capsys, ["pricing", "quote", "--from-genomes", "genome.litellm.fast",
                           "--margin", "0.2", "--policy", "fair"], env_store)
    assert rc == 0
    assert out["quote"]["price"] >= 0.0002 * 1.2 - 1e-9


def test_inference_list_transact_cli(env_store, capsys):
    run(capsys, ["genome", "seed"], env_store)
    rc, lm = run(capsys, ["inference", "list-model", "genome.litellm.fast", "0.0005",
                          "--available", "2"], env_store)
    assert rc == 0
    rc, tx = run(capsys, ["inference", "transact", lm["listing"]["listing_id"],
                          "cli-buyer", "--units", "2", "--settled"], env_store)
    assert rc == 0 and tx["trade"]["status"] == "settled"


@requires_ucg
def test_capability_cli(env_store, capsys):
    rc, out = run(capsys, ["capability", "nodes"], env_store)
    assert rc == 0 and len(out["nodes"]) >= 1
    cap_id = out["nodes"][0]["id"]
    rc, pub = run(capsys, ["capability", "publish", cap_id, "0.02", "--seller", "cli"], env_store)
    assert rc == 0 and pub["listing"]["status"] == "active"
    rc, buy = run(capsys, ["capability", "buy", pub["listing"]["listing_id"], "cli-buyer"],
                  env_store)
    assert rc == 0 and buy["trade"]["status"] == "settled"


def test_bundle_cli_compose_price(env_store, capsys):
    run(capsys, ["genome", "seed"], env_store)
    rc, b = run(capsys, ["bundle", "compose", "cli bundle", "--models", "genome.litellm.fast"],
                env_store)
    assert rc == 0 and b["bundle"]["bundle_id"].startswith("bundle-")
    rc, priced = run(capsys, ["bundle", "price", b["bundle"]["bundle_id"], "--margin", "0.2"],
                     env_store)
    assert rc == 0 and priced["bundle"]["price"] > 0


def test_trade_execute_journaled_cli_then_prove(env_store, capsys):
    if not braid_hook.braid_ok():
        pytest.skip("braid ledger unreachable")
    run(capsys, ["genome", "seed"], env_store)
    rc, t = run(capsys, ["trade", "execute", "cli-agent", "--from-genomes",
                         "genome.litellm.fast", "--reference", "0.5", "--wallet", "0.05"],
                env_store)
    assert rc == 0 and t["trade"]["status"] == "executed"
    cid = t["trade"]["provenance"]["cid"]
    assert t["trade"]["provenance"]["ok"] is True
    rc, prove = run(capsys, ["journal", "prove", cid], env_store)
    assert rc == 0 and prove["proved"] is True
    rc, node = run(capsys, ["journal", "node", cid], env_store)
    assert rc == 0 and node["node"]["cid"] == cid
    rc, tail = run(capsys, ["journal", "tail"], env_store)
    assert rc == 0 and tail["head"]["cid"] == cid


def test_trade_execute_cli_error_unfunded(env_store, capsys):
    rc = main(["trade", "execute", "poor-agent", "--bundle",
               '{"models":[{"model_id":"m","cost_per_call":0.01}],"capabilities":[]}',
               "--wallet", "0.0001", "--no-journal"])
    err = capsys.readouterr().err
    assert rc == 1 and "insufficient funds" in err


def test_unknown_subcommand_errors(capsys):
    with pytest.raises(SystemExit):
        main(["nonsense"])