"""
Durability / deployment-hardening tests for the SQLite layer.

Why these exist (each maps to a risk in the Docker + Litestream plan):

  * WAL mode      - Litestream replicates by tailing the WAL; without WAL there
                    is no continuous backup at all.
  * Concurrency   - several analyses finishing at once must not surface
                    "database is locked" to users.
  * Permissions   - the DB holds encrypted tokens and private-repo graphs; the
                    -wal / -shm sidecar files must be exactly as private.
  * Parser heap   - on a 512 MB container the Node heap cap has to be
                    configurable or the OS OOM-kills the whole process.
"""

import os
import sqlite3
import stat
import sys
import threading
from contextlib import closing

import pytest

from analyzer import parser_bridge
from graph.builder import build_dependency_graph
from services import store

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
SAMPLE_APP = os.path.join(REPO_ROOT, "examples", "sample-app")


# --------------------------------------------------------------------------- WAL


def test_database_is_in_wal_mode():
    with closing(store._connect()) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"


def test_wal_mode_is_stored_in_the_file_not_just_the_connection():
    """A restored backup must still be WAL: a fresh raw connection sees it."""
    with closing(store._connect()):
        pass
    with closing(sqlite3.connect(store._db_path())) as raw:
        assert raw.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"


def test_synchronous_is_normal_on_every_connection():
    # 1 == NORMAL. (FULL is 2.) Per-connection setting, so check a fresh one
    # AFTER the process-wide init has already happened.
    with closing(store._connect()):
        pass
    with closing(store._connect()) as conn:
        assert conn.execute("PRAGMA synchronous").fetchone()[0] == 1


# ------------------------------------------------------------------ concurrency


def _run_threads(worker, count):
    errors: list[BaseException] = []

    def wrapped(i):
        try:
            worker(i)
        except BaseException as exc:  # noqa: BLE001 - we want every failure
            errors.append(exc)

    threads = [threading.Thread(target=wrapped, args=(i,)) for i in range(count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert not any(t.is_alive() for t in threads), "a writer thread hung"
    return errors


def test_concurrent_session_writes_never_report_database_is_locked():
    store.clear_all()
    writers, per_writer = 8, 20

    def worker(i):
        for n in range(per_writer):
            store.create_session(f"sess-{i}-{n}", f"user{i}", None, "ghp_fake_token")
            # interleave reads, as real traffic does
            store.get_session(f"sess-{i}-{n}")

    errors = _run_threads(worker, writers)
    assert errors == [], f"concurrent writes failed: {errors[:3]}"
    with closing(store._connect()) as conn:
        assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == writers * per_writer
    store.clear_all()


def test_concurrent_project_saves_all_succeed_and_are_all_readable():
    """The real write path (INSERT + prune), many at once."""
    store.clear_all()
    build = build_dependency_graph(SAMPLE_APP)
    ids: list[str] = []
    lock = threading.Lock()

    def worker(_i):
        for _ in range(3):
            record = store.create_project(build, source_type="local", source_label="t")
            with lock:
                ids.append(record.project_id)

    errors = _run_threads(worker, 6)
    assert errors == [], f"concurrent saves failed: {errors[:3]}"
    assert len(ids) == 18 and len(set(ids)) == 18
    assert all(store.get_project(pid) is not None for pid in ids)
    store.clear_all()


def test_prune_ceiling_holds_under_concurrent_saves(monkeypatch):
    store.clear_all()
    monkeypatch.setenv("CODEMAP_MAX_PROJECTS", "5")
    build = build_dependency_graph(SAMPLE_APP)

    def worker(_i):
        for _ in range(4):
            store.create_project(build, source_type="local", source_label="t")

    errors = _run_threads(worker, 5)
    assert errors == [], f"concurrent saves failed: {errors[:3]}"
    with closing(store._connect()) as conn:
        assert conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 5
    store.clear_all()


# ------------------------------------------------------------------ permissions


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes")
def test_db_and_wal_sidecars_are_owner_only(tmp_path, monkeypatch):
    """
    Fresh DB file -> all three files private, even though the process umask is
    the usual permissive 022 in this test. (The container entrypoint also sets
    umask 077; this proves the app does not depend on that.)
    """
    monkeypatch.setenv("CODEMAP_DB_PATH", str(tmp_path / "perm.db"))
    monkeypatch.setattr(store, "_initialized_path", None)
    old_umask = os.umask(0o022)
    try:
        conn = store._connect()  # held open so the -wal / -shm files persist
        store.set_github_cache("k", "p")  # a real write through the real code path
        for suffix in ("", "-wal", "-shm"):
            path = str(tmp_path / "perm.db") + suffix
            assert os.path.exists(path), f"{path} should exist while a connection is open"
            mode = stat.S_IMODE(os.stat(path).st_mode)
            assert mode == 0o600, f"{suffix or 'main'} file is {oct(mode)}, expected 0o600"
        conn.close()
    finally:
        os.umask(old_umask)
        monkeypatch.setattr(store, "_initialized_path", None)


# ------------------------------------------------------------------ parser heap


def test_parser_heap_default_is_unchanged():
    assert parser_bridge.node_max_heap_mb() == 1536


def test_parser_heap_can_be_lowered_for_small_containers(monkeypatch):
    monkeypatch.setenv("CODEMAP_PARSER_MAX_HEAP_MB", "256")
    assert parser_bridge.node_max_heap_mb() == 256


@pytest.mark.parametrize("raw, expected", [
    ("garbage", 1536), ("", 1536), ("-5", 128), ("0", 128), ("16", 128), ("999999", 8192),
])
def test_parser_heap_bad_values_are_clamped_or_defaulted(monkeypatch, raw, expected):
    monkeypatch.setenv("CODEMAP_PARSER_MAX_HEAP_MB", raw)
    assert parser_bridge.node_max_heap_mb() == expected


def test_parser_subprocess_actually_receives_the_configured_cap(monkeypatch):
    monkeypatch.setenv("CODEMAP_PARSER_MAX_HEAP_MB", "300")
    seen = {}

    class FakeProc:
        returncode = 0
        stdout = "[]"
        stderr = ""

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        return FakeProc()

    monkeypatch.setattr(parser_bridge.subprocess, "run", fake_run)
    parser_bridge.parse_files(["/tmp/x.js"])
    assert "--max-old-space-size=300" in seen["cmd"]
