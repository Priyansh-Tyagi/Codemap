from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api import projects, files, graph, auth

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
app = FastAPI(
    title="CodeMap API",
    description="Interactive codebase intelligence & dependency analyzer",
    version="0.1.0",
)

# Default covers local dev (Vite's default port, both localhost and 127.0.0.1).
# For a real deployment, set CODEMAP_ALLOWED_ORIGINS to a comma-separated list
# of the actual frontend origin(s), e.g. "https://codemap.example.com".
_default_origins = "http://localhost:5173,http://127.0.0.1:5173"
allowed_origins = os.environ.get("CODEMAP_ALLOWED_ORIGINS", _default_origins).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
    # Required for the session cookie to be sent on cross-origin requests
    # (the frontend dev server and the API are different origins even when
    # both are localhost). allow_origins can't be "*" when this is True -
    # it isn't, it's always an explicit list, so this is safe as-is.
    allow_credentials=True,
)

app.include_router(auth.router, prefix="/api")
app.include_router(projects.router, prefix="/api")
app.include_router(files.router, prefix="/api")
app.include_router(graph.router, prefix="/api")


@app.get("/api/health")
def health_check() -> dict:
    return {"status": "ok"}


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
