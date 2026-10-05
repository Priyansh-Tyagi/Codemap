from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import projects, files, graph

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
)

app.include_router(projects.router, prefix="/api")
app.include_router(files.router, prefix="/api")
app.include_router(graph.router, prefix="/api")


@app.get("/api/health")
def health_check() -> dict:
    return {"status": "ok"}


from fastapi import Request
from fastapi.responses import JSONResponse


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
