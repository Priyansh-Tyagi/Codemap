"""
Regression tests for a crash seen live on Windows: a repo containing a test
fixture with an extremely long filename made tarfile.extractall raise
FileNotFoundError (path over MAX_PATH), which surfaced as a 500 and the UI
claiming the backend was unreachable.

Linux limits a single filename to 255 bytes, which fails the same way
(OSError), so a 300-char name reproduces the failure class here.
"""

import io
import os
import sys
import tarfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from fastapi.testclient import TestClient

from analyzer import github_fetcher
from analyzer.github_fetcher import _safe_extract, _wanted_member
from main import app

LONG = "a" * 300


def _tar(files: dict[str, bytes]) -> tarfile.TarFile:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            t.addfile(info, io.BytesIO(data))
    buf.seek(0)
    return tarfile.open(fileobj=buf, mode="r:gz")


def test_unwritable_non_source_file_no_longer_matters(tmp_path):
    tar = _tar({
        "o-r-abc/src/app.py": b"x = 1\n",
        f"o-r-abc/tests/fixtures/{LONG}.epub": b"binary",
    })
    skipped = _safe_extract(tar, str(tmp_path))
    assert skipped == 0                                  # the epub was never attempted
    assert (tmp_path / "o-r-abc/src/app.py").exists()


def test_unwritable_source_file_is_skipped_and_counted_not_fatal(tmp_path):
    tar = _tar({
        "o-r-abc/src/ok.js": b"export const a = 1;\n",
        f"o-r-abc/src/{LONG}.js": b"export const b = 2;\n",
        "o-r-abc/src/also_ok.py": b"y = 2\n",
    })
    skipped = _safe_extract(tar, str(tmp_path))
    assert skipped == 1
    assert (tmp_path / "o-r-abc/src/ok.js").exists()
    assert (tmp_path / "o-r-abc/src/also_ok.py").exists()


def test_only_scannable_files_are_extracted(tmp_path):
    tar = _tar({
        "o-r-abc/src/a.ts": b"1",
        "o-r-abc/src/b.tsx": b"1",
        "o-r-abc/README.md": b"docs",
        "o-r-abc/logo.png": b"png",
        "o-r-abc/node_modules/dep/index.js": b"1",
        "o-r-abc/.github/scripts/x.py": b"1",
    })
    _safe_extract(tar, str(tmp_path))
    extracted = sorted(
        os.path.relpath(os.path.join(d, f), tmp_path).replace(os.sep, "/")
        for d, _, fs in os.walk(tmp_path) for f in fs
    )
    assert extracted == ["o-r-abc/src/a.ts", "o-r-abc/src/b.tsx"]


def test_wanted_member_rules():
    def m(name, dir_=False):
        info = tarfile.TarInfo(name)
        info.type = tarfile.DIRTYPE if dir_ else tarfile.REGTYPE
        return info
    assert _wanted_member(m("o-r/src/x.py"))
    assert not _wanted_member(m("o-r/src", dir_=True))
    assert not _wanted_member(m("o-r/node_modules/x/y.js"))
    assert not _wanted_member(m("o-r/x.md"))


def test_path_traversal_is_still_rejected(tmp_path):
    tar = _tar({"o-r-abc/../../evil.py": b"boom"})
    try:
        _safe_extract(tar, str(tmp_path))
        raised = False
    except github_fetcher.GitHubFetchError:
        raised = True
    assert raised
    assert not (tmp_path.parent / "evil.py").exists()


def test_unexpected_server_error_returns_json_detail_not_bare_500(monkeypatch):
    def boom(_url, access_token=None):
        raise RuntimeError("kaboom")
    monkeypatch.setattr("api.projects.fetch_github_repo", boom)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post("/api/analyze", json={"githubUrl": "https://github.com/o/r"})
    assert resp.status_code == 500
    assert "RuntimeError" in resp.json()["detail"]
