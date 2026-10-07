"""
GitHub repository fetcher.

Downloads a GitHub repo as a tarball snapshot - ONE HTTP request, no git
history, no `git` binary required - and extracts it to a self-cleaning temp
directory so it can run through the exact same scanner/parser/resolver
pipeline used for local paths. Deliberately not a `git clone`: we only need
the files as they exist at a ref, not the commit history.

Why a tarball and not the GitHub Contents API: the Contents API needs one
request per file, which is slow and hits unauthenticated rate limits (60/hr)
almost immediately on any repo bigger than a handful of files. The tarball
endpoint returns the whole snapshot in one request.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import tarfile
import tempfile
from dataclasses import dataclass

import requests

from analyzer.scanner import DEFAULT_IGNORE_DIRS, SUPPORTED_EXTENSIONS

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
MAX_REPO_SIZE_KB = 200_000  # ~200MB - generous for MVP-sized repos, rejects huge monorepos
REQUEST_TIMEOUT_SECONDS = 30

_GITHUB_URL_RE = re.compile(
    r"^https?://github\.com/(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+?)(?:\.git)?"
    r"(?:/tree/(?P<ref>[\w./-]+))?/?$"
)


class GitHubFetchError(Exception):
    """Raised for any problem resolving, downloading, or extracting a GitHub repo.
    Callers (the API layer) are expected to turn this into a 400 response -
    these are all "the request can't be fulfilled" cases, not server bugs.
    """


@dataclass
class FetchedRepo:
    local_path: str  # extracted repo root, ready to hand to the scanner
    owner: str
    repo: str
    ref: str
    is_private: bool = False

    def cleanup(self) -> None:
        """local_path is nested one level inside its own temp dir; remove the whole thing."""
        parent = os.path.dirname(self.local_path)
        shutil.rmtree(parent, ignore_errors=True)


def parse_github_url(url: str) -> tuple[str, str, str | None]:
    """
    Returns (owner, repo, ref_or_none). Accepts:
      https://github.com/owner/repo
      https://github.com/owner/repo.git
      https://github.com/owner/repo/tree/branch-name
    Raises GitHubFetchError if the URL doesn't look like a GitHub repo URL.
    """
    match = _GITHUB_URL_RE.match(url.strip())
    if not match:
        raise GitHubFetchError(f"Doesn't look like a GitHub repository URL: {url}")
    return match.group("owner"), match.group("repo"), match.group("ref")


def _github_headers(access_token: str | None = None) -> dict:
    """
    Unauthenticated GitHub API requests are capped at 60/hour PER IP - easy
    to exhaust, especially from a shared or cloud IP (confirmed by hitting
    this exact limit while building this feature).

    Three ways to raise that, checked in order: (1) a signed-in user's own
    OAuth token (access_token param - each user then has their own 5,000/hr
    limit, AND can access their own private repos, which is the actual
    point of Phase F), (2) a server-wide GITHUB_TOKEN env var (raises the
    server's shared limit for anonymous use, unchanged from before OAuth
    existed), (3) unauthenticated.
    """
    token = access_token or os.environ.get("GITHUB_TOKEN")
    return {"Authorization": f"Bearer {token}"} if token else {}


def _get_repo_metadata(owner: str, repo: str, access_token: str | None = None) -> dict:
    resp = requests.get(
        f"{GITHUB_API}/repos/{owner}/{repo}",
        headers=_github_headers(access_token),
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    if resp.status_code == 404:
        if access_token:
            raise GitHubFetchError(
                f"Repository not found: {owner}/{repo} (or your signed-in GitHub "
                f"account doesn't have access to it)"
            )
        raise GitHubFetchError(
            f"Repository not found (or private - sign in with GitHub to analyze "
            f"your own private repos): {owner}/{repo}"
        )
    if resp.status_code == 403 and resp.headers.get("x-ratelimit-remaining") == "0":
        raise GitHubFetchError(
            "GitHub API rate limit reached"
            + (" for this account" if access_token else " for unauthenticated requests (60/hour per IP)")
            + ". Try again later"
            + ("." if access_token else ", sign in with GitHub, or set a GITHUB_TOKEN "
                                          "environment variable to raise the limit to 5,000/hour.")
        )
    if not resp.ok:
        raise GitHubFetchError(f"GitHub API error ({resp.status_code}) looking up {owner}/{repo}")
    return resp.json()


def _wanted_member(member: tarfile.TarInfo) -> bool:
    """
    Only extract what the scanner would ever read: regular files with a
    supported source extension that are not inside an ignored directory.
    Everything else (images, fixtures, node_modules, docs assets) is pure
    cost - and on Windows it is also a liability, because one file whose
    full path exceeds the 260-character MAX_PATH limit used to abort the
    entire analysis (seen live on a repo with a very long test-fixture name).
    """
    if not member.isfile():
        return False
    parts = member.name.split("/")
    # parts[0] is GitHub's top-level "owner-repo-<sha>" directory
    if any(part in DEFAULT_IGNORE_DIRS or part.startswith(".") for part in parts[1:-1]):
        return False
    return os.path.splitext(parts[-1])[1] in SUPPORTED_EXTENSIONS


def _safe_extract(tar: tarfile.TarFile, dest: str) -> int:
    """
    Extracts the source files from the tarball into dest and returns how many
    wanted files could not be written (e.g. path too long on Windows).

    Two protections: a manual check that no entry escapes dest via '../'
    ("tar slip"), plus tarfile's own filter="data" where available. A single
    unwritable file is skipped and counted rather than failing the whole
    analysis.
    """
    dest_abs = os.path.abspath(dest)
    members = tar.getmembers()
    for member in members:
        member_path = os.path.abspath(os.path.join(dest, member.name))
        if not (member_path == dest_abs or member_path.startswith(dest_abs + os.sep)):
            raise GitHubFetchError("Tarball contains an unsafe path, refusing to extract")

    skipped = 0
    for member in members:
        if not _wanted_member(member):
            continue
        try:
            try:
                tar.extract(member, dest, filter="data")
            except TypeError:  # Python < 3.12 has no `filter` kwarg
                tar.extract(member, dest)
        except OSError as exc:
            logger.warning("Skipping %s: %s", member.name, exc)
            skipped += 1
    return skipped


def fetch_github_repo(url: str, access_token: str | None = None) -> FetchedRepo:
    """
    access_token: a signed-in user's own GitHub OAuth token, if any. Used
    for every request in this function - repo lookup, tarball download -
    so private-repo access and the per-user rate limit are the same token.
    """
    owner, repo, ref = parse_github_url(url)

    metadata = _get_repo_metadata(owner, repo, access_token)
    size_kb = metadata.get("size", 0)
    if size_kb > MAX_REPO_SIZE_KB:
        raise GitHubFetchError(
            f"{owner}/{repo} is too large to analyze "
            f"({size_kb / 1000:.0f} MB, limit is {MAX_REPO_SIZE_KB / 1000:.0f} MB)"
        )

    resolved_ref = ref or metadata.get("default_branch") or "HEAD"

    tarball_url = f"{GITHUB_API}/repos/{owner}/{repo}/tarball/{resolved_ref}"
    resp = requests.get(
        tarball_url, headers=_github_headers(access_token), timeout=REQUEST_TIMEOUT_SECONDS, stream=True
    )
    if resp.status_code == 404:
        raise GitHubFetchError(f"Branch or ref not found: {resolved_ref}")
    if not resp.ok:
        raise GitHubFetchError(f"Failed to download tarball ({resp.status_code})")

    tmp_dir = tempfile.mkdtemp(prefix="codemap-gh-")
    try:
        tarball_path = os.path.join(tmp_dir, "repo.tar.gz")
        with open(tarball_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        with tarfile.open(tarball_path, "r:gz") as tar:
            skipped = _safe_extract(tar, tmp_dir)
        os.remove(tarball_path)
        if skipped:
            logger.warning("%s/%s: %d source file(s) could not be extracted", owner, repo, skipped)

        # GitHub tarballs contain exactly one top-level directory (e.g. "owner-repo-<sha>/")
        entries = [e for e in os.listdir(tmp_dir) if os.path.isdir(os.path.join(tmp_dir, e))]
        if len(entries) != 1:
            raise GitHubFetchError("Unexpected tarball structure from GitHub")

        extracted_root = os.path.join(tmp_dir, entries[0])
        return FetchedRepo(
            local_path=extracted_root, owner=owner, repo=repo, ref=resolved_ref,
            is_private=bool(metadata.get("private")),
        )
    except (tarfile.TarError, OSError) as exc:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise GitHubFetchError(f"Could not unpack {owner}/{repo}: {exc}") from exc
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
