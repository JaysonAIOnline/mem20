"""Tests for mem20messenger's account, session and API surface.

The module builds its SQLite database at import time under
``$HOME/.mem20/messenger``, so the conftest points ``HOME`` at a temp directory
*before* the import. No production code is weakened to make this testable.
"""

from __future__ import annotations

import sqlite3
import sys
import time
from pathlib import Path

import pytest

# The conftest has already imported the real package and registered it under this
# name. Taking it from sys.modules avoids importing `conftest` by name, which
# collides with other packages' conftest files that are on sys.path.
_messenger = sys.modules["mem20messenger"]


@pytest.fixture(scope="session")
def messenger():
    """Import mem20messenger with HOME redirected at a throwaway path."""
    return _messenger

    return _messenger


@pytest.fixture(autouse=True)
def _clean_accounts(messenger):
    """Every test starts from an empty account and session table."""
    with messenger._db_lock:
        messenger._conn.execute("DELETE FROM accounts")
        messenger._conn.execute("DELETE FROM sessions")
        messenger._conn.commit()
    yield


@pytest.fixture(scope="session")
def client(messenger):
    from fastapi.testclient import TestClient

    return TestClient(messenger.app)


# --- password storage --------------------------------------------------------


def test_password_hashes_are_salted(messenger):
    """Two accounts with the same password must not share a stored hash."""
    a = messenger._hash_password("correct horse battery")
    b = messenger._hash_password("correct horse battery")
    assert a != b, "identical passwords produced identical hashes - no salt"
    assert a.count("$") == 1


def test_password_hash_never_contains_the_plaintext(messenger):
    stored = messenger._hash_password("hunter2hunter2")
    assert "hunter2hunter2" not in stored
    assert len(stored.split("$")[1]) == 64, "expected a hex sha256 digest"


def test_verify_accepts_the_right_password_and_rejects_others(messenger):
    stored = messenger._hash_password("s3cret-passphrase")
    assert messenger._verify_password("s3cret-passphrase", stored) is True
    assert messenger._verify_password("s3cret-passphras", stored) is False
    assert messenger._verify_password("", stored) is False


def test_verify_rejects_a_tampered_digest(messenger):
    stored = messenger._hash_password("s3cret-passphrase")
    salt, _, digest = stored.partition("$")
    flipped = "0" if digest[0] != "0" else "1"
    assert messenger._verify_password("s3cret-passphrase", f"{salt}${flipped}{digest[1:]}") is False


# --- registration rules ------------------------------------------------------


@pytest.mark.parametrize("username", ["ab", "x" * 33, "has space", "has/slash", "quote'"])
def test_register_rejects_bad_usernames(messenger, username):
    result = messenger._register(username, "longenoughpw")
    assert result["ok"] is False
    assert "username" in result["error"]


@pytest.mark.parametrize("username", ["abc", "a.b-c_d", "x" * 32, "MixedCase99"])
def test_register_accepts_reasonable_usernames(messenger, username):
    result = messenger._register(username, "longenoughpw")
    assert result["ok"] is True
    assert result["username"] == username


def test_register_rejects_short_passwords(messenger):
    result = messenger._register("someone", "short")
    assert result["ok"] is False
    assert "password" in result["error"]


def test_register_refuses_a_duplicate_username(messenger):
    assert messenger._register("twin", "longenoughpw")["ok"] is True
    second = messenger._register("twin", "differentpw")
    assert second["ok"] is False
    assert second["error"] == "username taken"


def test_register_does_not_overwrite_the_original_password(messenger):
    messenger._register("twin", "firstpassword")
    messenger._register("twin", "secondpassword")
    assert messenger._login("twin", "firstpassword")["ok"] is True
    assert messenger._login("twin", "secondpassword")["ok"] is False


# --- login -------------------------------------------------------------------


def test_login_succeeds_after_register(messenger):
    messenger._register("alice", "goodpassword")
    result = messenger._login("alice", "goodpassword")
    assert result["ok"] is True
    assert result["token"]


def test_login_fails_with_the_wrong_password(messenger):
    messenger._register("alice", "goodpassword")
    result = messenger._login("alice", "wrongpassword")
    assert result["ok"] is False
    assert result["error"] == "bad credentials"


def test_login_for_an_unknown_user_is_refused(messenger):
    result = messenger._login("nobody", "anypassword")
    assert result["ok"] is False
    assert result["error"] == "bad credentials", (
        "an unknown user must be indistinguishable from a wrong password"
    )


# --- sessions ----------------------------------------------------------------


