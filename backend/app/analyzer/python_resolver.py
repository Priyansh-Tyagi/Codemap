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

Deliberately NOT a full Python import-system reimplementation - documented
limitation. Does not distinguish regular packages (with __init__.py) from
implicit namespace packages (PEP 420) - both are treated the same way
(any directory is a valid package for resolution purposes). Does not
support a `src/`-layout project where the real package root is nested
below the project root passed in.
"""

from __future__ import annotations

import os


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


def resolve_python_import(
    importing_file: str, module_path: str, level: int, project_root: str
) -> tuple[str | None, str]:
    """
    Returns (resolved_absolute_path_or_None, ResolutionKind).

    module_path: dotted path, e.g. "foo.bar" (never comma-separated - the
        parser already flattened multi-name imports into separate records).
    level: 0 for an absolute import, N for N dots of relative-ness.
    """
    if level == 0:
        base_dir = os.path.abspath(project_root)
    else:
        base_dir = _package_dir_for(importing_file, level)

    segments = module_path.split(".")
    candidate_base = os.path.normpath(os.path.join(base_dir, *segments))

    resolved = _try_module_file(candidate_base) or _try_package_init(candidate_base)

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
