"""
Tests for the GitHub OAuth handshake itself: state-cookie CSRF protection,
token exchange, session creation/lookup, and token-at-rest encryption.
Real network calls (GitHub's own endpoints) are mocked - these test our
code, not GitHub's.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest
from fastapi.testclient import TestClient

from main import app
from services import store

client = TestClient(app, follow_redirects=False)


@pytest.fixture(autouse=True)
def _clean_store():
    store.clear_all()
    yield
    store.clear_all()


@pytest.fixture
def github_configured(monkeypatch):
    monkeypatch.setenv("CODEMAP_GITHUB_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("CODEMAP_GITHUB_CLIENT_SECRET", "test-client-secret")


def test_login_redirects_to_github_with_a_state_param_and_sets_state_cookie(github_configured):
    resp = client.get("/api/auth/github/login")
    assert resp.status_code == 302
    assert resp.headers["location"].startswith("https://github.com/login/oauth/authorize?")
    assert "client_id=test-client-id" in resp.headers["location"]
    assert "state=" in resp.headers["location"]
    assert resp.cookies.get("codemap_oauth_state")


def test_login_without_configured_oauth_app_returns_503_not_a_crash(monkeypatch):
    # Explicit, not just "ambiently unset" - robust even if the developer
    # running this suite has a real backend/app/.env with real credentials
    # for their own local testing (load_dotenv uses override=False, so a
    # real .env would otherwise silently make this test meaningless).
    monkeypatch.delenv("CODEMAP_GITHUB_CLIENT_ID", raising=False)
    monkeypatch.delenv("CODEMAP_GITHUB_CLIENT_SECRET", raising=False)
    resp = client.get("/api/auth/github/login")
    assert resp.status_code == 503
    assert "not configured" in resp.json()["detail"]


def test_callback_rejects_mismatched_state_without_calling_github(github_configured, monkeypatch):
    import api.auth as auth_module

    called = []
    monkeypatch.setattr(auth_module, "exchange_code_for_token", lambda *a, **k: called.append(1))

    resp = client.get(
        "/api/auth/github/callback?code=abc&state=attacker-supplied",
        cookies={"codemap_oauth_state": "the-real-state"},
    )
    assert resp.status_code == 302
    assert "auth_error" in resp.headers["location"]
    assert called == []  # never reached the token exchange


def test_callback_rejects_missing_state_cookie(github_configured):
    resp = client.get("/api/auth/github/callback?code=abc&state=whatever")
    assert resp.status_code == 302
    assert "auth_error" in resp.headers["location"]


def test_successful_callback_creates_a_session_and_redirects_to_frontend(github_configured, monkeypatch):
    import api.auth as auth_module

    monkeypatch.setattr(auth_module, "exchange_code_for_token", lambda code, redirect_uri: "gho_faketoken")
    monkeypatch.setattr(
        auth_module, "fetch_github_user",
        lambda token: {"login": "octocat", "avatarUrl": "https://example.com/a.png"},
    )

    resp = client.get(
        "/api/auth/github/callback?code=abc&state=xyz",
        cookies={"codemap_oauth_state": "xyz"},
    )
    assert resp.status_code == 302
    assert resp.headers["location"] == "http://localhost:5173"
    session_cookie = resp.cookies.get("codemap_session")
    assert session_cookie

    me = client.get("/api/auth/me", cookies={"codemap_session": session_cookie})
    assert me.json() == {"user": {"login": "octocat", "avatarUrl": "https://example.com/a.png"}}


def test_me_with_no_session_cookie_reports_signed_out():
    assert client.get("/api/auth/me").json() == {"user": None}


def test_me_with_garbage_session_cookie_reports_signed_out_not_an_error():
    resp = client.get("/api/auth/me", cookies={"codemap_session": "not-a-real-session"})
    assert resp.status_code == 200
    assert resp.json() == {"user": None}


def test_logout_clears_the_session_cookie_and_invalidates_it(github_configured, monkeypatch):
    import api.auth as auth_module
    monkeypatch.setattr(auth_module, "exchange_code_for_token", lambda code, redirect_uri: "gho_x")
    monkeypatch.setattr(auth_module, "fetch_github_user", lambda token: {"login": "u", "avatarUrl": None})
    cb = client.get("/api/auth/github/callback?code=c&state=s", cookies={"codemap_oauth_state": "s"})
    sid = cb.cookies.get("codemap_session")

    assert client.get("/api/auth/me", cookies={"codemap_session": sid}).json()["user"] is not None
    client.post("/api/auth/logout", cookies={"codemap_session": sid})
    assert client.get("/api/auth/me", cookies={"codemap_session": sid}).json() == {"user": None}


def test_session_token_is_never_stored_in_plaintext_in_the_db(github_configured, monkeypatch):
    import api.auth as auth_module
    monkeypatch.setattr(auth_module, "exchange_code_for_token", lambda code, redirect_uri: "gho_SUPER_SECRET")
    monkeypatch.setattr(auth_module, "fetch_github_user", lambda token: {"login": "u", "avatarUrl": None})
    client.get("/api/auth/github/callback?code=c&state=s", cookies={"codemap_oauth_state": "s"})

    conn = store._connect()
    rows = conn.execute("SELECT encrypted_token FROM sessions").fetchall()
    conn.close()
    assert len(rows) == 1
    assert "gho_SUPER_SECRET" not in rows[0][0]


def test_undecryptable_session_token_is_treated_as_signed_out(monkeypatch):
    """Simulates CODEMAP_SECRET_KEY changing between restarts."""
    store.create_session("sess1", "octocat", None, "gho_x")
    monkeypatch.setattr("services.crypto.decrypt_token", lambda _: None)
    assert store.get_session("sess1") is None
