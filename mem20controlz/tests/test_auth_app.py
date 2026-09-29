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


@pytest.fixture(autouse=True)
def _hermetic_secrets(monkeypatch, tmp_path):
    """Point the auth module at a temp secrets file for every test in this module.

    Auth reads the secrets *file* first and the environment only as a fallback, so
    a suite that merely set environment variables would quietly authenticate
    against the real ``/opt/mem20/secrets/.env`` on this host. That made a green
    suite depend on production secrets. Redirecting the file makes every test
    hermetic and is why a per-test ``setenv`` is no longer enough to change the
    configured credential.
    """
    path = tmp_path / "control.env"
    _write_secrets(path, PASSWORD, SECRET)
    monkeypatch.setattr(auth_module(), "SECRETS_FILE", str(path))
    for key in (
        "MEM20_CONTROL_PASSWORD",
        "CONTROL_ADMIN_PASSWORD",
        "MEM20_CONTROL_SECRET",
        "CONTROL_SESSION_SECRET",
    ):
        monkeypatch.delenv(key, raising=False)
    return path


def _write_secrets(path, password, secret):
    path.write_text(f"MEM20_CONTROL_PASSWORD={password}\nMEM20_CONTROL_SECRET={secret}\n")


@pytest.fixture()
def client(monkeypatch, tmp_path):
    """A TestClient with a known password/secret and the registry stubbed.

    The registry stub matters: the real one shells out to every CLI on the box,
    which is far too slow and too host-dependent for a unit test.
    """
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


def auth_module():
    from mem20controlz import auth

    return auth


@pytest.fixture()
def app_client_factory():
    """A TestClient that can impersonate a chosen peer address.

    Needed because loopback trust is a claim about the network, and a test has to
    state which network it is standing in.
    """
    from fastapi.testclient import TestClient

    from mem20controlz.app import app

    def _make(peer: str, port: int = 51234):
        return TestClient(app, client=(peer, port))

    return _make


@pytest.fixture()
def logged_in(client):
    response = client.post("/api/auth/login", json={"password": PASSWORD})
    assert response.status_code == 200
    return client


# --- auth primitives -------------------------------------------------------


def test_correct_password_is_accepted():
    from mem20controlz import auth

    assert auth.check_password(PASSWORD) is True


def test_wrong_password_is_rejected():
    from mem20controlz import auth

    assert auth.check_password("definitely not the password") is False


def test_a_password_change_takes_effect_without_a_restart(tmp_path, monkeypatch):
    """The bug: rotating the password appeared to do nothing until a restart.

    `llm.py` runs a dotenv load at import time and copies *every* key from the
    secrets file into `os.environ` - including the admin password, despite its
    docstring promising API keys only. The control plane imports it transitively
    via mem20dreamz, so the password got snapshotted into the process
    environment at boot, and `_password()` preferred the environment over the
    file. The file is the documented single home for these secrets, so it has to
    win, or a rotated password is silently ignored for the life of the process.
    """
    from mem20controlz import auth

    secrets_file = tmp_path / ".env"
    secrets_file.write_text(f"MEM20_CONTROL_SECRET={SECRET}\nMEM20_CONTROL_PASSWORD=first-value\n")

    # Stand in for the import-time snapshot: the environment holds the old value.
    monkeypatch.setenv("MEM20_CONTROL_PASSWORD", "first-value")
    monkeypatch.setattr(auth, "SECRETS_FILE", str(secrets_file))
    assert auth.check_password("first-value") is True

    # The file is rotated. No restart, no re-import.
    secrets_file.write_text(f"MEM20_CONTROL_SECRET={SECRET}\nMEM20_CONTROL_PASSWORD=second-value\n")

    assert auth.check_password("second-value") is True, "the rotated password must work at once"
    assert auth.check_password("first-value") is False, "the old one must stop working at once"


def test_the_environment_still_works_when_there_is_no_secrets_file(tmp_path, monkeypatch):
    """An env-only deployment must keep working, so env is a fallback, not a ban."""
    from mem20controlz import auth

    monkeypatch.setattr(auth, "SECRETS_FILE", str(tmp_path / "does-not-exist"))
    monkeypatch.setenv("MEM20_CONTROL_PASSWORD", PASSWORD)
    assert auth.check_password(PASSWORD) is True


