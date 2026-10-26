"""
Regression: a deployed service that sets CODEMAP_ALLOWED_HOSTS answered its own
platform's health checks with 400, so the deploy was judged unhealthy and looped.

Render's checker calls /api/health with the service's PRIVATE address as the Host,
not the public hostname. Starlette's TrustedHostMiddleware rejects every path with
no exceptions, so the check failed even though the app was perfectly healthy.

Fix: exempt exactly GET/HEAD /api/health (it returns a constant, so there is no
Host-dependent output to poison); every other path keeps the strict check.
"""
import importlib

import pytest
from fastapi.testclient import TestClient

PUBLIC = "api.example.com"
PRIVATE = "10.238.24.204:10000"      # what a platform health checker may send as Host


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("CODEMAP_ALLOWED_HOSTS", PUBLIC)
    import main
    importlib.reload(main)           # the host list is read once, at import time
    yield TestClient(main.app)
    monkeypatch.delenv("CODEMAP_ALLOWED_HOSTS")
    importlib.reload(main)           # leave the module as other tests expect it


def test_health_check_with_a_private_host_is_healthy(client):
    assert client.get("/api/health", headers={"Host": PRIVATE}).status_code == 200


def test_health_check_with_the_public_host_still_works(client):
    assert client.get("/api/health", headers={"Host": PUBLIC}).status_code == 200


@pytest.mark.parametrize("path", ["/api/config", "/api/projects", "/", "/api/health/", "/api/healthz"])
def test_every_other_path_still_rejects_unknown_hosts(client, path):
    assert client.get(path, headers={"Host": PRIVATE}).status_code == 400


def test_post_to_health_does_not_get_the_exemption(client):
    assert client.post("/api/health", headers={"Host": PRIVATE}).status_code == 400


def test_other_paths_work_with_the_public_host(client):
    assert client.get("/api/config", headers={"Host": PUBLIC}).status_code == 200
