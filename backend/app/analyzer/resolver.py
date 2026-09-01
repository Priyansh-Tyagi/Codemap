"""
Local import resolver.

Given the file that contains an import statement, and the raw specifier
it imports (e.g. "./utils", "../models/User"), figure out which actual
file on disk that refers to.

Deliberately NOT a full Node/bundler resolution algorithm - documented
limitation. Handles the common cases:
  - exact file with extension already given
  - specifier + one of the supported extensions
  - specifier as a directory containing an index.* file

Does not handle: tsconfig `paths` aliases, package "exports" maps,
symlinks, case-insensitive filesystems edge cases.
"""

from __future__ import annotations

import os

RESOLUTION_EXTENSIONS = [".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"]
INDEX_BASENAMES = [f"index{ext}" for ext in RESOLUTION_EXTENSIONS]


def resolve_specifier(importing_file: str, specifier: str, project_root: str) -> str | None:
    """
    Resolve `specifier` (as imported from `importing_file`) to an absolute
    path within `project_root`.

    Returns None if it can't be resolved (missing file, or resolves outside
    the project root - which we treat as unresolved rather than following it,
    since it's not part of the analyzed codebase).
    """
    importing_dir = os.path.dirname(importing_file)
    candidate_base = os.path.normpath(os.path.join(importing_dir, specifier))

    resolved = (
        _try_exact_file(candidate_base)
        or _try_with_extensions(candidate_base)
        or _try_as_index_directory(candidate_base)
    )

    if resolved is None:
        return None

    # Guard: resolved path must stay within project_root.
    project_root_abs = os.path.abspath(project_root)
    resolved_abs = os.path.abspath(resolved)
    if os.path.commonpath([project_root_abs, resolved_abs]) != project_root_abs:
        return None

    return resolved_abs


def _try_exact_file(candidate_base: str) -> str | None:
    if os.path.isfile(candidate_base):
        return candidate_base
    return None


def _try_with_extensions(candidate_base: str) -> str | None:
    for ext in RESOLUTION_EXTENSIONS:
        candidate = candidate_base + ext
        if os.path.isfile(candidate):
            return candidate
    return None


def _try_as_index_directory(candidate_base: str) -> str | None:
    if not os.path.isdir(candidate_base):
        return None
    for index_name in INDEX_BASENAMES:
        candidate = os.path.join(candidate_base, index_name)
        if os.path.isfile(candidate):
            return candidate
    return None
