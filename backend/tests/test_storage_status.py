"""
GET /api/status: whether backup storage is usable, shown as a banner.

The entrypoint writes a small JSON file; the app reads it back. These tests pin
the two safety rules: only FIXED WORDS are returned (a provider's error text or a
tampered file must never reach the page), and a missing/broken file degrades to
"unmanaged" instead of an error (a banner problem must never break the app).
"""
import json

import pytest
from fastapi.testclient import TestClient

from main import app
from services import storage_status

client = TestClient(app)


@pytest.fixture
def status_file(tmp_path, monkeypatch):
    path = tmp_path / "storage.json"
    monkeypatch.setenv("CODEMAP_STORAGE_STATUS_FILE", str(path))
    return path


def get_storage():
    r = client.get("/api/status")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    return r.json()["storage"]


def test_unmanaged_when_no_file_is_configured(monkeypatch):
    monkeypatch.delenv("CODEMAP_STORAGE_STATUS_FILE", raising=False)
    assert get_storage() == {"state": "unmanaged"}


def test_unmanaged_when_the_file_does_not_exist(status_file):
    assert get_storage() == {"state": "unmanaged"}


def test_ok(status_file):
    status_file.write_text(json.dumps({"state": "ok", "since": "2026-10-26T10:00:00Z"}))
    assert get_storage() == {"state": "ok", "since": "2026-10-26T10:00:00Z"}


def test_disabled(status_file):
    status_file.write_text(json.dumps({"state": "disabled"}))
    assert get_storage() == {"state": "disabled"}


@pytest.mark.parametrize("reason", ["provider_refused", "timeout", "unreachable", "corrupt"])
def test_degraded_keeps_a_known_reason(status_file, reason):
    status_file.write_text(json.dumps({"state": "degraded", "reason": reason, "since": "2026-10-26T10:00:00Z"}))
    assert get_storage() == {"state": "degraded", "reason": reason, "since": "2026-10-26T10:00:00Z"}


def test_degraded_with_an_unknown_reason_never_echoes_it(status_file):
    hostile = "AccessDenied: <script>alert(1)</script> Transaction cap exceeded"
    status_file.write_text(json.dumps({"state": "degraded", "reason": hostile}))
    storage = get_storage()
    assert storage == {"state": "degraded", "reason": "unknown"}
    assert "script" not in json.dumps(storage)


def test_unknown_state_is_treated_as_unmanaged(status_file):
    status_file.write_text(json.dumps({"state": "on fire", "reason": "x"}))
    assert get_storage() == {"state": "unmanaged"}


def test_extra_fields_are_dropped(status_file):
    status_file.write_text(json.dumps({"state": "ok", "secret": "hunter2", "since": "2026-10-26T10:00:00Z"}))
    assert "secret" not in get_storage()


@pytest.mark.parametrize("since", ["yesterday", "2026-10-26 10:00:00", "<b>x</b>", 12345, None])
def test_malformed_since_is_omitted(status_file, since):
    status_file.write_text(json.dumps({"state": "ok", "since": since}))
    assert get_storage() == {"state": "ok"}


@pytest.mark.parametrize("content", ["", "not json", "[1,2,3]", '"ok"', "null", "{"])
def test_malformed_file_is_unmanaged_not_an_error(status_file, content):
    status_file.write_text(content)
    assert get_storage() == {"state": "unmanaged"}


def test_oversized_file_is_ignored(status_file):
    status_file.write_text(json.dumps({"state": "degraded", "reason": "timeout", "pad": "x" * 5000}))
    assert get_storage() == {"state": "unmanaged"}


def test_valid_json_followed_by_padding_is_still_oversized(status_file):
    # A truncated read of this is VALID JSON, so only the explicit size check rejects it.
    status_file.write_text(json.dumps({"state": "degraded", "reason": "timeout"}) + " " * 5000)
    assert get_storage() == {"state": "unmanaged"}


def test_binary_garbage_is_unmanaged(status_file):
    status_file.write_bytes(b"\xff\xfe\x00\x01")
    assert get_storage() == {"state": "unmanaged"}


def test_a_directory_instead_of_a_file_is_unmanaged(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEMAP_STORAGE_STATUS_FILE", str(tmp_path))
    assert get_storage() == {"state": "unmanaged"}


def test_status_is_not_cached_by_browsers_or_proxies(status_file):
    status_file.write_text(json.dumps({"state": "ok"}))
    assert "no-store" in client.get("/api/status").headers.get("cache-control", "")


def test_status_follows_the_file_without_a_restart(status_file):
    status_file.write_text(json.dumps({"state": "ok"}))
    assert get_storage()["state"] == "ok"
    status_file.write_text(json.dumps({"state": "degraded", "reason": "timeout"}))
    assert get_storage()["state"] == "degraded"


def test_reader_returns_fresh_dicts():
    a = storage_status.read_storage_status()
    a["state"] = "mutated"
    assert storage_status.read_storage_status()["state"] != "mutated"
