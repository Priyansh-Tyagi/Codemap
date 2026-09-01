"""
Tests for analyzer/github_fetcher.py.

All network calls are mocked - deliberately, not just for speed. While
building this feature, a real request against GitHub's API hit the
unauthenticated rate limit (60/hour) from this sandbox's shared IP. That's
a real condition the code needs to handle gracefully (see the dedicated
rate-limit test below), but it means tests can't depend on a live GitHub
call succeeding, or they'd be flaky through no fault of the code.
"""

import io
import os
import sys
import tarfile
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest
from analyzer.github_fetcher import (
    fetch_github_repo,
    parse_github_url,
    GitHubFetchError,
)


# --- parse_github_url -------------------------------------------------

def test_parses_plain_url():
    assert parse_github_url("https://github.com/owner/repo") == ("owner", "repo", None)


def test_parses_url_with_git_suffix():
    assert parse_github_url("https://github.com/owner/repo.git") == ("owner", "repo", None)


def test_parses_url_with_branch():
    assert parse_github_url("https://github.com/owner/repo/tree/main") == (
        "owner",
        "repo",
        "main",
    )


def test_parses_url_with_trailing_slash():
    assert parse_github_url("https://github.com/owner/repo/") == ("owner", "repo", None)


def test_non_github_url_raises():
    with pytest.raises(GitHubFetchError):
        parse_github_url("https://gitlab.com/owner/repo")


def test_garbage_input_raises():
    with pytest.raises(GitHubFetchError):
        parse_github_url("not a url at all")


# --- fetch_github_repo (mocked) ----------------------------------------

def _make_fake_tarball_bytes(top_dir="owner-repo-abc123"):
    """Builds an in-memory .tar.gz matching GitHub's tarball structure."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        content = b"import x from './y';\n"
        info = tarfile.TarInfo(name=f"{top_dir}/src/app.js")
        info.size = len(content)
        tar.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


def _make_fake_response(status_code=200, json_data=None, content_bytes=b"", ok=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.ok = ok if ok is not None else (200 <= status_code < 300)
    resp.headers = {}
    if json_data is not None:
        resp.json.return_value = json_data
    if content_bytes:
        resp.iter_content.return_value = [content_bytes]
    return resp


def test_successful_fetch_extracts_repo(tmp_path):
    metadata_resp = _make_fake_response(200, json_data={"size": 10, "default_branch": "main"})
    tarball_resp = _make_fake_response(200, content_bytes=_make_fake_tarball_bytes())

    with patch("analyzer.github_fetcher.requests.get", side_effect=[metadata_resp, tarball_resp]):
        fetched = fetch_github_repo("https://github.com/owner/repo")

    try:
        assert fetched.owner == "owner"
        assert fetched.repo == "repo"
        assert fetched.ref == "main"
        assert os.path.isdir(fetched.local_path)
        assert os.path.isfile(os.path.join(fetched.local_path, "src", "app.js"))
    finally:
        fetched.cleanup()
        assert not os.path.exists(fetched.local_path)


def test_cleanup_removes_the_whole_temp_dir(tmp_path):
    metadata_resp = _make_fake_response(200, json_data={"size": 10, "default_branch": "main"})
    tarball_resp = _make_fake_response(200, content_bytes=_make_fake_tarball_bytes())

    with patch("analyzer.github_fetcher.requests.get", side_effect=[metadata_resp, tarball_resp]):
        fetched = fetch_github_repo("https://github.com/owner/repo")

    parent_dir = os.path.dirname(fetched.local_path)
    fetched.cleanup()
    assert not os.path.exists(parent_dir)


def test_repo_not_found_raises():
    metadata_resp = _make_fake_response(404)
    with patch("analyzer.github_fetcher.requests.get", return_value=metadata_resp):
        with pytest.raises(GitHubFetchError, match="not found"):
            fetch_github_repo("https://github.com/owner/does-not-exist")


def test_rate_limit_produces_clear_message():
    """The exact condition hit live while building this feature."""
    resp = _make_fake_response(403)
    resp.headers = {"x-ratelimit-remaining": "0"}
    with patch("analyzer.github_fetcher.requests.get", return_value=resp):
        with pytest.raises(GitHubFetchError, match="rate limit"):
            fetch_github_repo("https://github.com/owner/repo")


def test_repo_too_large_raises_before_downloading():
    metadata_resp = _make_fake_response(200, json_data={"size": 999_999_999, "default_branch": "main"})
    with patch("analyzer.github_fetcher.requests.get", return_value=metadata_resp) as mock_get:
        with pytest.raises(GitHubFetchError, match="too large"):
            fetch_github_repo("https://github.com/owner/huge-repo")
        # only the metadata call should have happened - never attempted the download
        assert mock_get.call_count == 1


def test_ref_not_found_raises():
    metadata_resp = _make_fake_response(200, json_data={"size": 10, "default_branch": "main"})
    tarball_404 = _make_fake_response(404)
    with patch("analyzer.github_fetcher.requests.get", side_effect=[metadata_resp, tarball_404]):
        with pytest.raises(GitHubFetchError, match="not found"):
            fetch_github_repo("https://github.com/owner/repo/tree/no-such-branch")


def test_explicit_ref_in_url_is_used_over_default_branch():
    metadata_resp = _make_fake_response(200, json_data={"size": 10, "default_branch": "main"})
    tarball_resp = _make_fake_response(200, content_bytes=_make_fake_tarball_bytes())

    with patch("analyzer.github_fetcher.requests.get", side_effect=[metadata_resp, tarball_resp]) as mock_get:
        fetched = fetch_github_repo("https://github.com/owner/repo/tree/feature-branch")

    try:
        assert fetched.ref == "feature-branch"
        # the tarball request should have been made against the explicit ref, not "main"
        tarball_call_url = mock_get.call_args_list[1].args[0]
        assert "feature-branch" in tarball_call_url
    finally:
        fetched.cleanup()


def test_unsafe_tarball_path_is_rejected(tmp_path):
    """A tarball with a '../' entry must not extract outside the temp dir (tar slip)."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        content = b"malicious"
        info = tarfile.TarInfo(name="../../evil.txt")
        info.size = len(content)
        tar.addfile(info, io.BytesIO(content))

    metadata_resp = _make_fake_response(200, json_data={"size": 10, "default_branch": "main"})
    tarball_resp = _make_fake_response(200, content_bytes=buffer.getvalue())

    with patch("analyzer.github_fetcher.requests.get", side_effect=[metadata_resp, tarball_resp]):
        with pytest.raises(GitHubFetchError, match="unsafe path"):
            fetch_github_repo("https://github.com/owner/repo")
