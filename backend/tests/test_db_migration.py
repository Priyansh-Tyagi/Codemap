"""
Regression test for a bug that hit a real, pre-existing codemap.db: columns
added in later phases were missing from databases created by earlier ones,
so every analysis failed with 'table projects has no column named
is_private'. All other tests start from an empty database, which is exactly
why they never caught it - this one starts from an OLD one.
"""

import json
import os
import sqlite3
import subprocess
import sys
import textwrap

APP_DIR = os.path.join(os.path.dirname(__file__), "..", "app")

# The projects table exactly as Phase E first shipped it (no cycle_info_json,
# is_private, or owner_session_id), plus the github_cache table.
PHASE_E_SCHEMA = """
CREATE TABLE projects (
    project_id TEXT PRIMARY KEY, root TEXT NOT NULL, graph_json TEXT NOT NULL,
    cycles_json TEXT NOT NULL, nodes_in_cycles_json TEXT NOT NULL,
    metrics_json TEXT NOT NULL, external_dependencies_json TEXT NOT NULL,
    unresolved_imports_json TEXT NOT NULL, parse_errors_json TEXT NOT NULL,
    architecture_json TEXT NOT NULL, risk_json TEXT NOT NULL,
    source_type TEXT NOT NULL, source_label TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE github_cache (
    cache_key TEXT PRIMARY KEY, project_id TEXT NOT NULL, cached_at REAL NOT NULL
);
"""


def _run(code: str, db_path: str) -> str:
    env = {**os.environ, "CODEMAP_DB_PATH": db_path, "PYTHONPATH": os.path.abspath(APP_DIR)}
    r = subprocess.run([sys.executable, "-c", textwrap.dedent(code)], cwd=APP_DIR,
                       env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def _old_db_with_one_project(tmp_path) -> str:
    db = str(tmp_path / "old.db")
    conn = sqlite3.connect(db)
    conn.executescript(PHASE_E_SCHEMA)
    graph = {"directed": True, "multigraph": False, "graph": {}, "nodes": [{"id": "a.js", "filePath": "a.js"}], "links": []}
    conn.execute(
        "INSERT INTO projects VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("old-project-1", "/r", json.dumps(graph), "[]", "[]",
         json.dumps({"avgDependencies": 0.0}), "{}", "[]", "[]", "{}", "{}",
         "local", "/r", "2026-01-01T00:00:00+00:00"),
    )
    conn.commit()
    conn.close()
    return db


def test_old_database_gains_the_new_columns_without_losing_data(tmp_path):
    db = _old_db_with_one_project(tmp_path)
    out = _run("""
        from services import store
        r = store.get_project('old-project-1')
        print(r.project_id, r.is_private, r.owner_session_id, r.cycles_truncated)
    """, db)
    assert out == "old-project-1 False None False"


def test_creating_a_project_in_an_old_database_works(tmp_path):
    """The exact operation that crashed: an INSERT naming is_private."""
    db = _old_db_with_one_project(tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.js").write_text("export const a = 1;\n")
    out = _run(f"""
        from graph.builder import build_dependency_graph
        from services import store
        r = store.create_project(build_dependency_graph({str(repo)!r}), is_private=True, owner_session_id='s1')
        got = store.get_project(r.project_id)
        old = store.get_project('old-project-1')
        print(got.is_private, got.owner_session_id, old is not None)
    """, db)
    assert out == "True s1 True"


def test_migration_is_idempotent_across_restarts(tmp_path):
    db = _old_db_with_one_project(tmp_path)
    for _ in range(3):  # three separate processes = three "restarts"
        _run("from services import store; store.get_project('old-project-1')", db)
    cols = [r[1] for r in sqlite3.connect(db).execute("PRAGMA table_info(projects)")]
    assert cols.count("is_private") == 1 and cols.count("owner_session_id") == 1


def test_fresh_database_and_migrated_database_end_up_with_identical_columns(tmp_path):
    old = _old_db_with_one_project(tmp_path)
    fresh = str(tmp_path / "fresh.db")
    for db in (old, fresh):
        _run("from services import store; store.get_project('x')", db)
    cols = lambda d: sorted(r[1] for r in sqlite3.connect(d).execute("PRAGMA table_info(projects)"))
    assert cols(old) == cols(fresh)