def test_the_signing_secret_also_comes_from_the_file(tmp_path, monkeypatch):
    """A rotated session secret must take effect too, or old cookies outlive it."""
    from mem20controlz import auth

    secrets_file = tmp_path / ".env"
    secrets_file.write_text("MEM20_CONTROL_SECRET=old-secret-value\n")
    monkeypatch.setattr(auth, "SECRETS_FILE", str(secrets_file))
    stale = auth.issue_session()
    assert stale is not None

    secrets_file.write_text("MEM20_CONTROL_SECRET=new-secret-value-longer\n")
    fresh = auth.issue_session()
    assert fresh is not None
    assert auth._verify(fresh, "old-secret-value") is None, "the old secret must stop verifying"
    assert auth._verify(fresh, "new-secret-value-longer") is not None


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


def test_session_signed_with_another_secret_is_rejected(_hermetic_secrets):
    from mem20controlz import auth

    _write_secrets(_hermetic_secrets, PASSWORD, "secret-one")
    token = auth.issue_session()
    _write_secrets(_hermetic_secrets, PASSWORD, "secret-two")
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


PROXY_HEADERS_USED_BY_TESTS = (
    "x-forwarded-for", "x-forwarded-host", "x-forwarded-proto", "x-real-ip",
    "forwarded", "cf-connecting-ip", "true-client-ip", "x-client-ip",
)

# --- loopback trust ---------------------------------------------------------
#
# The owner asked not to be asked for a password on the box that owns the estate.
# That is granted, but as a *network fact* rather than by switching auth off: the
# peer really is a loopback socket, and the moment that stops being true the
# password applies again by itself.


def test_a_local_caller_is_admitted_without_a_password():
    from mem20controlz import auth

    assert auth.local_request_allowed("127.0.0.1", {}) is True
    assert auth.local_request_allowed("127.0.0.5", {}) is True
    assert auth.local_request_allowed("::1", {}) is True
    assert auth.local_request_allowed("::ffff:127.0.0.1", {}) is True


def test_a_remote_caller_is_never_admitted():
    from mem20controlz import auth

    assert auth.local_request_allowed("10.0.0.4", {}) is False
    assert auth.local_request_allowed("203.0.113.9", {}) is False
    assert auth.local_request_allowed("", {}) is False
    assert auth.local_request_allowed(None, {}) is False


@pytest.mark.parametrize("header", list(PROXY_HEADERS_USED_BY_TESTS))
def test_a_proxied_request_does_not_inherit_loopback_trust(header):
    """The whole point: a tunnel terminates here on a loopback socket too.

    Without this, exposing the panel through any reverse proxy would silently
    hand the whole control plane - DNS writes, dream promotion, money-spending
    runs - to whoever could reach the proxy.
    """
    from mem20controlz import auth

    assert auth.local_request_allowed("127.0.0.1", {header: "203.0.113.9"}) is False


def test_an_empty_forwarded_header_does_not_defeat_the_check():
    from mem20controlz import auth

    assert auth.local_request_allowed("127.0.0.1", {"x-forwarded-for": ""}) is True


def test_loopback_trust_can_be_switched_off(monkeypatch):
    from mem20controlz import auth

    monkeypatch.setenv("MEM20_CONTROL_TRUST_LOOPBACK", "0")
    assert auth.local_request_allowed("127.0.0.1", {}) is False


def test_the_status_endpoint_reports_the_layer():
    from mem20controlz import auth

    status = auth.auth_status()
    assert status["trust_loopback"] is True
    assert "loopback" in status["policy"]


def test_data_routes_are_open_to_a_local_caller(app_client_factory):
    """The user-visible consequence: no login screen, and the panel just works."""
    local = app_client_factory(peer="127.0.0.1")
    assert local.get("/api/dreams").status_code == 200
    assert local.get("/api/dreams/manifest").status_code == 200


def test_the_default_test_client_is_not_loopback(client):
    """Documents the real boundary: only an actual loopback peer is admitted.

    Starlette's TestClient presents itself as the host ``testclient``, which is
    not a loopback address, so a suite that does not say which peer it is
    impersonating must be refused. That is the guard working, not a gap in it.
    """
    assert client.get("/api/dreams").status_code == 401


def test_a_proxied_caller_still_has_to_authenticate(client):
    """Same route, arriving as a tunnel would: refused without a session."""
    proxied = {"x-forwarded-for": "203.0.113.9"}
    assert client.get("/api/dreams", headers=proxied).status_code == 401
    assert client.get("/api/dreams/manifest", headers=proxied).status_code == 401


def test_a_proxied_caller_can_still_log_in(client):
    response = client.post(
        "/api/auth/login", json={"password": PASSWORD}, headers={"x-forwarded-for": "203.0.113.9"}
    )
    assert response.status_code == 200
    assert client.get("/api/dreams", headers={"x-forwarded-for": "203.0.113.9"}).status_code == 200
