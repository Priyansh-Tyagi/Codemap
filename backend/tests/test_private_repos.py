"""
Private-repo access control: a private project is visible only to the
session that created it. This is the correctness guarantee that makes
shareable links safe to combine with private-repo analysis at all - without
it, a private repo's dependency graph (file names, import structure, risk
data) would be visible to anyone who gets the /p/:id link, defeating the
point of it being private.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest
from fastapi.testclient import TestClient

from main import app
from services import store

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clean_store():
    store.clear_all()
    yield
    store.clear_all()


@pytest.fixture
def repo(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.js").write_text("export const a = 1;\n")
    return tmp_path


def _sign_in_as(login: str) -> str:
    store.create_session(f"sess-{login}", login, None, f"gho_{login}_token")
    return f"sess-{login}"


def _fake_github_fetch(monkeypatch, repo_path, is_private):
    import api.projects as projects_module
    from analyzer.github_fetcher import FetchedRepo

    class FakeFetchedRepo(FetchedRepo):
        def cleanup(self):
            pass

    monkeypatch.setattr(
        projects_module, "fetch_github_repo",
        lambda url, access_token=None: FakeFetchedRepo(
            local_path=str(repo_path), owner="octocat", repo="secret-project", ref="main",
            is_private=is_private,
        ),
    )


def test_a_public_github_project_is_visible_to_anyone(repo, monkeypatch):
    _fake_github_fetch(monkeypatch, repo, is_private=False)
    pid = client.post("/api/analyze", json={"githubUrl": "https://github.com/octocat/pub"}).json()["projectId"]

    anon = client.get(f"/api/projects/{pid}")
    assert anon.status_code == 200
    assert anon.json()["isPrivate"] is False

    someone_else = client.get(f"/api/projects/{pid}", cookies={"codemap_session": _sign_in_as("mallory")})
    assert someone_else.status_code == 200


def test_a_private_github_project_is_invisible_to_everyone_but_its_owner(repo, monkeypatch):
    owner_session = _sign_in_as("octocat")
    _fake_github_fetch(monkeypatch, repo, is_private=True)

    resp = client.post(
        "/api/analyze", json={"githubUrl": "https://github.com/octocat/secret-project"},
        cookies={"codemap_session": owner_session},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["isPrivate"] is True
    pid = body["projectId"]

    # Anonymous: looks exactly like a nonexistent project (404, not 403 -
    # existence itself isn't revealed).
    anon = client.get(f"/api/projects/{pid}")
    assert anon.status_code == 404

    # A different signed-in user: also 404.
    mallory = _sign_in_as("mallory")
    other = client.get(f"/api/projects/{pid}", cookies={"codemap_session": mallory})
    assert other.status_code == 404

    # The owner, in a fresh request with their own cookie: 200.
    owner = client.get(f"/api/projects/{pid}", cookies={"codemap_session": owner_session})
    assert owner.status_code == 200
    assert owner.json()["isPrivate"] is True


def test_private_project_lockdown_covers_every_read_route_not_just_the_summary(repo, monkeypatch):
    """Guards against someone adding a new /projects/{id}/... route later
    and forgetting to route it through the shared access-control check."""
    owner_session = _sign_in_as("octocat")
    _fake_github_fetch(monkeypatch, repo, is_private=True)
    pid = client.post(
        "/api/analyze", json={"githubUrl": "https://github.com/octocat/secret"},
        cookies={"codemap_session": owner_session},
    ).json()["projectId"]

    mallory = _sign_in_as("mallory")
    for path in (
        f"/api/projects/{pid}",
        f"/api/projects/{pid}/graph",
        f"/api/projects/{pid}/files",
        f"/api/projects/{pid}/cycles",
        f"/api/projects/{pid}/metrics",
        f"/api/projects/{pid}/files/src/a.js",
        f"/api/projects/{pid}/files/src/a.js/impact",
    ):
        assert client.get(path, cookies={"codemap_session": mallory}).status_code == 404, path
        assert client.get(path).status_code == 404, path  # anonymous too

    # Sanity check: the owner CAN reach all the same routes (proves the 404s
    # above are from ownership, not from these routes being broken).
    for path in (
        f"/api/projects/{pid}",
        f"/api/projects/{pid}/graph",
        f"/api/projects/{pid}/files",
        f"/api/projects/{pid}/cycles",
        f"/api/projects/{pid}/metrics",
    ):
        assert client.get(path, cookies={"codemap_session": owner_session}).status_code == 200, path


def test_private_repo_analysis_without_being_signed_in_is_rejected(repo, monkeypatch):
    """Defense in depth: even if fetch_github_repo somehow returned
    is_private=True for an anonymous request, refuse to store it ownerless
    rather than create an unrestricted-but-marked-private project."""
    _fake_github_fetch(monkeypatch, repo, is_private=True)
    resp = client.post("/api/analyze", json={"githubUrl": "https://github.com/octocat/secret"})
    assert resp.status_code == 400
    assert "Sign in" in resp.json()["detail"]


def test_github_cache_is_scoped_per_session_for_signed_in_users(repo, monkeypatch):
    """Two different signed-in users analyzing 'the same' repo+ref must not
    share a cache entry - if one of them actually has a private repo of
    that name and the other doesn't have access, a shared cache would leak
    the first user's analysis to the second."""
    import api.projects as projects_module
    from analyzer.github_fetcher import FetchedRepo

    call_count = [0]

    class FakeFetchedRepo(FetchedRepo):
        def cleanup(self):
            pass

    def fake_fetch(url, access_token=None):
        call_count[0] += 1
        return FakeFetchedRepo(local_path=str(repo), owner="o", repo="r", ref="main", is_private=False)

    monkeypatch.setattr(projects_module, "fetch_github_repo", fake_fetch)

    alice = _sign_in_as("alice")
    bob = _sign_in_as("bob")

    client.post("/api/analyze", json={"githubUrl": "https://github.com/o/r"}, cookies={"codemap_session": alice})
    client.post("/api/analyze", json={"githubUrl": "https://github.com/o/r"}, cookies={"codemap_session": bob})
    assert call_count[0] == 2  # no shared cache hit across sessions

    # But a repeat request from the SAME signed-in user IS cached.
    client.post("/api/analyze", json={"githubUrl": "https://github.com/o/r"}, cookies={"codemap_session": alice})
    assert call_count[0] == 2  # unchanged - alice's second request hit her own cache


def test_github_cache_still_works_for_anonymous_requests(repo, monkeypatch):
    import api.projects as projects_module
    from analyzer.github_fetcher import FetchedRepo

    call_count = [0]

    class FakeFetchedRepo(FetchedRepo):
        def cleanup(self):
            pass

    def fake_fetch(url, access_token=None):
        call_count[0] += 1
        return FakeFetchedRepo(local_path=str(repo), owner="o", repo="r", ref="main", is_private=False)

    monkeypatch.setattr(projects_module, "fetch_github_repo", fake_fetch)
    client.post("/api/analyze", json={"githubUrl": "https://github.com/o/r"})
    client.post("/api/analyze", json={"githubUrl": "https://github.com/o/r"})
    assert call_count[0] == 1  # cached, same as before OAuth existed
