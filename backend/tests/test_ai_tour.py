"""
Tests for the AI-narrated tour layer: caching, rate limiting, and -
critically - that every kind of failure degrades to the working
deterministic tour rather than breaking the response.

Real Gemini calls are mocked throughout (no network, no API key needed to
run this suite) - these test our handling of the AI layer, not Gemini
itself.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest
from fastapi.testclient import TestClient

import analyzer.ai_tour as ai_tour_module
import api.graph as graph_module
from main import app
from services import store

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clean_state():
    store.clear_all()
    ai_tour_module._call_timestamps.clear()
    yield
    store.clear_all()
    ai_tour_module._call_timestamps.clear()


@pytest.fixture
def project_id(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n")
    (tmp_path / "src" / "b.py").write_text("from . import a\n")
    resp = client.post("/api/analyze", json={"path": str(tmp_path)})
    return resp.json()["projectId"]


def test_narrate_without_gemini_key_falls_back_to_deterministic_tour(project_id, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    resp = client.post(f"/api/projects/{project_id}/tour/narrate")
    assert resp.status_code == 200
    body = resp.json()
    assert body["narrated"] is False
    assert "not configured" in body["narrationError"]
    assert len(body["stops"]) == 2
    assert all(stop["narrative"] is None for stop in body["stops"])


def test_successful_narration_is_attached_to_each_stop_and_cached(project_id, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(
        graph_module, "narrate_tour",
        lambda label, stops, summary: [f"Narrative for {s['filePath']}" for s in stops],
    )

    resp = client.post(f"/api/projects/{project_id}/tour/narrate")
    body = resp.json()
    assert body["narrated"] is True
    assert all(stop["narrative"] for stop in body["stops"])

    # Cached: a second call must not invoke narrate_tour again.
    monkeypatch.setattr(
        graph_module, "narrate_tour",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not be called - should hit cache")),
    )
    resp2 = client.post(f"/api/projects/{project_id}/tour/narrate")
    assert resp2.json()["narrated"] is True
    assert resp2.json()["stops"] == body["stops"]


def test_ai_provider_failure_degrades_to_deterministic_tour_not_a_500(project_id, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    def boom(label, stops, summary):
        raise ai_tour_module.AINarrationError("Could not reach the AI provider (Timeout).")
    monkeypatch.setattr(graph_module, "narrate_tour", boom)

    resp = client.post(f"/api/projects/{project_id}/tour/narrate")
    assert resp.status_code == 200  # never a 500 - a graceful degrade
    body = resp.json()
    assert body["narrated"] is False
    assert "Could not reach the AI provider" in body["narrationError"]
    assert len(body["stops"]) == 2  # deterministic tour still fully present


def test_malformed_ai_response_is_rejected_rather_than_misaligned(monkeypatch):
    """A line-count mismatch must not silently attach the wrong sentence to
    the wrong file - that's worse than no narration at all."""
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    class FakeResp:
        ok = True
        status_code = 200
        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": "Only one line.\n"}]}}]}

    monkeypatch.setattr(ai_tour_module.requests, "post", lambda *a, **k: FakeResp())
    with pytest.raises(ai_tour_module.AINarrationError, match="expected a 1:1 match"):
        ai_tour_module.narrate_tour("demo", [{"filePath": "a.py", "stage": "x", "reasons": []},
                                              {"filePath": "b.py", "stage": "y", "reasons": []}], {})


