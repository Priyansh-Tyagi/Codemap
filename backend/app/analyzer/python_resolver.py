"""
Python import resolver.

Structurally different from the JS resolver (resolver.py), not just a
copy with renamed variables - Python's import system has no free syntactic
marker for "this is local" the way JS's "./" prefix is. A relative import
(`from . import x`, level >= 1) is unambiguously local by definition. An
absolute import (`import foo.bar`, level == 0) is ambiguous: `foo` might be
a local package, or it might be a pip-installed one. For absolute imports,
classification and resolution are the same step here - we ATTEMPT to
resolve it against the project; success means local, failure means we
treat it as external (a third-party package or stdlib module), the same
way JS treats "react" as external without even trying to resolve it -
Python just doesn't give us that answer for free, so we have to check.

Where an absolute import is looked for (first match wins):
  1. the project root;
  2. <project root>/src, the conventional src-layout;
  3. each parent directory of the importing file, nearest first.
(3) mirrors how Python actually runs most apps: it puts the running
script's directory on sys.path, so a backend started from backend/ writes
`from routes.simulation import router` even though routes/ is not at the
repo root. This was found on a real project whose Python backend showed zero
connections: every one of its imports was relative to backend/, and a
resolver that only tried the repo root classified all of them as external.
Standard-library names (sys.stdlib_module_names) are never resolved through
(3), so a local folder named `json` or `types` can't capture `import json`.

Deliberately NOT a full Python import-system reimplementation - documented
limitation. Does not distinguish regular packages (with __init__.py) from
implicit namespace packages (PEP 420) - both are treated the same way (any
directory is a valid package for resolution purposes). Does not read
sys.path edits or PYTHONPATH, so a project that relies on those to find code
outside the importing file's own ancestors is still not resolved.
"""

from __future__ import annotations

import os
import sys

_STDLIB = getattr(sys, "stdlib_module_names", frozenset())


class ResolutionKind:
    LOCAL = "local"
    EXTERNAL = "external"
    UNRESOLVED = "unresolved"  # relative import that SHOULD be local but no matching file was found


def _package_dir_for(importing_file: str, level: int) -> str:
    """
    The directory a relative import is resolved relative to.

    level=1 ("from . import x") means "my own containing package" - i.e.
    the directory the importing file lives in.
    level=2 ("from .. import x") means one package up from that, and so on.
    """
    base = os.path.dirname(importing_file)
    for _ in range(level - 1):
        base = os.path.dirname(base)
    return base


def _try_module_file(candidate_base: str) -> str | None:
    """foo/bar -> foo/bar.py"""
    candidate = candidate_base + ".py"
    return candidate if os.path.isfile(candidate) else None


def _try_package_init(candidate_base: str) -> str | None:
    """foo/bar -> foo/bar/__init__.py"""
    candidate = os.path.join(candidate_base, "__init__.py")
    return candidate if os.path.isfile(candidate) else None


def _within_project_root(resolved_abs: str, project_root: str) -> bool:
    project_root_abs = os.path.abspath(project_root)
    return (
        os.path.commonpath([project_root_abs, resolved_abs]) == project_root_abs
    )


def _absolute_import_roots(importing_file: str, project_root: str, top_level: str) -> list[str]:
    """Directories an absolute import may be resolved against, in priority order."""
    root = os.path.abspath(project_root)
    roots = [root]
    src = os.path.join(root, "src")
    if os.path.isdir(src):
        roots.append(src)
    if top_level not in _STDLIB:
        directory = os.path.dirname(os.path.abspath(importing_file))
        while directory != root and _within_project_root(directory, root):
            if directory not in roots:
                roots.append(directory)
            parent = os.path.dirname(directory)
            if parent == directory:
                break
            directory = parent
    return roots


def resolve_python_import(
    importing_file: str, module_path: str, level: int, project_root: str,
    is_bare_dot_name: bool = False,
) -> tuple[str | None, str]:
    """
    Returns (resolved_absolute_path_or_None, ResolutionKind).

    module_path: dotted path, e.g. "foo.bar" (never comma-separated - the
        parser already flattened multi-name imports into separate records).
    level: 0 for an absolute import, N for N dots of relative-ness.
    is_bare_dot_name: True for `from . import name` (parser's symbols==["*"]
        case). There, module_path is actually the imported NAME, not
        necessarily a submodule - Python resolves it as a submodule if one
        exists, but otherwise as an attribute already defined in the
        containing package's __init__.py (a very common pattern: a package
        builds a singleton in __init__.py, e.g. `calibre_db = CalibreDB()`,
        and sibling modules do `from . import calibre_db`). Only this bare
        form gets that fallback - `from .foo import x` requires `foo` itself
        to be a real module, so it must resolve on its own.
    """
    segments = module_path.split(".")

    if level == 0:
        resolved = None
        for base_dir in _absolute_import_roots(importing_file, project_root, segments[0]):
            candidate_base = os.path.normpath(os.path.join(base_dir, *segments))
            resolved = _try_module_file(candidate_base) or _try_package_init(candidate_base)
            if resolved:
                break
    else:
        base_dir = _package_dir_for(importing_file, level)
        candidate_base = os.path.normpath(os.path.join(base_dir, *segments))
        resolved = _try_module_file(candidate_base) or _try_package_init(candidate_base)

    if resolved is None and is_bare_dot_name and level > 0:
        # Not a submodule - try the containing package's own __init__.py,
        # in case `name` is an attribute defined there instead. Skip this
        # when the importing file IS that __init__.py: a name it can't find
        # in itself isn't suddenly found by "importing itself", and treating
        # it as resolved would create a false self-loop edge.
        init_candidate = _try_package_init(base_dir)
        if init_candidate and os.path.abspath(init_candidate) != os.path.abspath(importing_file):
            resolved = init_candidate

    if resolved is None:
        # Absolute import that didn't resolve = treat as a third-party/stdlib
        # package, same as JS's bare "react" specifier. Relative import that
        # didn't resolve = genuinely broken, since relative imports can only
        # ever mean "something in this project".
        kind = ResolutionKind.EXTERNAL if level == 0 else ResolutionKind.UNRESOLVED
        return None, kind

    resolved_abs = os.path.abspath(resolved)
    if not _within_project_root(resolved_abs, project_root):
        # Resolved technically, but climbed outside the project (e.g. a
        # relative import with more ".." than the project is deep). Same
        # containment principle as the JS resolver's security guard.
        kind = ResolutionKind.EXTERNAL if level == 0 else ResolutionKind.UNRESOLVED
        return None, kind

    return resolved_abs, ResolutionKind.LOCAL
