"""
The AI-narrated layer on top of the deterministic guided tour (graph/tour.py).

Phase G's roadmap note (carried over from the project handoff) flagged this
as the highest-risk feature specifically because of the GitHub-rate-limit
lesson from earlier phases: a free-tier AI key will hit its own wall during
exactly the traffic burst that matters most (recruiters evaluating in a
cluster). Four mandated constraints, all implemented here or in api/graph.py:
1. The deterministic tour works and ships as a complete feature with ZERO
   AI involvement (graph/tour.py - no dependency on this module at all).
2. This layer is opt-in - never called automatically, only on a button
   the user clicks (POST /tour/narrate, never part of GET /tour).
3. Responses are cached (services/store.py ai_tour_cache table) - the same
   immutable project is never re-narrated twice.
4. Server-side rate limiting (below) and a graceful fallback: any failure
   here must still leave the user with the working deterministic tour,
   never a broken page.

Provider: Google Gemini via the generateContent endpoint (still fully
supported alongside Google's newer Interactions API). The model is
configurable with GEMINI_MODEL because model IDs get retired: this module
originally hardcoded gemini-1.5-flash, which is no longer in Google's
supported list, so the narration button would have failed outright.
Default is gemini-2.5-flash - fast, listed as supported, and has a usable
free tier, matching the "free key" risk this design is defending against.

Privacy note: only STRUCTURAL metadata is ever sent to the AI provider -
file paths, architecture categories, dependency counts, cycle membership.
Never file contents. This matters most for a signed-in user's own private
repo: CodeMap reads their source to build the graph, but what leaves the
server for narration is the shape of the graph, not the code in it.
"""

from __future__ import annotations

import os
import time

import requests

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
REQUEST_TIMEOUT_SECONDS = 20

# Server-wide sliding-window limit, deliberately in-memory (NOT persisted,
# unlike project data) - this is a safety cap on API spend, not user data,
# and resetting it on a restart is the right behavior, not a bug.
RATE_LIMIT_MAX_CALLS = 20
RATE_LIMIT_WINDOW_SECONDS = 60 * 60
_call_timestamps: list[float] = []


class AINarrationError(Exception):
    """Any reason narration isn't available right now. Always caught and
    turned into a graceful fallback - never allowed to surface as a 500."""


def is_configured() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


def _provider_message(resp) -> str:
    """The human-readable reason Google puts in its error body, e.g. 'API key
    not valid' or a quota/billing explanation. Surfacing it is the whole
    point: a bare status code (the first version showed only '(402)') sends
    the user guessing. Truncated, and the API key is redacted defensively -
    it travels in the request URL, so it must never be echoed back to a
    browser even if some error text happened to include it."""
    try:
        message = resp.json().get("error", {}).get("message", "")
    except Exception:
        return ""
    key = os.environ.get("GEMINI_API_KEY", "")
    if key:
        message = message.replace(key, "[redacted]")
    message = " ".join(str(message).split())
    return message[:240]


def _explain_http_error(resp) -> str:
    status = resp.status_code
    detail = _provider_message(resp)
    hint = {
        400: "the request or API key was rejected",
        401: "the API key was not accepted",
        402: "the provider says payment or billing is required for this key/model",
        403: "this API key is not permitted to use that model or API",
        429: "the free-tier quota or rate limit was reached",
    }.get(status, "the provider returned an error")
    text = f"AI provider error {status}: {hint}"
    return f"{text} - \"{detail}\"." if detail else f"{text}."


def _api_url() -> str:
    model = os.environ.get("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL
    return f"{GEMINI_BASE_URL}/{model}:generateContent"


def _check_rate_limit() -> None:
    now = time.time()
    while _call_timestamps and now - _call_timestamps[0] > RATE_LIMIT_WINDOW_SECONDS:
        _call_timestamps.pop(0)
    if len(_call_timestamps) >= RATE_LIMIT_MAX_CALLS:
        raise AINarrationError(
            f"AI narration is temporarily rate-limited ({RATE_LIMIT_MAX_CALLS} requests/hour "
            f"server-wide). Showing the deterministic tour instead."
        )
    _call_timestamps.append(now)


def _build_prompt(project_label: str, stops: list[dict], architecture_summary: dict[str, int]) -> str:
    lines = [
        f"You are narrating a guided code tour for a project called '{project_label}'.",
        "Below is a suggested reading order through its files, computed from its "
        "dependency graph structure (not from reading the actual source code).",
        "For EACH stop, in order, write ONE short sentence (max 25 words) explaining "
        "what a newcomer should understand about its ROLE in the architecture, given "
        "its category and structural position. Do not invent implementation details "
        "you cannot know from file names and categories alone.",
        "",
        f"Architecture breakdown: {architecture_summary}",
        "",
        "Stops:",
    ]
    for i, stop in enumerate(stops, 1):
        members = stop.get("members") or []
        # A grouped stop is one line covering several sibling files; list their
        # paths so the sentence can describe the group's role as a whole.
        subject = f"{stop['filePath']}: " + ", ".join(m["filePath"] for m in members) if members else stop["filePath"]
        lines.append(f"{i}. {subject} (stage: {stop['stage']}; {'; '.join(stop['reasons']) or 'no notable signals'})")
    lines.append("")
    lines.append(
        f"Respond with exactly {len(stops)} lines, one sentence per stop, in the same "
        f"order, no numbering, no extra commentary before or after."
    )
    return "\n".join(lines)


def narrate_tour(project_label: str, stops: list[dict], architecture_summary: dict[str, int]) -> list[str]:
    """
    Returns one narrative sentence per stop, same order as `stops`.
    Raises AINarrationError for anything that should fall back gracefully
    (not configured, rate limited, network/timeout, malformed response).
    """
    if not is_configured():
        raise AINarrationError("AI narration is not configured on this server (GEMINI_API_KEY unset).")
    if not stops:
        return []

    _check_rate_limit()

    prompt = _build_prompt(project_label, stops, architecture_summary)
    try:
        resp = requests.post(
            _api_url(),
            params={"key": os.environ["GEMINI_API_KEY"]},
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as e:
        raise AINarrationError(f"Could not reach the AI provider ({type(e).__name__}).") from e

    if resp.status_code == 404:
        raise AINarrationError(
            f"AI model '{os.environ.get('GEMINI_MODEL') or DEFAULT_GEMINI_MODEL}' was not found - "
            f"it may have been retired. Set GEMINI_MODEL to a current model ID."
        )
    if not resp.ok:
        raise AINarrationError(_explain_http_error(resp))

    try:
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, ValueError) as e:
        raise AINarrationError("AI provider returned an unexpected response shape.") from e

    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if len(lines) != len(stops):
        # Don't guess which sentence belongs to which stop if the count is
        # off - a misaligned narration (sentence N describing stop N+1) is
        # worse than falling back to the deterministic tour.
        raise AINarrationError(
            f"AI provider returned {len(lines)} lines for {len(stops)} stops (expected a 1:1 match)."
        )
    return lines
