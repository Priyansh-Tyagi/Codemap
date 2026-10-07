"""
Symmetric encryption for GitHub access tokens at rest.

Session rows in SQLite hold a real GitHub OAuth token (scoped to whatever
the user granted - potentially 'repo', i.e. read/write on their repos).
Storing that in plaintext in a file that's already on disk for persistence
reasons is a worse habit than it needs to be for one extra module.

Key source: CODEMAP_SECRET_KEY (a Fernet key - 32 url-safe base64 bytes).
Generate one with:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

If unset, a key is generated in memory for this process only, and a loud
warning is logged. This is a deliberate, visible version of the same class
of problem the DB-path default used to cause silently: every session
becomes unreadable (not corrupted - just undecryptable) the next time the
process starts, so every signed-in user is logged out on every restart.
Fine for local development; set CODEMAP_SECRET_KEY for anything that
needs sessions to survive a restart.
"""

from __future__ import annotations

import logging
import os

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is not None:
        return _fernet

    key = os.environ.get("CODEMAP_SECRET_KEY")
    if not key:
        key = Fernet.generate_key().decode()
        logger.warning(
            "CODEMAP_SECRET_KEY is not set - generated a temporary key for this "
            "process only. All signed-in sessions will be invalidated on the next "
            "restart. Set CODEMAP_SECRET_KEY to a stable value to avoid this."
        )
    _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    return _fernet


def encrypt_token(plaintext: str) -> str:
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str) -> str | None:
    """None if the ciphertext can't be decrypted (wrong/rotated key) rather
    than raising - a session row that can no longer be read is equivalent to
    a session that doesn't exist, not a server error."""
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        return None
