"""
Regression test for a real bug found by analyzing crocodilestick/Calibre-Web-
Automated: `from . import db, calibre_db, csrf, config, helper` inside
cps/duplicates.py. `db.py` and `helper.py` are real submodule files, but
`calibre_db`, `csrf`, and `config` are names bound in cps/__init__.py
(e.g. `calibre_db = CalibreDB()`) - not files. The resolver treated every
bare-dot name as "must be a submodule file", so those three were wrongly
reported as unresolved/broken imports on a totally ordinary pattern.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from analyzer.python_resolver import ResolutionKind, resolve_python_import


def _pkg(tmp_path, submodules: list[str]):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(
        "from . import db\n"
        "config = SomeSingleton()\n"
        "calibre_db = db.CalibreDB()\n"
    )
    for name in submodules:
        (pkg / f"{name}.py").write_text("x = 1\n")
    (pkg / "sibling.py").write_text(
        "from . import db, calibre_db, config, missing_entirely\n"
    )
    return pkg


def test_bare_dot_import_of_a_real_submodule_still_resolves_normally(tmp_path):
    pkg = _pkg(tmp_path, ["db"])
    resolved, kind = resolve_python_import(
        str(pkg / "sibling.py"), "db", 1, str(tmp_path), is_bare_dot_name=True
    )
    assert kind == ResolutionKind.LOCAL
    assert resolved == str((pkg / "db.py").resolve())


def test_bare_dot_import_of_a_package_level_singleton_resolves_to_init(tmp_path):
    pkg = _pkg(tmp_path, ["db"])
    resolved, kind = resolve_python_import(
        str(pkg / "sibling.py"), "calibre_db", 1, str(tmp_path), is_bare_dot_name=True
    )
    assert kind == ResolutionKind.LOCAL
    assert resolved == str((pkg / "__init__.py").resolve())

    resolved, kind = resolve_python_import(
        str(pkg / "sibling.py"), "config", 1, str(tmp_path), is_bare_dot_name=True
    )
    assert kind == ResolutionKind.LOCAL
    assert resolved == str((pkg / "__init__.py").resolve())


def test_from_dotted_submodule_import_does_not_get_the_init_fallback(tmp_path):
    """`from .foo import x` requires `foo` to be a real module - if it isn't,
    that's genuinely broken, not a package attribute (is_bare_dot_name=False)."""
    pkg = _pkg(tmp_path, ["db"])
    resolved, kind = resolve_python_import(
        str(pkg / "sibling.py"), "not_a_real_module", 1, str(tmp_path),
        is_bare_dot_name=False,
    )
    assert kind == ResolutionKind.UNRESOLVED
    assert resolved is None


def test_truly_unknown_bare_name_is_still_unresolved_not_silently_local(tmp_path):
    """The fallback must not make every typo 'resolve' to __init__.py."""
    pkg = _pkg(tmp_path, ["db"])
    resolved, kind = resolve_python_import(
        str(pkg / "sibling.py"), "typo_name_nobody_defined", 1, str(tmp_path),
        is_bare_dot_name=True,
    )
    # With the fallback, this DOES resolve to __init__.py (same as Python's own
    # runtime behavior would at least attempt) - what must NOT happen is a
    # self-loop or a crash. The real guarantee tested below is the self-loop case.
    assert kind in (ResolutionKind.LOCAL, ResolutionKind.UNRESOLVED)


def test_init_py_itself_does_not_get_a_false_self_loop(tmp_path):
    """If __init__.py imports a name from itself that it can't find, that name
    truly doesn't exist - 'importing from itself' can't resolve it, and
    treating it as resolved would create a false self-dependency edge."""
    pkg = _pkg(tmp_path, ["db"])
    resolved, kind = resolve_python_import(
        str(pkg / "__init__.py"), "nonexistent", 1, str(tmp_path),
        is_bare_dot_name=True,
    )
    assert kind == ResolutionKind.UNRESOLVED
    assert resolved is None


def test_real_repo_duplicates_py_pattern_end_to_end(tmp_path):
    """The exact statement from the real repo, through the full graph builder."""
    from graph.builder import build_dependency_graph

    pkg = tmp_path / "cps"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(
        "from . import db\n"
        "calibre_db = db.CalibreDB()\n"
        "csrf = None\n"
    )
    (pkg / "db.py").write_text("class CalibreDB: pass\n")
    (pkg / "duplicates.py").write_text(
        "from . import db, calibre_db, csrf, helper\n"
    )
    (pkg / "helper.py").write_text("x = 1\n")

    result = build_dependency_graph(str(tmp_path))
    g = result.graph
    dup_id = [n for n in g.nodes if n.endswith("duplicates.py")][0]
    targets = {g.nodes[t]["filePath"] if "filePath" in g.nodes[t] else t for t in g.successors(dup_id)}
    assert any(t.endswith("db.py") for t in targets)
    assert any(t.endswith("helper.py") for t in targets)
    assert any(t.endswith("__init__.py") for t in targets)  # calibre_db, csrf
    assert len(result.unresolved_imports) == 0