def test_token_maps_back_to_its_user(messenger):
    result = messenger._register("carol", "goodpassword")
    assert messenger._user_for_token(result["token"]) == "carol"


def test_issuing_a_new_token_retires_the_old_one(messenger):
    """One active session per user: a new sign-in invalidates the previous token."""
    first = messenger._login("dave", "goodpassword")
    messenger._register("dave", "goodpassword")
    first = messenger._login("dave", "goodpassword")
    second = messenger._login("dave", "goodpassword")
    assert first["token"] != second["token"]
    assert messenger._user_for_token(second["token"]) == "dave"
    assert messenger._user_for_token(first["token"]) is None, (
        "the superseded token must stop working"
    )


def test_expired_token_is_rejected(messenger):
    result = messenger._register("erin", "goodpassword")
    with messenger._db_lock:
        messenger._conn.execute("UPDATE sessions SET expires=? WHERE token=?",
                                (time.time() - 1, result["token"]))
        messenger._conn.commit()
    assert messenger._user_for_token(result["token"]) is None


def test_empty_and_unknown_tokens_resolve_to_nothing(messenger):
    assert messenger._user_for_token("") is None
    assert messenger._user_for_token("made-up-token") is None


def test_tokens_are_long_and_unpredictable(messenger):
    token = messenger._register("frank", "goodpassword")["token"]
    assert len(token) >= 32, "token is too short to resist guessing"
    other = messenger._register("grace", "goodpassword")["token"]
    assert token != other


# --- username safety ---------------------------------------------------------


def test_re_safe_accepts_only_the_intended_character_set(messenger):
    assert messenger.re_safe("abc.XYZ-123_") is True
    assert messenger.re_safe("has space") is False
    assert messenger.re_safe("slash/es") is False
    assert messenger.re_safe("") is True, "an empty string is caught by the length rule instead"


# --- HTTP surface ------------------------------------------------------------


def test_health_is_public(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["service"] == "mem20messenger"
    assert body["roster"] > 0, "the roster should be populated"


def test_register_over_http_returns_a_working_token(client):
    response = client.post("/api/register", json={"username": "httpuser", "password": "longenoughpw"})
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert _messenger._user_for_token(body["token"]) == "httpuser"


def test_register_over_http_rejects_a_bad_request_with_400(client):
    response = client.post("/api/register", json={"username": "x", "password": "short"})
    assert response.status_code == 400
    assert response.json()["ok"] is False


def test_login_failure_is_401_not_200(client):
    client.post("/api/register", json={"username": "httpuser2", "password": "longenoughpw"})
    response = client.post("/api/login", json={"username": "httpuser2", "password": "wrongpassword"})
    assert response.status_code == 401
    assert response.json()["ok"] is False


def test_empty_chat_message_is_refused(client):
    token = client.post("/api/register", json={"username": "quiet", "password": "longenoughpw"}).json()["token"]
    response = client.post(
        "/api/chat", params={"token": token}, json={"bot": "assistant", "message": "   "}
    )
    assert response.status_code == 400
    assert response.json()["error"] == "message required"


def test_login_over_http(client):
    client.post("/api/register", json={"username": "httpuser", "password": "longenoughpw"})
    ok = client.post("/api/login", json={"username": "httpuser", "password": "longenoughpw"})
    assert ok.json()["ok"] is True
    bad = client.post("/api/login", json={"username": "httpuser", "password": "nope-nope-nope"})
    assert bad.json()["ok"] is False


def test_roster_requires_a_token(client):
    assert client.get("/api/roster").status_code == 401
    anonymous = client.get("/api/roster", params={"token": "not-a-token"})
    assert anonymous.status_code == 401, "a forged token must not open the roster"
    assert anonymous.json()["error"] == "unauthorized"


def test_roster_opens_with_a_real_token(client, monkeypatch):
    token = client.post("/api/register", json={"username": "chatty", "password": "longenoughpw"}).json()["token"]
    monkeypatch.setattr("mem20messenger.roster", lambda backend=None: ["assistant", "coder"])
    response = client.get("/api/roster", params={"token": token})
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["bots"] == ["assistant", "coder"]


def test_chat_requires_a_token(client):
    response = client.post("/api/chat", json={"bot": "assistant", "message": "hi"})
    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"


def test_database_file_is_created_under_the_redirected_home(messenger):
    assert Path(messenger.ACCOUNTS_DB).exists()
    with sqlite3.connect(messenger.ACCOUNTS_DB) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"accounts", "sessions"} <= tables
