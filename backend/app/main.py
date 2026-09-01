from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import projects, files, graph

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
