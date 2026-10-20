"""
Repository scanner.

Walks a repo root, applies ignore rules, and returns the list of
JS/TS/JSX/TSX source files to analyze. Ignore rules are applied at the
directory level (os.walk lets us prune dirs in-place) so we never even
descend into node_modules/.git/etc - not just filter results after the fact.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

DEFAULT_IGNORE_DIRS = {
    "node_modules",
    ".git",
    "dist",
    "build",
    "coverage",
    ".next",
    ".cache",
    "venv",
    "__pycache__",
}

SUPPORTED_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx", ".py"}
PYTHON_EXTENSIONS = {".py"}

# Resource ceilings. The repository being scanned is untrusted input (anyone
# can point a public server at any GitHub repo), and every scanned file is
# parsed - by Babel in a subprocess, or by Python's own parser inside the
# server process. Without limits one hostile repo (a million tiny files, a
# 200 MB generated bundle, deeply nested expressions) could pin the server.
# Real source files are far below these; generated/minified bundles are
# skipped, which is also what a human reading a dependency graph wants.
MAX_FILES = 20_000
MAX_FILE_BYTES = 2 * 1024 * 1024  # 2 MB


class ScanLimitError(ValueError):
    """The repository is larger than this server is willing to analyze."""


@dataclass
class ScanResult:
    root: str
    files: list[str] = field(default_factory=list)  # absolute paths
    skipped_dirs: list[str] = field(default_factory=list)
    skipped_files: list[str] = field(default_factory=list)  # symlinks and oversized files

    @property
    def file_count(self) -> int:
        return len(self.files)


def scan_repository(
    root_path: str,
    ignore_dirs: set[str] | None = None,
    extensions: set[str] | None = None,
) -> ScanResult:
    """
    Recursively scan `root_path` for source files.

    Raises:
        ScanLimitError: if the repo has more than MAX_FILES source files.
        FileNotFoundError: if root_path doesn't exist.
        NotADirectoryError: if root_path isn't a directory.
    """
    if not os.path.exists(root_path):
        raise FileNotFoundError(f"path does not exist: {root_path}")
    if not os.path.isdir(root_path):
        raise NotADirectoryError(f"path is not a directory: {root_path}")

    ignore = ignore_dirs if ignore_dirs is not None else DEFAULT_IGNORE_DIRS
    exts = extensions if extensions is not None else SUPPORTED_EXTENSIONS

    result = ScanResult(root=os.path.abspath(root_path))

    for dirpath, dirnames, filenames in os.walk(result.root):
        # Prune ignored directories in-place so os.walk never descends into them.
        kept = []
        for d in dirnames:
            if d in ignore or d.startswith("."):
                result.skipped_dirs.append(os.path.join(dirpath, d))
            else:
                kept.append(d)
        dirnames[:] = kept

        for filename in filenames:
            _, ext = os.path.splitext(filename)
            if ext not in exts:
                continue
            full = os.path.join(dirpath, filename)
            # Never follow a file symlink: it can point anywhere on the machine
            # (a link named util.py -> the server's own source or a config
            # file), which would pull that file into the parse and the graph.
            if os.path.islink(full):
                result.skipped_files.append(full)
                continue
            try:
                too_big = os.path.getsize(full) > MAX_FILE_BYTES
            except OSError:
                continue
            if too_big:
                result.skipped_files.append(full)
                continue
            result.files.append(full)
            if len(result.files) > MAX_FILES:
                raise ScanLimitError(
                    f"This repository has more than {MAX_FILES:,} source files, which is more than "
                    f"this server will analyze."
                )

    return result
