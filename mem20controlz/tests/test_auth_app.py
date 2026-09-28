"""Auth and HTTP-surface tests for the control plane.

These cover what the registry/websites suite does not reach: the session
lifecycle, fail-closed behaviour, CF Access trust, and the fact that the
middleware actually protects every route rather than some of them.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PASSWORD = "correct horse battery staple"
SECRET = "unit-test-secret-value"


@pytest.fixture()
def client(monkeypatch):
    """A TestClient with a known password/secret and the registry stubbed.

    The registry stub matters: the real one shells out to every CLI on the box,
    which is far too slow and too host-dependent for a unit test.
    """
    monkeypatch.setenv("MEM20_CONTROL_PASSWORD", PASSWORD)
    monkeypatch.setenv("MEM20_CONTROL_SECRET", SECRET)
    monkeypatch.setenv("CONTROL_TRUST_CF_ACCESS", "0")

    import mem20controlz.registry as registry_mod

    monkeypatch.setattr(
        registry_mod,
        "registry",
        lambda **k: {"panels": [], "counts": {}, "total": 0},
    )

    from fastapi.testclient import TestClient

    from mem20controlz.app import app, clear_registry_cache

    # The sweep cache is process-global by design; clear it so each test starts
    # from a known-cold cache instead of inheriting a warm one.
    clear_registry_cache()
    return TestClient(app)


@pytest.fixture()
def logged_in(client):
    response = client.post("/api/auth/login", json={"password": PASSWORD})
    assert response.status_code == 200
    return client


# --- auth primitives -------------------------------------------------------


def test_correct_password_is_accepted(monkeypatch):
    from mem20controlz import auth

    monkeypatch.setenv("MEM20_CONTROL_PASSWORD", PASSWORD)
    assert auth.check_password(PASSWORD) is True


def test_wrong_password_is_rejected(monkeypatch):
    from mem20controlz import auth

    monkeypatch.setenv("MEM20_CONTROL_PASSWORD", PASSWORD)
    assert auth.check_password("definitely not the password") is False


def test_missing_configured_password_fails_closed(monkeypatch, tmp_path):
    from mem20controlz import auth

    monkeypatch.delenv("MEM20_CONTROL_PASSWORD", raising=False)
    monkeypatch.delenv("CONTROL_ADMIN_PASSWORD", raising=False)
    monkeypatch.setattr(auth, "SECRETS_FILE", str(tmp_path / "absent.env"))
    # No configured password must mean nothing can log in, not "allow all".
    assert auth.check_password("") is False
    assert auth.check_password("anything") is False


def test_session_roundtrip(monkeypatch):
    from mem20controlz import auth

    monkeypatch.setenv("MEM20_CONTROL_SECRET", SECRET)
    token = auth.issue_session()
    assert token
    assert auth.session_valid(token) is True


def test_no_secret_means_no_session(monkeypatch, tmp_path):
    from mem20controlz import auth

    monkeypatch.delenv("MEM20_CONTROL_SECRET", raising=False)
    monkeypatch.delenv("CONTROL_SESSION_SECRET", raising=False)
    monkeypatch.setattr(auth, "SECRETS_FILE", str(tmp_path / "absent.env"))
    assert auth.issue_session() is None
    assert auth.session_valid("irrelevant") is False


def test_tampered_session_is_rejected(monkeypatch):
    from mem20controlz import auth

    monkeypatch.setenv("MEM20_CONTROL_SECRET", SECRET)
    token = auth.issue_session()
    assert auth.session_valid(token[:-4] + "aaaa") is False


def test_session_signed_with_another_secret_is_rejected(monkeypatch):
    from mem20controlz import auth

    monkeypatch.setenv("MEM20_CONTROL_SECRET", "secret-one")
    token = auth.issue_session()
    monkeypatch.setenv("MEM20_CONTROL_SECRET", "secret-two")
    assert auth.session_valid(token) is False


def test_expired_session_is_rejected(monkeypatch):
    from mem20controlz import auth

    monkeypatch.setenv("MEM20_CONTROL_SECRET", SECRET)
    stale = auth._sign(str(time.time() - auth.SESSION_TTL_SECONDS - 60), SECRET)
    assert auth.session_valid(stale) is False


def test_garbage_tokens_are_rejected(monkeypatch):
    from mem20controlz import auth

    monkeypatch.setenv("MEM20_CONTROL_SECRET", SECRET)
    for token in ("", "no-dot-here", "abc.def", "...."):
        assert auth.session_valid(token) is False


def test_cf_identity_ignored_when_not_trusted(monkeypatch):
    from mem20controlz import auth

    monkeypatch.setenv("CONTROL_TRUST_CF_ACCESS", "0")
    forged = {"cf-access-authenticated-user-email": "attacker@evil.test"}
    assert auth.identity_from_headers(forged) is None


def test_cf_identity_trusted_when_enabled(monkeypatch):
    from mem20controlz import auth

    monkeypatch.setenv("CONTROL_TRUST_CF_ACCESS", "1")
    header = {"cf-access-authenticated-user-email": "admin@example.test"}
    assert auth.identity_from_headers(header) == "admin@example.test"


def test_auth_status_never_leaks_the_secret(monkeypatch):
    from mem20controlz import auth

    monkeypatch.setenv("MEM20_CONTROL_SECRET", SECRET)
    monkeypatch.setenv("MEM20_CONTROL_PASSWORD", PASSWORD)
    status = auth.auth_status()
    assert SECRET not in repr(status)
    assert PASSWORD not in repr(status)
    assert status["secret_configured"] is True
    assert status["password_configured"] is True


# --- HTTP surface ----------------------------------------------------------


def test_health_is_open_and_reports_ok(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_auth_status_is_reachable_without_a_session(client):
    response = client.get("/api/auth/status")
    assert response.status_code == 200
    assert "password_configured" in response.json()


def test_registry_requires_auth(client):
    assert client.get("/api/registry").status_code == 401


def test_registry_served_with_a_session(logged_in):
    assert logged_in.get("/api/registry").status_code == 200


def test_bad_login_is_401(client):
    assert client.post("/api/auth/login", json={"password": "nope"}).status_code == 401


def test_login_without_a_secret_is_503_not_200(client, monkeypatch):
    from mem20controlz import auth

    monkeypatch.setattr(auth, "issue_session", lambda: None)
    response = client.post("/api/auth/login", json={"password": PASSWORD})
    assert response.status_code == 503
    assert "error" in response.json()


def test_logout_requires_auth_then_succeeds(client):
    assert client.post("/api/auth/logout").status_code == 401
    client.post("/api/auth/login", json={"password": PASSWORD})
    assert client.post("/api/auth/logout").status_code == 200


def test_forged_cf_header_admits_nothing_when_untrusted(client):
    response = client.get(
        "/api/registry", headers={"cf-access-authenticated-user-email": "attacker@evil.test"}
    )
    assert response.status_code == 401


def test_registry_cache_reports_age_and_avoids_resweep(client, monkeypatch):
    import mem20controlz.registry as registry_mod

    calls = []

    def counting(**kwargs):
        calls.append(1)
        return {"panels": [], "counts": {}, "total": 0}

    monkeypatch.setattr(registry_mod, "registry", counting)
    client.post("/api/auth/login", json={"password": PASSWORD})

    first = client.get("/api/registry").json()
    second = client.get("/api/registry").json()

    assert first["cached"] is False
    assert second["cached"] is True
    assert len(calls) == 1, "a poll inside the TTL must not re-pay the whole sweep"


def test_coverage_endpoint_is_cached(client, monkeypatch):
    """A full audit is slow; the endpoint must not re-run it per request."""
    from mem20ops import clicheck

    calls = []

    def counting_audit(timeout=25):
        calls.append(timeout)
        return {"results": [], "totals": {"audited_clis": 0}}

    monkeypatch.setattr(clicheck, "audit", counting_audit)
    client.post("/api/auth/login", json={"password": PASSWORD})

    first = client.get("/api/cli/coverage").json()
    second = client.get("/api/cli/coverage").json()

    assert first["cached"] is False
    assert second["cached"] is True
    assert len(calls) == 1, "the coverage audit must be cached"
    assert isinstance(second["age_s"], (int, float))


def test_coverage_cache_is_not_shared_across_timeouts(client, monkeypatch):
    """An audit run with a 15s budget is not evidence for a 60s request."""
    from mem20ops import clicheck

    calls = []

    def counting_audit(timeout=25):
        calls.append(timeout)
        return {"results": [], "totals": {"audited_clis": 0}, "timeout_used": timeout}

    monkeypatch.setattr(clicheck, "audit", counting_audit)
    client.post("/api/auth/login", json={"password": PASSWORD})

    client.get("/api/cli/coverage?timeout=15").json()
    other = client.get("/api/cli/coverage?timeout=60").json()

    assert other["cached"] is False
    assert other["timeout_used"] == 60
    assert calls == [15, 60]


@pytest.mark.parametrize(
    "path",
    [
        "/api/registry",
        "/api/cli/coverage",
        "/api/websites/manifest",
        "/api/websites/sites",
        "/api/websites/dns",
        "/api/websites/health",
        "/api/websites/logs",
        "/api/websites/pages",
        "/api/dreams/manifest",
        "/api/dreams",
        "/api/dreams/idle-stats",
        "/api/dreams/hollow",
        "/api/dreams/runs",
        "/api/dreams/runs/run-abc123",
        "/api/dreams/dream-some-id",
        "/api/dreams/dream-some-id/chain",
    ],
)
def test_every_data_route_is_protected(client, path):
    assert client.get(path).status_code == 401, f"{path} is not protected"


@pytest.mark.parametrize(
    "call",
    [
        ("post", "/api/dreams", {"seed": "a brief"}),
        ("post", "/api/dreams/runs", {"dream_id": "dream-x", "iterations": 1}),
        ("post", "/api/dreams/dream-x/verify", None),
        ("post", "/api/dreams/dream-x/promote", {}),
    ],
)
def test_every_dream_write_route_is_protected(client, call):
    """Promotion and run spend money or move bytes, so they are gated too."""
    method, path, body = call
    response = getattr(client, method)(path, json=body) if body is not None else getattr(client, method)(path)
    assert response.status_code == 401, f"{method} {path} is not protected"


def test_dns_write_routes_are_protected(client):
    assert client.post("/api/websites/dns", json={}).status_code == 401
    assert client.delete("/api/websites/dns/abc123").status_code == 401


def test_dns_create_validates_required_fields(logged_in):
    assert logged_in.post("/api/websites/dns", json={"zone": "example.com"}).status_code == 422


def test_logs_lines_is_bounded(logged_in):
    assert logged_in.get("/api/websites/logs?lines=0").status_code == 422
    assert logged_in.get("/api/websites/logs?lines=999999").status_code == 422


def test_frontend_is_served(client):
    """The SPA is reachable without a session; only the API is guarded."""
    response = client.get("/")
    assert response.status_code == 200
    assert "<script" in response.text or "<div id=\"root\"" in response.text


def test_unknown_api_path_is_404_not_the_spa(client):
    # A mistyped API route must not silently return HTML, or a broken client
    # would look like a working one.
    assert client.get("/api/definitely-not-a-route").status_code == 404
