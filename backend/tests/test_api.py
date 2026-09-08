"""
API-level tests using FastAPI's TestClient (via httpx).

Run against a fixture repo with a genuine cycle, so a single /analyze call
exercises every endpoint meaningfully (cycles, impact, dependencies, etc.
all have real data to return, not just empty lists).

Includes a regression test for a route-ordering bug: {file_path:path} is a
greedy converter, so /{file_path:path}/impact only works if it's declared
before the bare /{file_path:path} route. If someone reorders api/files.py
in the future, this test will catch it.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest
from fastapi.testclient import TestClient

from main import app
from services import store


@pytest.fixture
def client():
    store.clear_all()
    return TestClient(app)


@pytest.fixture
def cyclic_repo(tmp_path):
    """auth.js -> user.js -> database.js -> auth.js"""
    src = tmp_path / "src"
    src.mkdir()
    (src / "auth.js").write_text(
        "import { getUser } from './user';\nexport function login() { return getUser(); }\n"
    )
    (src / "user.js").write_text(
        "import { query } from './database';\nexport function getUser() { return query(); }\n"
    )
    (src / "database.js").write_text(
        "import { login } from './auth';\nexport function query() { return login(); }\n"
    )
    return tmp_path


@pytest.fixture
def analyzed_project_id(client, cyclic_repo):
    response = client.post("/api/analyze", json={"path": str(cyclic_repo)})
    assert response.status_code == 200
    return response.json()["projectId"]


def test_health_check(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_analyze_returns_correct_summary(client, cyclic_repo):
    response = client.post("/api/analyze", json={"path": str(cyclic_repo)})
    assert response.status_code == 200
    body = response.json()
    assert body["fileCount"] == 3
    assert body["edgeCount"] == 3
    assert body["cycleCount"] == 1
    assert "projectId" in body


def test_analyze_nonexistent_path_returns_400(client):
    response = client.post("/api/analyze", json={"path": "/definitely/not/a/real/path"})
    assert response.status_code == 400


def test_analyze_with_neither_path_nor_github_url_returns_422(client):
    response = client.post("/api/analyze", json={})
    assert response.status_code == 422


def test_analyze_with_both_path_and_github_url_returns_422(client, cyclic_repo):
    response = client.post(
        "/api/analyze",
        json={"path": str(cyclic_repo), "githubUrl": "https://github.com/owner/repo"},
    )
    assert response.status_code == 422


def test_analyze_with_invalid_github_url_returns_400(client):
    response = client.post("/api/analyze", json={"githubUrl": "not-a-github-url"})
    assert response.status_code == 400


def test_analyze_via_github_url_wires_through_correctly(client, cyclic_repo, monkeypatch):
    """
    Mocks fetch_github_repo itself (rather than the HTTP layer underneath
    it, which is already covered in test_github_fetcher.py) to verify the
    /analyze endpoint correctly: calls the fetcher, builds the graph from
    the returned local_path, records sourceType/sourceLabel, and cleans up
    afterward - without making any real network call.
    """
    import api.projects as projects_module
    from analyzer.github_fetcher import FetchedRepo

    cleanup_called = []

    class FakeFetchedRepo(FetchedRepo):
        def cleanup(self):
            cleanup_called.append(True)

    fake_repo = FakeFetchedRepo(
        local_path=str(cyclic_repo), owner="someone", repo="their-app", ref="main"
    )

    monkeypatch.setattr(
        projects_module, "fetch_github_repo", lambda url: fake_repo
    )

    response = client.post(
        "/api/analyze", json={"githubUrl": "https://github.com/someone/their-app"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["sourceType"] == "github"
    assert body["sourceLabel"] == "someone/their-app@main"
    assert body["fileCount"] == 3
    assert cleanup_called == [True]  # cleanup ran even though analysis succeeded


def test_repeat_github_analyze_is_served_from_cache(client, cyclic_repo, monkeypatch):
    """
    Second identical request must NOT call fetch_github_repo again - the
    whole point of caching is skipping the network download + re-parse.
    """
    import api.projects as projects_module
    from analyzer.github_fetcher import FetchedRepo

    fetch_call_count = [0]

    class FakeFetchedRepo(FetchedRepo):
        def cleanup(self):
            pass

    def fake_fetch(url):
        fetch_call_count[0] += 1
        return FakeFetchedRepo(local_path=str(cyclic_repo), owner="someone", repo="app", ref="main")

    monkeypatch.setattr(projects_module, "fetch_github_repo", fake_fetch)

    first = client.post("/api/analyze", json={"githubUrl": "https://github.com/someone/app"})
    second = client.post("/api/analyze", json={"githubUrl": "https://github.com/someone/app"})

    assert first.status_code == 200 and second.status_code == 200
    assert fetch_call_count[0] == 1  # only the FIRST request actually fetched

    assert first.json()["cached"] is False
    assert second.json()["cached"] is True
    # same underlying project, not a fresh analysis
    assert first.json()["projectId"] == second.json()["projectId"]


def test_force_refresh_bypasses_the_cache(client, cyclic_repo, monkeypatch):
    import api.projects as projects_module
    from analyzer.github_fetcher import FetchedRepo

    fetch_call_count = [0]

    class FakeFetchedRepo(FetchedRepo):
        def cleanup(self):
            pass

    def fake_fetch(url):
        fetch_call_count[0] += 1
        return FakeFetchedRepo(local_path=str(cyclic_repo), owner="someone", repo="app", ref="main")

    monkeypatch.setattr(projects_module, "fetch_github_repo", fake_fetch)

    client.post("/api/analyze", json={"githubUrl": "https://github.com/someone/app"})
    forced = client.post(
        "/api/analyze",
        json={"githubUrl": "https://github.com/someone/app", "forceRefresh": True},
    )

    assert forced.status_code == 200
    assert forced.json()["cached"] is False
    assert fetch_call_count[0] == 2  # forceRefresh actually re-fetched


def test_local_path_analysis_is_never_cached(client, cyclic_repo, monkeypatch):
    """
    Local paths must always re-scan, even for the identical path twice in a
    row - caching local results risks silently showing stale data if the
    user edited their own files between requests.
    """
    import analyzer.scanner as scanner_module

    scan_call_count = [0]
    original_scan = scanner_module.scan_repository

    def counting_scan(*args, **kwargs):
        scan_call_count[0] += 1
        return original_scan(*args, **kwargs)

    monkeypatch.setattr(scanner_module, "scan_repository", counting_scan)
    # builder.py imported scan_repository directly, so patch it there too
    import graph.builder as builder_module
    monkeypatch.setattr(builder_module, "scan_repository", counting_scan)

    client.post("/api/analyze", json={"path": str(cyclic_repo)})
    client.post("/api/analyze", json={"path": str(cyclic_repo)})

    assert scan_call_count[0] == 2  # both requests actually scanned, no caching


def test_different_refs_get_separate_cache_entries(client, cyclic_repo, monkeypatch):
    import api.projects as projects_module
    from analyzer.github_fetcher import FetchedRepo

    fetch_call_count = [0]

    class FakeFetchedRepo(FetchedRepo):
        def cleanup(self):
            pass

    def fake_fetch(url):
        fetch_call_count[0] += 1
        ref = "develop" if "develop" in url else "main"
        return FakeFetchedRepo(local_path=str(cyclic_repo), owner="someone", repo="app", ref=ref)

    monkeypatch.setattr(projects_module, "fetch_github_repo", fake_fetch)

    client.post("/api/analyze", json={"githubUrl": "https://github.com/someone/app"})
    client.post("/api/analyze", json={"githubUrl": "https://github.com/someone/app/tree/develop"})

    assert fetch_call_count[0] == 2  # different refs are genuinely different sources


def test_cache_expires_after_ttl(client, cyclic_repo, monkeypatch):
    import api.projects as projects_module
    import services.store as store_module
    from analyzer.github_fetcher import FetchedRepo

    fetch_call_count = [0]

    class FakeFetchedRepo(FetchedRepo):
        def cleanup(self):
            pass

    def fake_fetch(url):
        fetch_call_count[0] += 1
        return FakeFetchedRepo(local_path=str(cyclic_repo), owner="someone", repo="app", ref="main")

    monkeypatch.setattr(projects_module, "fetch_github_repo", fake_fetch)

    client.post("/api/analyze", json={"githubUrl": "https://github.com/someone/app"})
    assert fetch_call_count[0] == 1

    # simulate time passing beyond the TTL by back-dating the cache entry directly
    for key, (project_id, _cached_at) in list(store_module._github_cache.items()):
        store_module._github_cache[key] = (project_id, 0)  # epoch 0 = long expired

    client.post("/api/analyze", json={"githubUrl": "https://github.com/someone/app"})
    assert fetch_call_count[0] == 2  # expired entry triggered a real re-fetch


def test_unknown_project_id_returns_404(client):
    response = client.get("/api/projects/not-a-real-id")
    assert response.status_code == 404


def test_project_graph_has_expected_nodes_and_edges(client, analyzed_project_id):
    response = client.get(f"/api/projects/{analyzed_project_id}/graph")
    assert response.status_code == 200
    body = response.json()
    node_names = {n["name"] for n in body["nodes"]}
    assert node_names == {"auth.js", "user.js", "database.js"}
    assert len(body["edges"]) == 3
    # every node should be flagged as in-cycle, since all 3 form one cycle
    assert all(n["inCycle"] for n in body["nodes"])


def test_project_cycles_endpoint(client, analyzed_project_id):
    response = client.get(f"/api/projects/{analyzed_project_id}/cycles")
    assert response.status_code == 200
    cycles = response.json()
    assert len(cycles) == 1
    assert cycles[0]["chain"][0] == cycles[0]["chain"][-1]


def test_project_metrics_endpoint(client, analyzed_project_id):
    response = client.get(f"/api/projects/{analyzed_project_id}/metrics")
    assert response.status_code == 200
    body = response.json()
    assert body["fileCount"] == 3
    assert body["connectedComponentCount"] == 1


def test_file_detail_endpoint(client, analyzed_project_id):
    response = client.get(f"/api/projects/{analyzed_project_id}/files/src/auth.js")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "auth.js"
    assert body["inCycle"] is True


def test_unknown_file_returns_404(client, analyzed_project_id):
    response = client.get(f"/api/projects/{analyzed_project_id}/files/src/nope.js")
    assert response.status_code == 404


def test_file_dependencies_and_dependents(client, analyzed_project_id):
    deps = client.get(f"/api/projects/{analyzed_project_id}/files/src/auth.js/dependencies")
    assert deps.status_code == 200
    assert deps.json() == ["src/user.js"]

    dependents = client.get(f"/api/projects/{analyzed_project_id}/files/src/auth.js/dependents")
    assert dependents.status_code == 200
    assert dependents.json() == ["src/database.js"]


def test_file_impact_endpoint_reachable_despite_greedy_path_route(client, analyzed_project_id):
    """
    Regression test: /{file_path:path}/impact must not be shadowed by the
    bare /{file_path:path} route. This is the exact bug caught during
    manual Day 4 testing (see api/files.py route-ordering comment).
    """
    response = client.get(f"/api/projects/{analyzed_project_id}/files/src/database.js/impact")
    assert response.status_code == 200
    body = response.json()
    assert body["directDependents"] == ["src/user.js"]
    assert body["indirectDependents"] == ["src/auth.js"]
    assert body["estimatedAffected"] == 2


def test_impact_on_unknown_file_returns_404(client, analyzed_project_id):
    response = client.get(f"/api/projects/{analyzed_project_id}/files/src/nope.js/impact")
    assert response.status_code == 404
