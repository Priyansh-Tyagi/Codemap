from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api import projects, files, graph, auth
from services import ratelimit, security, storage_status

# Loads backend/app/.env if it exists (copy .env.example to .env and fill it
# in - see README "GitHub sign-in"). Anchored to this file's own directory,
# not the process's working directory, for the same reason the default
# SQLite path is (see services/store.py) - so it's found the same way
# regardless of which directory you happen to launch uvicorn from.
# override=False: real environment variables you already set always win
# over .env, which is the behavior you want when e.g. a deployment platform
# injects CODEMAP_DB_PATH itself.
load_dotenv(Path(__file__).parent / ".env", override=False)

logger = logging.getLogger("codemap")

_docs = security.docs_enabled()
app = FastAPI(
    title="CodeMap API",
    description="Interactive codebase intelligence & dependency analyzer",
    version="0.1.0",
    # Interactive API docs are handy locally but advertise the whole API
    # surface; CODEMAP_DISABLE_DOCS=true turns them off for a deployment.
    docs_url="/docs" if _docs else None,
    redoc_url="/redoc" if _docs else None,
    openapi_url="/openapi.json" if _docs else None,
)

# Default covers local dev (Vite's default port, both localhost and 127.0.0.1).
# For a real deployment, set CODEMAP_ALLOWED_ORIGINS to a comma-separated list
# of the actual frontend origin(s). A wildcard is refused outright: the
# session cookie is sent cross-origin, so "*" would hand every website the
# signed-in user's identity.
allowed_origins = security.allowed_origins()

_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_MAX_BODY_BYTES = 64 * 1024  # every request body in this API is a few hundred bytes


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    """
    Cross-cutting protections, applied before any route runs:

    1. Request-size cap, so nobody streams a huge body at a JSON endpoint.
    2. CSRF defense for state-changing requests: browsers always attach an
       Origin header to cross-site POSTs, so a POST from an origin that is
       not ours is refused. (Requests with no Origin - curl, tests, server to
       server - cannot be a forged cross-site browser request and pass.)
       This is on top of the SameSite cookie attribute, not instead of it.
    3. A generous global per-client limit against scraping and floods; the
       expensive endpoints have much tighter limits of their own.
    4. Security headers on every response.
    """
    path = request.url.path
    if path.startswith("/api/"):
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > _MAX_BODY_BYTES:
            return _security_headers(JSONResponse(status_code=413, content={"detail": "Request body too large."}), request)

        if request.method in _UNSAFE_METHODS:
            origin = request.headers.get("origin")
            if origin and origin.rstrip("/") not in allowed_origins:
                return _security_headers(
                    JSONResponse(status_code=403, content={"detail": "Cross-origin request refused."}), request
                )

        try:
            ratelimit.check(request, "global", *security.global_rate())
        except HTTPException as exc:
            return _security_headers(
                JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers), request
            )

    return _security_headers(await call_next(request), request)


def _security_headers(response, request: Request):
    h = response.headers
    h["X-Content-Type-Options"] = "nosniff"
    h["X-Frame-Options"] = "DENY"
    h["Referrer-Policy"] = "no-referrer"
    h["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
    if request.url.path.startswith("/api/"):
        # JSON only: nothing here should ever be rendered, framed or cached
        # (responses depend on the session cookie, and private projects are
        # served from the same URLs as public ones).
        h["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        h["Cache-Control"] = "no-store"
    if request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https":
        h["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


# Added AFTER the decorator above so CORS is the outermost layer: its headers
# land on every response, including the 403/413/429 ones produced above.
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    # Only what the frontend actually uses, not "*".
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
    # Required for the session cookie to be sent on cross-origin requests.
    # Safe because allow_origins is always an explicit list (see above).
    allow_credentials=True,
)

_hosts = security.allowed_hosts()
if _hosts:
    # Optional defense against Host-header tricks (e.g. poisoned redirect URLs):
    # set CODEMAP_ALLOWED_HOSTS=api.example.com in a deployment.
    app.add_middleware(security.HostCheckExceptHealth, allowed_hosts=_hosts)

app.include_router(auth.router, prefix="/api")
app.include_router(projects.router, prefix="/api")
app.include_router(files.router, prefix="/api")
app.include_router(graph.router, prefix="/api")


@app.get("/api/health")
def health_check() -> dict:
    return {"status": "ok"}


@app.get("/api/status")
def server_status() -> dict:
    """Is the server up, and is its backup storage usable? Drives the UI banners.

    Answering at all means the server is awake; the frontend uses this one call
    both as its warm-up (a sleeping free host wakes on the first request) and to
    learn whether projects saved now will survive a restart.
    """
    return {"status": "ok", "storage": storage_status.read_storage_status()}


@app.get("/api/config")
def public_config() -> dict:
    """Non-secret capabilities the UI adapts to (e.g. hide the local-folder option)."""
    return {"allowLocalPaths": security.local_paths_allowed()}


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception):
    """
    Any unexpected failure still returns JSON with a `detail`, so the UI can
    say "the server hit an error" instead of guessing the backend is down.
    The full traceback stays in the server log.
    """
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error ({type(exc).__name__}). Check the backend log."},
    )
