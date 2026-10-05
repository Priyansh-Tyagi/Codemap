"""
Regression test: the default DB path must be anchored to backend/app/, not
to the process's working directory. A CWD-relative default meant starting
uvicorn from a different directory between sessions (new terminal, IDE run
config) silently created a second, empty database - indistinguishable from
"persistence doesn't work" to the user.
"""

import os
import subprocess
import sys
import textwrap

APP_DIR = os.path.join(os.path.dirname(__file__), "..", "app")


def test_default_db_path_is_the_same_regardless_of_launch_directory(tmp_path):
    code = """
        from services.store import DEFAULT_DB_PATH
        print(DEFAULT_DB_PATH)
    """
    paths = set()
    for cwd in (APP_DIR, tmp_path, os.path.dirname(APP_DIR)):
        env = {k: v for k, v in os.environ.items() if k != "CODEMAP_DB_PATH"}
        env["PYTHONPATH"] = os.path.abspath(APP_DIR)
        result = subprocess.run(
            [sys.executable, "-c", textwrap.dedent(code)],
            cwd=str(cwd), env=env, capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, result.stderr
        paths.add(result.stdout.strip())
    assert len(paths) == 1, f"default DB path varied by launch directory: {paths}"


def test_default_db_path_lives_in_backend_app():
    from services.store import DEFAULT_DB_PATH
    assert os.path.basename(os.path.dirname(DEFAULT_DB_PATH)) == "app"
    assert os.path.basename(DEFAULT_DB_PATH) == "codemap.db"


def test_explicit_codemap_db_path_still_overrides_the_default(tmp_path, monkeypatch):
    custom = tmp_path / "custom.db"
    monkeypatch.setenv("CODEMAP_DB_PATH", str(custom))
    import importlib
    from services import store
    importlib.reload(store)
    assert store._db_path() == str(custom)
    importlib.reload(store)  # restore for any later test in this process
