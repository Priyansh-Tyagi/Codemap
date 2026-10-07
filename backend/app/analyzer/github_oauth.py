"""
GitHub OAuth (classic OAuth App, authorization-code flow).

Why an OAuth App and not a GitHub App: a GitHub App's fine-grained,
per-repository installable permissions are the more "correct" long-term
design, but they require an installation flow (the user picks which repos
to grant, separately from signing in) and a different token-exchange shape
(installation tokens that expire hourly and must be refreshed). For a
portfolio tool whose actual goals are (1) each user bringing their own
rate limit and (2) being able to analyze their own private repos, a classic
OAuth App with the `repo` scope gets there in a quarter of the code. The
trade-off, stated plainly: `repo` grants read/write on every repo the user
can access, more than this tool needs (it only ever reads). Documented as
a known trade-off, not hidden.
"""

from __future__ import annotations

import os

import requests

AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
TOKEN_URL = "https://github.com/login/oauth/access_token"
USER_API_URL = "https://api.github.com/user"
SCOPE = "repo"
REQUEST_TIMEOUT_SECONDS = 15


class GitHubOAuthError(Exception):
    """Raised for any problem completing the OAuth handshake. Callers turn
    this into a redirect-with-error or a 400, never a 500 - these are all
    "the handshake didn't complete", not server bugs."""


def is_configured() -> bool:
    return bool(os.environ.get("CODEMAP_GITHUB_CLIENT_ID") and os.environ.get("CODEMAP_GITHUB_CLIENT_SECRET"))


def _client_id() -> str:
    return os.environ["CODEMAP_GITHUB_CLIENT_ID"]


def _client_secret() -> str:
    return os.environ["CODEMAP_GITHUB_CLIENT_SECRET"]


def build_authorize_url(state: str, redirect_uri: str) -> str:
    params = {
        "client_id": _client_id(),
        "redirect_uri": redirect_uri,
        "scope": SCOPE,
        "state": state,
        "allow_signup": "true",
    }
    query = "&".join(f"{k}={requests.utils.quote(v, safe='')}" for k, v in params.items())
    return f"{AUTHORIZE_URL}?{query}"


def exchange_code_for_token(code: str, redirect_uri: str) -> str:
    """Returns the access token, or raises GitHubOAuthError."""
    resp = requests.post(
        TOKEN_URL,
        data={
            "client_id": _client_id(),
            "client_secret": _client_secret(),
            "code": code,
            "redirect_uri": redirect_uri,
        },
        headers={"Accept": "application/json"},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    if not resp.ok:
        raise GitHubOAuthError(f"GitHub token exchange failed ({resp.status_code})")
    body = resp.json()
    if "error" in body:
        raise GitHubOAuthError(body.get("error_description", body["error"]))
    token = body.get("access_token")
    if not token:
        raise GitHubOAuthError("GitHub did not return an access token")
    return token


def fetch_github_user(access_token: str) -> dict:
    """Returns {"login": ..., "avatarUrl": ...}. Raises GitHubOAuthError on failure."""
    resp = requests.get(
        USER_API_URL,
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    if not resp.ok:
        raise GitHubOAuthError(f"Could not fetch GitHub user profile ({resp.status_code})")
    body = resp.json()
    return {"login": body["login"], "avatarUrl": body.get("avatar_url")}
