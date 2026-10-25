"""
Is this SQLite file safe to start the app (and the replicator) on?

Used by entrypoint.sh after a restore. Stdlib only, read-only.

Exit codes:  0 = healthy      2 = file missing      3 = unreadable / corrupt
Prints ONE line the entrypoint logs, e.g.:
    integrity=ok journal=wal projects=12 sessions=3

Why this matters: if a damaged database were opened and replicated, Litestream
would faithfully upload the damage on top of the good history.
"""

import sqlite3
import sys


def main(path: str) -> int:
    import os

    if not os.path.exists(path):
        print("integrity=missing")
        return 2
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
        try:
            verdict = conn.execute("PRAGMA integrity_check").fetchone()[0]
            journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
            counts = {}
            for table in ("projects", "sessions"):
                try:
                    counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                except sqlite3.OperationalError:
                    counts[table] = 0  # fresh DB: tables not created yet
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        print(f"integrity=error detail={str(exc)[:120]!r}")
        return 3
    if verdict != "ok":
        print(f"integrity=FAILED detail={verdict[:120]!r}")
        return 3
    print(f"integrity=ok journal={journal} projects={counts['projects']} sessions={counts['sessions']}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: check_db.py <db-path>", file=sys.stderr)
        sys.exit(64)
    sys.exit(main(sys.argv[1]))
