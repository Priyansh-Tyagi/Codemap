"""
Test isolation: every test session uses a throwaway SQLite file, so running
the suite never creates or touches a real codemap.db.

Security defaults: local-folder analysis is OFF in the product unless
CODEMAP_ALLOW_LOCAL_PATHS=true (see services/security.py). Most of the suite
exercises the analyzer through local fixture folders, so it opts in here,
exactly as a developer running CodeMap on their own machine would; the tests
in test_security.py that care about the default turn it back off explicitly.
The rate limiter is reset per test so one test's requests never count against
another's.

Hermetic by design: importing the app loads the developer's real backend/app/.env
(API keys, tunables), so without isolation the suite's results depend on whose
machine it runs on - and a test that reaches an external service would silently
spend real quota. (This actually happened: a narration test made a real Gemini
call using a developer's key and failed only on machines that had one.) So each
test starts with secrets and tunables removed, and any real outbound HTTP call
that a test forgot to mock raises instead of going out.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))


@pytest.fixture(scope="session", autouse=True)
def _isolated_db(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("codemap-db") / "test.db"
    mp = pytest.MonkeyPatch()
    mp.setenv("CODEMAP_DB_PATH", str(db_path))
    yield db_path
    mp.undo()


# Anything in a developer's .env that could change a test's outcome or reach a
# real service. Tests that need one of these set it themselves, explicitly.
_AMBIENT_ENV = (
    "GEMINI_API_KEY", "GEMINI_MODEL", "GITHUB_TOKEN",
    "CODEMAP_GITHUB_CLIENT_ID", "CODEMAP_GITHUB_CLIENT_SECRET", "CODEMAP_GITHUB_REDIRECT_URI",
    "CODEMAP_LOCAL_PATH_ROOTS", "CODEMAP_ALLOWED_HOSTS", "CODEMAP_DISABLE_DOCS", "CODEMAP_COOKIE_SECURE",
    "CODEMAP_ANALYZE_LIMIT", "CODEMAP_ANALYZE_WINDOW_SECONDS", "CODEMAP_NARRATE_LIMIT",
    "CODEMAP_NARRATE_WINDOW_SECONDS", "CODEMAP_GLOBAL_LIMIT", "CODEMAP_MAX_PROJECTS",
    "CODEMAP_PARSER_MAX_HEAP_MB",
)


def _no_real_network(self, method, url, *args, **kwargs):
    raise AssertionError(
        f"A test tried to make a real HTTP request ({method} {url}). Mock it - the suite must "
        f"never reach external services or spend real API quota."
    )


@pytest.fixture(autouse=True)
def _security_test_defaults(monkeypatch):
    from services import ratelimit

    for name in _AMBIENT_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("CODEMAP_ALLOW_LOCAL_PATHS", "true")
    # Tests mock at the requests.get/post/delete level (which never reaches here),
    # so this only trips on a call that nobody mocked.
    monkeypatch.setattr("requests.sessions.Session.request", _no_real_network)
    ratelimit.reset()
    yield
    ratelimit.reset()
