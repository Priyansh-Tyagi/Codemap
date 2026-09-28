"""
Test isolation: every test session uses a throwaway SQLite file, so running
the suite never creates or touches a real codemap.db.
"""

import pytest


@pytest.fixture(scope="session", autouse=True)
def _isolated_db(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("codemap-db") / "test.db"
    mp = pytest.MonkeyPatch()
    mp.setenv("CODEMAP_DB_PATH", str(db_path))
    yield db_path
    mp.undo()
