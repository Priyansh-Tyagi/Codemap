"""
Server-side security settings and checks shared by the API layer.

Everything is read from the environment at call time (not import time) so a
deployment's settings are what counts and tests can change them freely.
Defaults are the SAFE ones: a deployment that forgets to configure anything
must not be the vulnerable one.
"""

from __future__ import annotations

import os

from fastapi import HTTPException
from fastapi.middleware.trustedhost import TrustedHostMiddleware

_TRUE = {"1", "true", "yes", "on"}


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUE


# ---------------------------------------------------------------------------
# Local-path analysis
# ---------------------------------------------------------------------------
# "Analyze this folder on the server" is exactly what a developer wants on
# their own machine, and exactly what must never be reachable on a public
# server: it lets any visitor enumerate the server's filesystem and map the
# server's own source code. So it is OFF unless explicitly enabled.

def local_paths_allowed() -> bool:
    return _flag("CODEMAP_ALLOW_LOCAL_PATHS")


def _local_roots() -> list[str]:
    raw = os.environ.get("CODEMAP_LOCAL_PATH_ROOTS", "")
    return [os.path.realpath(p.strip()) for p in raw.split(os.pathsep) if p.strip()]


def resolve_local_path(path: str) -> str:
    """
    Gate for a user-supplied local path. Returns the path to analyze, or
    raises a 403. When CODEMAP_LOCAL_PATH_ROOTS is set (os.pathsep-separated
    list), only folders inside one of those roots are allowed - symlinks are
    resolved first, so a link cannot be used to step outside them.
    """
    if not local_paths_allowed():
        raise HTTPException(
            status_code=403,
            detail=(
                "Analyzing local folders is disabled on this server. Use a GitHub URL, or "
                "set CODEMAP_ALLOW_LOCAL_PATHS=true when running CodeMap on your own machine."
            ),
        )
    roots = _local_roots()
    if not roots:
        return path
    real = os.path.realpath(path)
    for root in roots:
        try:
            if os.path.commonpath([root, real]) == root:
                return real
        except ValueError:  # different drives on Windows
            continue
    raise HTTPException(status_code=403, detail="That folder is outside the directories this server may analyze.")


# ---------------------------------------------------------------------------
# Origins / hosts
# ---------------------------------------------------------------------------

DEFAULT_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"


def allowed_origins() -> list[str]:
    origins = [o.strip().rstrip("/") for o in os.environ.get("CODEMAP_ALLOWED_ORIGINS", DEFAULT_ORIGINS).split(",")]
    origins = [o for o in origins if o]
    if "*" in origins:
        # Credentials (the session cookie) + a wildcard origin would let ANY
        # website make authenticated requests as the signed-in user.
        raise RuntimeError("CODEMAP_ALLOWED_ORIGINS must list explicit origins, never '*' (cookies are sent).")
    return origins


def allowed_hosts() -> list[str] | None:
    raw = os.environ.get("CODEMAP_ALLOWED_HOSTS", "")
    hosts = [h.strip() for h in raw.split(",") if h.strip()]
    return hosts or None


def docs_enabled() -> bool:
    return not _flag("CODEMAP_DISABLE_DOCS")


# ---------------------------------------------------------------------------
# Tunable limits (requests per window, per client address)
# ---------------------------------------------------------------------------

def _int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, default)))
    except ValueError:
        return default


def analyze_rate() -> tuple[int, int]:
    """(max uncached analyses, window seconds). Cache hits are free and not counted."""
    return _int_env("CODEMAP_ANALYZE_LIMIT", 12), _int_env("CODEMAP_ANALYZE_WINDOW_SECONDS", 600)


def narrate_rate() -> tuple[int, int]:
    return _int_env("CODEMAP_NARRATE_LIMIT", 6), _int_env("CODEMAP_NARRATE_WINDOW_SECONDS", 3600)


def global_rate() -> tuple[int, int]:
    return _int_env("CODEMAP_GLOBAL_LIMIT", 600), 60


def max_projects() -> int:
    return _int_env("CODEMAP_MAX_PROJECTS", 5000)


class HostCheckExceptHealth(TrustedHostMiddleware):
    """TrustedHostMiddleware, except GET/HEAD /api/health skips the Host check.

    Platform health checkers (Render's among them) address the container by its
    private IP, not the public hostname. Starlette's check has no exceptions, so
    the app answered its own platform with 400 and the deploy looped as
    "unhealthy" while the app itself was fine.

    Safe because the endpoint returns a constant: there is no Host-dependent
    output to poison. The match is exact, so /api/health/, /api/healthz and POST
    all keep the strict check.
    """

    async def __call__(self, scope, receive, send) -> None:
        if (
            scope["type"] == "http"
            and scope["path"] == "/api/health"
            and scope["method"] in ("GET", "HEAD")
        ):
            await self.app(scope, receive, send)
            return
        await super().__call__(scope, receive, send)
