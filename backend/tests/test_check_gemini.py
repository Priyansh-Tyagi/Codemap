import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import check_gemini


class R:
    def __init__(self, status, body=None):
        self.status_code, self.ok, self._b = status, status < 400, body or {}
    def json(self):
        return self._b


def _run(monkeypatch, capsys, listed, gen, key="AQ.KEY123456"):
    monkeypatch.setenv("GEMINI_API_KEY", key)
    monkeypatch.setattr(check_gemini.requests, "get", lambda *a, **k: listed)
    monkeypatch.setattr(check_gemini.requests, "post", lambda *a, **k: gen)
    code = check_gemini.main()
    return code, capsys.readouterr().out


def test_no_key_says_where_to_put_it(monkeypatch, capsys):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert check_gemini.main() == 1
    assert ".env" in capsys.readouterr().out


def test_working_key_reports_success_and_the_reply(monkeypatch, capsys):
    ok = R(200, {"candidates": [{"content": {"parts": [{"text": "ready"}]}}]})
    code, out = _run(monkeypatch, capsys, R(200), ok)
    assert code == 0 and "ready" in out and "work" in out


def test_rejected_key_prints_googles_reason_and_never_the_key(monkeypatch, capsys):
    bad = R(401, {"error": {"message": "invalid credentials for AQ.KEY123456"}})
    code, out = _run(monkeypatch, capsys, bad, bad)
    assert code == 4 and "invalid credentials" in out and "Google rejects the key" in out
    assert "AQ.KEY123456" not in out          # length and first 4 chars only


def test_key_ok_but_model_refused_points_at_the_model(monkeypatch, capsys):
    code, out = _run(monkeypatch, capsys, R(200), R(429, {"error": {"message": "quota"}}))
    assert code == 3 and "GEMINI_MODEL" in out


def test_network_failure_is_reported_not_a_traceback(monkeypatch, capsys):
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaKEY")
    def boom(*a, **k):
        raise check_gemini.requests.ConnectionError("offline")
    monkeypatch.setattr(check_gemini.requests, "get", boom)
    assert check_gemini.main() == 2
    assert "Could not reach Google" in capsys.readouterr().out


def test_402_is_explained_as_billing_not_as_a_bad_key(monkeypatch, capsys):
    msg = {"error": {"message": "Your prepayment credits are depleted."}}
    code, out = _run(monkeypatch, capsys, R(200), R(402, msg))
    assert code == 5
    assert "BILLING" in out and "prepayment credits are depleted" in out
    assert "Google rejects the key" not in out


def test_it_reports_whether_the_model_came_from_env_or_the_default(monkeypatch, capsys):
    monkeypatch.setenv("GEMINI_MODEL", "my-model")
    _, out = _run(monkeypatch, capsys, R(200), R(200, {"candidates": []}))
    assert "my-model" in out and "GEMINI_MODEL in your .env" in out
    monkeypatch.delenv("GEMINI_MODEL")
    _, out = _run(monkeypatch, capsys, R(200), R(200, {"candidates": []}))
    assert "built-in default" in out
