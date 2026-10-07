"""
GitHub OAuth endpoints and the session helpers other routers use to find
"is this request signed in, and with which GitHub token".

Flow: /github/login redirects to GitHub with a random `state`, which is
also stashed in a short-lived HttpOnly cookie (CSRF protection - GitHub
echoes `state` back on the callback, and we check it matches the cookie
before trusting anything). /github/callback exchanges the code for a
token, creates a session row, sets the long-lived session cookie, and
redirects back to the frontend. The session cookie holds only an opaque,
unguessable session_id - the real GitHub token never leaves the server.
"""

from __future__ import annotations

import os
import secrets
import urllib.parse

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, JSONResponse

from analyzer.github_oauth import (
    GitHubOAuthError, build_authorize_url, exchange_code_for_token,
    fetch_github_user, is_configured,
)
from services import store

router = APIRouter(prefix="/auth", tags=["auth"])

SESSION_COOKIE = "codemap_session"
STATE_COOKIE = "codemap_oauth_state"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 30  # 30 days
STATE_MAX_AGE_SECONDS = 60 * 10  # 10 minutes - just long enough to complete the redirect round trip


def _cookie_security() -> dict:
    """
    SameSite=Lax + no Secure flag works for local dev (localhost:5173 and
    localhost:8000 are different origins but the SAME "site" - SameSite
    classification ignores port - so the cookie IS sent on normal requests
    between them over plain HTTP).

    A real cross-domain deployment (e.g. a Vercel frontend + a Render
    backend) needs SameSite=None and Secure=True instead, which requires
    both sides to be served over HTTPS - browsers refuse SameSite=None
    cookies without Secure. Toggle with CODEMAP_COOKIE_SECURE=true.
    """
    if os.environ.get("CODEMAP_COOKIE_SECURE", "").lower() == "true":
        return {"secure": True, "samesite": "none"}
    return {"secure": False, "samesite": "lax"}


def _redirect_uri(request: Request) -> str:
    override = os.environ.get("CODEMAP_GITHUB_REDIRECT_URI")
    if override:
        return override
    return str(request.url_for("github_callback"))


def _frontend_url() -> str:
    return os.environ.get("CODEMAP_FRONTEND_URL", "http://localhost:5173")


def get_session_id(request: Request) -> str | None:
    return request.cookies.get(SESSION_COOKIE)


def get_current_session(request: Request) -> store.SessionRecord | None:
    """None if there's no cookie, an unknown session, or a session whose
    token can't be decrypted - all equivalent to "not signed in"."""
    return store.get_session(get_session_id(request))


def get_access_token_for_request(request: Request) -> str | None:
    """
    The user's own GitHub token if signed in, else None (callers fall back
    to the server-wide GITHUB_TOKEN env var, same as before OAuth existed -
    signing in is additive, never required).
    """
    session = get_current_session(request)
    return session.access_token if session else None


@router.get("/github/login")
def github_login(request: Request):
    if not is_configured():
        return JSONResponse(
            status_code=503,
            content={"detail": "GitHub sign-in is not configured on this server "
                                "(CODEMAP_GITHUB_CLIENT_ID / CODEMAP_GITHUB_CLIENT_SECRET unset)."},
        )
    state = secrets.token_urlsafe(24)
    url = build_authorize_url(state, _redirect_uri(request))
    response = RedirectResponse(url, status_code=302)
    response.set_cookie(
        STATE_COOKIE, state, max_age=STATE_MAX_AGE_SECONDS, httponly=True, path="/api/auth", **_cookie_security()
    )
    return response


@router.get("/github/callback", name="github_callback")
def github_callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None):
    frontend = _frontend_url()
    cookie_state = request.cookies.get(STATE_COOKIE)

    def _fail(message: str) -> RedirectResponse:
        resp = RedirectResponse(f"{frontend}/?auth_error={urllib.parse.quote(message, safe='')}", status_code=302)
        resp.delete_cookie(STATE_COOKIE, path="/api/auth")
        return resp

    if error:
        return _fail(f"GitHub sign-in was cancelled ({error})")
    if not code or not state or not cookie_state or state != cookie_state:
        return _fail("GitHub sign-in failed (invalid or expired state - please try again)")

    try:
        access_token = exchange_code_for_token(code, _redirect_uri(request))
        user = fetch_github_user(access_token)
    except GitHubOAuthError as e:
        return _fail(str(e))

    session_id = secrets.token_urlsafe(32)
    store.create_session(session_id, user["login"], user.get("avatarUrl"), access_token)

    response = RedirectResponse(frontend, status_code=302)
    response.delete_cookie(STATE_COOKIE, path="/api/auth")
    response.set_cookie(
        SESSION_COOKIE, session_id, max_age=SESSION_MAX_AGE_SECONDS, httponly=True, path="/", **_cookie_security()
    )
    return response


@router.get("/me")
def get_me(request: Request):
    session = get_current_session(request)
    if session is None:
        return {"user": None}
    return {"user": {"login": session.github_login, "avatarUrl": session.github_avatar_url}}


@router.post("/logout")
def logout(request: Request):
    store.delete_session(get_session_id(request))
    response = JSONResponse({"ok": True})
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response

