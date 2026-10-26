"""
Whether the backup storage behind the database is usable, for the UI banner.

The container entrypoint writes a tiny JSON file at startup (and rewrites it on
every start). This module reads it back. Two rules keep that safe:

  * Only FIXED WORDS are ever returned. The file is parsed, then state and reason
    are looked up in allow-lists; anything else becomes "unmanaged"/"unknown".
    A provider's error text, or a tampered file, can never reach the page.
  * Unreadable, oversized, missing or malformed means "unmanaged" (what a laptop
    without the entrypoint reports), never an error: this must not break a page.

States:  ok         replication is running
         degraded   backup storage could not be used; the app runs WITHOUT
                    replication (projects saved now will not survive a restart)
         disabled   replication switched off on purpose
         unmanaged  no entrypoint (local development)
"""
from __future__ import annotations

import json
import os
import re

STATES = frozenset({"ok", "degraded", "disabled", "unmanaged"})
REASONS = frozenset({"provider_refused", "timeout", "unreachable", "corrupt"})
_MAX_BYTES = 2048
_ISO_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

UNMANAGED = {"state": "unmanaged"}


def read_storage_status() -> dict:
    path = os.environ.get("CODEMAP_STORAGE_STATUS_FILE", "")
    if not path:
        return dict(UNMANAGED)
    try:
        with open(path, "rb") as f:
            raw = f.read(_MAX_BYTES + 1)
    except OSError:
        return dict(UNMANAGED)
    if len(raw) > _MAX_BYTES:
        return dict(UNMANAGED)
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return dict(UNMANAGED)
    if not isinstance(data, dict):
        return dict(UNMANAGED)

    state = data.get("state")
    if not isinstance(state, str) or state not in STATES:
        return dict(UNMANAGED)

    result: dict = {"state": state}
    if state == "degraded":
        reason = data.get("reason")
        result["reason"] = reason if isinstance(reason, str) and reason in REASONS else "unknown"
    since = data.get("since")
    if isinstance(since, str) and _ISO_UTC.match(since):
        result["since"] = since
    return result