def test_rate_limit_blocks_further_calls_within_the_window(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    for _ in range(ai_tour_module.RATE_LIMIT_MAX_CALLS):
        ai_tour_module._check_rate_limit()
    with pytest.raises(ai_tour_module.AINarrationError, match="rate-limited"):
        ai_tour_module._check_rate_limit()


def test_rate_limit_is_scoped_to_the_window_not_permanent(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    now = 1_000_000.0
    monkeypatch.setattr(ai_tour_module.time, "time", lambda: now)
    for _ in range(ai_tour_module.RATE_LIMIT_MAX_CALLS):
        ai_tour_module._check_rate_limit()

    monkeypatch.setattr(ai_tour_module.time, "time", lambda: now + ai_tour_module.RATE_LIMIT_WINDOW_SECONDS + 1)
    ai_tour_module._check_rate_limit()  # should not raise - old timestamps aged out


def test_rate_limit_exhaustion_degrades_gracefully_through_the_api(project_id, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    for _ in range(ai_tour_module.RATE_LIMIT_MAX_CALLS):
        ai_tour_module._call_timestamps.append(__import__("time").time())

    resp = client.post(f"/api/projects/{project_id}/tour/narrate")
    assert resp.status_code == 200
    assert resp.json()["narrated"] is False
    assert "rate-limited" in resp.json()["narrationError"]


def test_empty_project_narrate_returns_empty_stops_without_calling_ai(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    (tmp_path / "README.md").write_text("no source files\n")
    pid = client.post("/api/analyze", json={"path": str(tmp_path)}).json()["projectId"]

    monkeypatch.setattr(
        graph_module, "narrate_tour",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not call the AI for an empty tour")),
    )
    resp = client.post(f"/api/projects/{pid}/tour/narrate")
    body = resp.json()
    assert body["stops"] == [] and body["narrated"] is False and body["narrationError"] is None


def test_prompt_sends_structure_only_never_file_contents():
    """Privacy guard: the AI prompt must describe the tour structurally -
    paths, stages, reasons - and must never embed raw file contents, since
    this is the one place project data leaves the server to a third party."""
    stops = [{"filePath": "src/secret_sauce.py", "stage": "Core logic", "reasons": ["3 other files depend on this"]}]
    prompt = ai_tour_module._build_prompt("demo/project", stops, {"Service": 1})
    assert "src/secret_sauce.py" in prompt
    assert "Core logic" in prompt
    # Nothing resembling source code syntax should appear - this is a schema
    # describing the tour, not a dump of the files in it.
    assert "def " not in prompt and "import " not in prompt.replace("one", "")


def test_model_is_configurable_and_defaults_to_a_current_one(monkeypatch):
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    assert "gemini-2.5-flash:generateContent" in ai_tour_module._api_url()
    assert "1.5" not in ai_tour_module._api_url()  # retired model must never come back as the default
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.6-flash")
    assert "models/gemini-3.6-flash:generateContent" in ai_tour_module._api_url()


def test_retired_model_gives_an_actionable_message_not_a_generic_error(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-1.5-flash")

    class NotFound:
        ok = False
        status_code = 404

    monkeypatch.setattr(ai_tour_module.requests, "post", lambda *a, **k: NotFound())
    with pytest.raises(ai_tour_module.AINarrationError, match="GEMINI_MODEL"):
        ai_tour_module.narrate_tour("demo", [{"filePath": "a.py", "stage": "x", "reasons": []}], {})


def test_request_body_and_url_are_what_the_real_api_expects(monkeypatch):
    """Captures the actual outgoing request - the closest check available
    without a live API key."""
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    captured = {}

    class Ok:
        ok = True
        status_code = 200
        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": "One sentence."}]}}]}

    def fake_post(url, params=None, json=None, timeout=None):
        captured.update(url=url, params=params, json=json, timeout=timeout)
        return Ok()

    monkeypatch.setattr(ai_tour_module.requests, "post", fake_post)
    out = ai_tour_module.narrate_tour("demo", [{"filePath": "a.py", "stage": "Foundation", "reasons": []}], {})
    assert out == ["One sentence."]
    assert captured["url"].endswith("/models/gemini-2.5-flash:generateContent")
    assert captured["params"] == {"key": "fake-key"}
    assert captured["json"]["contents"][0]["parts"][0]["text"]
    assert captured["timeout"] == ai_tour_module.REQUEST_TIMEOUT_SECONDS


@pytest.fixture
def fanout_project(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("from . import hub\n")
    (tmp_path / "src" / "hub.py").write_text("".join(f"from . import leaf{i}\n" for i in range(4)))
    for i in range(4):
        (tmp_path / "src" / f"leaf{i}.py").write_text("x = 1\n")
    (tmp_path / "src" / "lonely.py").write_text("y = 1\n")
    return client.post("/api/analyze", json={"path": str(tmp_path)}).json()["projectId"]


def test_tour_endpoint_modes_members_and_note(fanout_project):
    trace = client.get(f"/api/projects/{fanout_project}/tour").json()
    assert trace["mode"] == "trace"
    assert [s["filePath"] for s in trace["stops"][:2]] == ["src/main.py", "src/hub.py"]
    group = trace["stops"][2]
    assert group["filePath"] == "4 files used by hub.py" and len(group["members"]) == 4
    assert "no import connections" in trace["note"]          # lonely.py is left out, and we say so

    found = client.get(f"/api/projects/{fanout_project}/tour?mode=foundation").json()
    assert found["mode"] == "foundation"
    assert found["stops"][-1]["filePath"] == "src/main.py"   # bottom-up ends at the entry point


def test_invalid_tour_mode_is_rejected(fanout_project):
    assert client.get(f"/api/projects/{fanout_project}/tour?mode=sideways").status_code == 422


def test_narration_cached_for_one_mode_is_never_attached_to_the_other(fanout_project, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    calls = []

    def fake(label, stops, summary):
        calls.append(len(stops))
        return [f"narration {len(calls)}-{i}" for i in range(len(stops))]
    monkeypatch.setattr(graph_module, "narrate_tour", fake)

    a = client.post(f"/api/projects/{fanout_project}/tour/narrate?mode=trace").json()
    b = client.post(f"/api/projects/{fanout_project}/tour/narrate?mode=foundation").json()
    assert len(calls) == 2                                   # each mode narrated separately
    assert a["stops"][0]["narrative"].startswith("narration 1-")
    assert b["stops"][0]["narrative"].startswith("narration 2-")

    a2 = client.post(f"/api/projects/{fanout_project}/tour/narrate?mode=trace").json()
    assert len(calls) == 2                                   # second trace request: cache hit
    assert a2["stops"] == a["stops"]


def test_prompt_lists_the_members_of_a_grouped_stop():
    stops = [{"filePath": "3 files used by Dashboard.jsx", "stage": "Building blocks", "reasons": [],
              "members": [{"filePath": "src/A.jsx"}, {"filePath": "src/B.jsx"}, {"filePath": "src/C.jsx"}]}]
    prompt = ai_tour_module._build_prompt("demo", stops, {})
    assert "src/A.jsx" in prompt and "src/C.jsx" in prompt


class _Resp:
    def __init__(self, status, body=None, ok=None):
        self.status_code = status
        self.ok = (status < 400) if ok is None else ok
        self._body = body
    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


def _narrate_with(monkeypatch, resp):
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-SECRET-KEY")
    monkeypatch.setattr(ai_tour_module.requests, "post", lambda *a, **k: resp)
    return ai_tour_module.narrate_tour("demo", [{"filePath": "a.py", "stage": "x", "reasons": []}], {})


def test_provider_error_message_is_shown_not_just_the_status_code(monkeypatch):
    """The first version showed only 'returned an error (402)', leaving the
    user to guess why. Google's body says why."""
    resp = _Resp(402, {"error": {"message": "Billing is required to use this model."}})
    with pytest.raises(ai_tour_module.AINarrationError) as e:
        _narrate_with(monkeypatch, resp)
    text = str(e.value)
    assert "402" in text and "Billing is required to use this model." in text
    assert "billing is required" in text.lower()


@pytest.mark.parametrize("status,needle", [
    (400, "rejected"), (401, "not accepted"), (403, "not permitted"), (429, "quota"),
])
def test_each_common_status_gets_an_actionable_hint(monkeypatch, status, needle):
    with pytest.raises(ai_tour_module.AINarrationError, match=needle):
        _narrate_with(monkeypatch, _Resp(status, {"error": {"message": "x"}}))


def test_api_key_is_never_echoed_back_even_if_the_provider_message_contains_it(monkeypatch):
    resp = _Resp(400, {"error": {"message": "Bad key AIza-SECRET-KEY supplied"}})
    with pytest.raises(ai_tour_module.AINarrationError) as e:
        _narrate_with(monkeypatch, resp)
    assert "AIza-SECRET-KEY" not in str(e.value)
    assert "[redacted]" in str(e.value)


def test_error_with_no_json_body_still_gives_a_clean_message(monkeypatch):
    with pytest.raises(ai_tour_module.AINarrationError) as e:
        _narrate_with(monkeypatch, _Resp(502, None))
    assert "502" in str(e.value)


def test_overlong_provider_message_is_truncated(monkeypatch):
    resp = _Resp(400, {"error": {"message": "word " * 500}})
    with pytest.raises(ai_tour_module.AINarrationError) as e:
        _narrate_with(monkeypatch, resp)
    assert len(str(e.value)) < 400
