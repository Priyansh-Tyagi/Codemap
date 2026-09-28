"""
Persistence tests: prove data survives a "restart" by using REAL separate
Python processes that share nothing but the on-disk SQLite file.
"""

import os
import subprocess
import sys
import textwrap

APP_DIR = os.path.join(os.path.dirname(__file__), "..", "app")


def _run(code: str, db_path: str) -> str:
    env = {**os.environ, "CODEMAP_DB_PATH": db_path}
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        cwd=APP_DIR, env=env, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _make_repo(tmp_path):
    src = tmp_path / "repo" / "src"
    src.mkdir(parents=True)
    (src / "a.js").write_text("import { b } from './b';\nexport const a = b;\n")
    (src / "b.js").write_text("import { a } from './a';\nexport const b = 1;\n")
    return str(tmp_path / "repo")


def test_project_survives_process_restart(tmp_path):
    db = str(tmp_path / "p.db")
    repo = _make_repo(tmp_path)
    project_id = _run(f"""
        from graph.builder import build_dependency_graph
        from services import store
        r = store.create_project(build_dependency_graph({repo!r}))
        print(r.project_id)
    """, db)
    out = _run(f"""
        from services import store
        r = store.get_project({project_id!r})
        print(r.graph.number_of_nodes(), r.graph.number_of_edges(), len(r.cycles))
    """, db)
    assert out == "2 2 1"


def test_unknown_id_returns_none_in_fresh_process(tmp_path):
    db = str(tmp_path / "p.db")
    out = _run("""
        from services import store
        print(store.get_project('nope'))
    """, db)
    assert out == "None"


def test_github_cache_survives_restart(tmp_path):
    db = str(tmp_path / "p.db")
    repo = _make_repo(tmp_path)
    project_id = _run(f"""
        from graph.builder import build_dependency_graph
        from services import store
        r = store.create_project(build_dependency_graph({repo!r}))
        store.set_github_cache('o/r@main', r.project_id)
        print(r.project_id)
    """, db)
    out = _run("""
        from services import store
        print(store.get_cached_github_project_id('o/r@main'))
    """, db)
    assert out == project_id


def test_importing_store_does_not_create_db_file(tmp_path):
    db = tmp_path / "should_not_exist.db"
    _run("from services import store; import main", str(db))
    assert not db.exists()
