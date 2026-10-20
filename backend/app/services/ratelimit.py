"""
Small in-memory sliding-window rate limiter.

Why it exists: /analyze downloads a repo, spawns a Node subprocess and parses
hundreds of files, and /tour/narrate spends a paid-quota AI key. Both are
reachable anonymously, so without a limit one client can saturate the server,
exhaust the shared GitHub token's quota, or burn the AI budget for everyone.

Deliberately in-memory and per-process, like the AI limiter before it: this
is abuse protection, not user data, and a restart clearing it is fine. The
deployment is already pinned to one process (SQLite), so a shared store like
Redis would add moving parts without adding protection.

Client identity is the socket peer address. Behind a reverse proxy that is
the proxy's address for EVERYONE unless uvicorn is told to trust the proxy's
X-Forwarded-For (`--proxy-headers --forwarded-allow-ips=...`); render.yaml
does this. Trusting that header from an arbitrary client would let it spoof
its way around the limit, so it is never read here directly.
"""

from __future__ import annotations

import math
import threading
import time
from collections import deque

from fastapi import HTTPException, Request

_MAX_TRACKED_KEYS = 20_000  # bounds memory if someone rotates through many addresses

_lock = threading.Lock()
_hits: dict[tuple[str, str], deque[float]] = {}


def client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def reset() -> None:
    """Forget everything (used by tests)."""
    with _lock:
        _hits.clear()


def check(request: Request, bucket: str, limit: int, window_seconds: float) -> None:
    """
    Record one hit for this client in `bucket`; raise 429 (with Retry-After)
    if that makes more than `limit` hits inside the last `window_seconds`.
    A rejected request is not counted, so waiting out the window always works.
    """
    now = time.monotonic()
    key = (bucket, client_key(request))
    with _lock:
        if len(_hits) >= _MAX_TRACKED_KEYS and key not in _hits:
            _evict_stale(now, window_seconds)
        q = _hits.setdefault(key, deque())
        while q and now - q[0] > window_seconds:
            q.popleft()
        if len(q) >= limit:
            retry_after = max(1, math.ceil(window_seconds - (now - q[0])))
            raise HTTPException(
                status_code=429,
                detail=f"Too many requests. Please wait about {retry_after} seconds and try again.",
                headers={"Retry-After": str(retry_after)},
            )
        q.append(now)


def _evict_stale(now: float, window_seconds: float) -> None:
    for k in [k for k, q in _hits.items() if not q or now - q[-1] > window_seconds]:
        del _hits[k]
    if len(_hits) >= _MAX_TRACKED_KEYS:  # still full of live keys: drop the oldest quarter
        for k in sorted(_hits, key=lambda k: _hits[k][-1] if _hits[k] else 0)[: _MAX_TRACKED_KEYS // 4]:
            del _hits[k]
