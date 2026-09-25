"""Shared fixtures: every test runs against a private temp store so nothing
touches the estate's real planes. The braid ledger is shared and real by
design (journaled trades are the exit test), so the few tests that journal
assert actual provenance instead of stubbing it."""
from __future__ import annotations

import os

import pytest


@pytest.fixture()
def store(tmp_path):
    store_dir = str(tmp_path / "mktz")
    os.makedirs(store_dir, exist_ok=True)
    return store_dir


@pytest.fixture()
def env_store(monkeypatch, store):
    monkeypatch.setenv("MEM20_MKTZ_STORE", store)
    return store


def ucg_alive() -> bool:
    try:
        from mem20mktz.ucg_client import UCGClient, ucg_ok

        return ucg_ok(UCGClient())
    except Exception:
        return False


requires_ucg = pytest.mark.skipif(
    not ucg_alive(), reason="live UCG at MEM20_UCG_URL required for UCG-backed flows"
)