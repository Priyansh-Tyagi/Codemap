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


@dataclass
class ScanResult:
    root: str
    files: list[str] = field(default_factory=list)  # absolute paths
    skipped_dirs: list[str] = field(default_factory=list)

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
            if ext in exts:
                result.files.append(os.path.join(dirpath, filename))

    return result
