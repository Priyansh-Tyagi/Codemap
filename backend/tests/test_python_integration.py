"""
End-to-end tests for Python support through the real build_dependency_graph
pipeline - not the parser/resolver in isolation (those are covered in
test_python_parser.py / test_python_resolver.py), but the actual wiring:
does a genuine Python repo on disk produce the right graph.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from graph.builder import build_dependency_graph


def _write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def test_python_only_repo_builds_correct_graph(tmp_path):
    """
    myapp/
      __init__.py
      services/
        __init__.py
        auth.py           <-> user_service.py (a genuine cycle)
        user_service.py
      models/
        __init__.py
        user.py
    """
    _write(tmp_path / "myapp" / "__init__.py", "")
    _write(tmp_path / "myapp" / "services" / "__init__.py", "")
    _write(
        tmp_path / "myapp" / "services" / "auth.py",
        "from .user_service import find_user\n\ndef issue_token(): return find_user(1)\n",
    )
    _write(
        tmp_path / "myapp" / "services" / "user_service.py",
        "from .auth import issue_token\n\ndef find_user(id): return issue_token()\n",
    )
    _write(tmp_path / "myapp" / "models" / "__init__.py", "")
    _write(tmp_path / "myapp" / "models" / "user.py", "class User:\n    pass\n")

    result = build_dependency_graph(str(tmp_path))
    g = result.graph

    node_paths = set(g.nodes)
    assert "myapp/services/auth.py" in node_paths
    assert "myapp/services/user_service.py" in node_paths
    assert "myapp/models/user.py" in node_paths

    # the genuine cycle
    assert g.has_edge("myapp/services/auth.py", "myapp/services/user_service.py")
    assert g.has_edge("myapp/services/user_service.py", "myapp/services/auth.py")

    # every node correctly tagged as python
    for node_id in node_paths:
        assert g.nodes[node_id]["language"] == "python"


def test_stdlib_and_pip_imports_counted_as_external_not_edges(tmp_path):
    _write(tmp_path / "app.py", "import os\nimport requests\nimport json\n")

    result = build_dependency_graph(str(tmp_path))
    assert result.graph.number_of_edges() == 0
    assert result.external_dependencies == {"os": 1, "requests": 1, "json": 1}


def test_broken_relative_import_is_reported_as_unresolved(tmp_path):
    _write(tmp_path / "app.py", "from . import does_not_exist\n")

    result = build_dependency_graph(str(tmp_path))
    assert result.graph.number_of_edges() == 0
    assert len(result.unresolved_imports) == 1
    assert result.unresolved_imports[0]["specifier"] == "does_not_exist"


def test_import_symbols_carried_through_to_the_graph(tmp_path):
    _write(tmp_path / "models.py", "class User:\n    pass\n")
    _write(
        tmp_path / "app.py",
        "from models import User\n",
    )

    result = build_dependency_graph(str(tmp_path))
    edge_data = result.graph.edges["app.py", "models.py"]
    assert edge_data["symbols"] == ["User"]


def test_mixed_language_repo_no_cross_language_edges(tmp_path):
    """
    The critical correctness guarantee for this whole feature: a JS file
    and a Python file that happen to share a base name must NEVER link to
    each other on the graph, even though both exist and both are named
    "utils". Each language's resolver only looks for its own extensions,
    so this should hold structurally - this test proves it rather than
    just asserting it in a comment.
    """
    _write(tmp_path / "src" / "utils.py", "def helper():\n    pass\n")
    _write(tmp_path / "src" / "utils.js", "export function helper() {}\n")

    # a Python file importing "./utils" the Python way
    _write(tmp_path / "src" / "app.py", "from .utils import helper\n")
    # a JS file importing "./utils" the JS way
    _write(tmp_path / "src" / "app.js", "import { helper } from './utils';\n")

    result = build_dependency_graph(str(tmp_path))
    g = result.graph

    # app.py must resolve to utils.py, never utils.js
    assert g.has_edge("src/app.py", "src/utils.py")
    assert not g.has_edge("src/app.py", "src/utils.js")

    # app.js must resolve to utils.js, never utils.py
    assert g.has_edge("src/app.js", "src/utils.js")
    assert not g.has_edge("src/app.js", "src/utils.py")

    # and the languages are correctly tagged
    assert g.nodes["src/utils.py"]["language"] == "python"
    assert g.nodes["src/utils.js"]["language"] == "javascript"


def test_mixed_language_repo_python_cannot_resolve_into_js_even_by_name_collision(tmp_path):
    """
    A stricter version of the above: even if a Python module path segment
    happens to match a JS filename stem exactly, Python resolution must
    never even consider .js/.jsx/.ts/.tsx as candidate extensions.
    """
    _write(tmp_path / "shared.js", "export const x = 1;\n")
    _write(tmp_path / "app.py", "import shared\n")  # "shared" only exists as .js, not .py

    result = build_dependency_graph(str(tmp_path))
    # must NOT resolve to shared.js - correctly falls through to "external"
    # (Python has no local "shared" module) rather than silently linking
    # into an unrelated JS file of the same name
    assert result.graph.number_of_edges() == 0
    assert "shared" in result.external_dependencies
