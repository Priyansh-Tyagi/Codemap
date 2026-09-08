"""
Tests for graph/builder.py, run against fixture repos built in-test.

Requires `node` on PATH with parser/ dependencies installed
(npm install in backend/parser), since the builder calls the full
scan -> parse -> classify -> resolve pipeline under the hood.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest
from graph.builder import build_dependency_graph


@pytest.fixture
def linear_repo(tmp_path):
    """A -> B -> C, no cycles."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.js").write_text("import b from './b';\n")
    (src / "b.js").write_text("import c from './c';\n")
    (src / "c.js").write_text("export default 1;\n")
    return tmp_path


@pytest.fixture
def cyclic_repo(tmp_path):
    """A -> B -> C -> A, a genuine cycle."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.js").write_text("import b from './b';\n")
    (src / "b.js").write_text("import c from './c';\n")
    (src / "c.js").write_text("import a from './a';\n")
    return tmp_path


def test_builds_correct_nodes_and_edges(linear_repo):
    result = build_dependency_graph(str(linear_repo))
    g = result.graph

    node_names = {os.path.basename(n) for n in g.nodes}
    assert node_names == {"a.js", "b.js", "c.js"}
    assert g.number_of_edges() == 2

    a_id = next(n for n in g.nodes if n.endswith("a.js"))
    b_id = next(n for n in g.nodes if n.endswith("b.js"))
    c_id = next(n for n in g.nodes if n.endswith("c.js"))
    assert g.has_edge(a_id, b_id)
    assert g.has_edge(b_id, c_id)
    assert not g.has_edge(a_id, c_id)  # no direct edge, only transitive


def test_isolated_and_unresolved_files_still_tracked(linear_repo):
    result = build_dependency_graph(str(linear_repo))
    # c.js has no outgoing local imports but must still be a node
    c_id = next(n for n in result.graph.nodes if n.endswith("c.js"))
    assert result.graph.out_degree(c_id) == 0


def test_no_duplicate_edges_for_repeated_import(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.js").write_text(
        "import { x } from './b';\nimport { y } from './b';\n"
    )
    (src / "b.js").write_text("export const x = 1; export const y = 2;\n")

    result = build_dependency_graph(str(tmp_path))
    assert result.graph.number_of_edges() == 1

    a_id = next(n for n in result.graph.nodes if n.endswith("a.js"))
    b_id = next(n for n in result.graph.nodes if n.endswith("b.js"))
    # both statements' symbols must survive the merge, not just the first
    assert result.graph.edges[a_id, b_id]["symbols"] == ["x", "y"]


def test_default_import_symbol_is_labeled_default(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.js").write_text("import Widget from './widget';\n")
    (src / "widget.js").write_text("export default function Widget() {}\n")

    result = build_dependency_graph(str(tmp_path))
    a_id = next(n for n in result.graph.nodes if n.endswith("a.js"))
    w_id = next(n for n in result.graph.nodes if n.endswith("widget.js"))
    assert result.graph.edges[a_id, w_id]["symbols"] == ["default"]


def test_named_import_reports_source_side_name_not_local_alias(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.js").write_text(
        "import { createUser as makeUser } from './userService';\n"
    )
    (src / "userService.js").write_text("export function createUser() {}\n")

    result = build_dependency_graph(str(tmp_path))
    a_id = next(n for n in result.graph.nodes if n.endswith("a.js"))
    s_id = next(n for n in result.graph.nodes if n.endswith("userService.js"))
    # "createUser" (what the source file exports), not "makeUser" (the local alias)
    assert result.graph.edges[a_id, s_id]["symbols"] == ["createUser"]


def test_namespace_import_symbol_is_wildcard(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.js").write_text("import * as utils from './utils';\n")
    (src / "utils.js").write_text("export function helper() {}\n")

    result = build_dependency_graph(str(tmp_path))
    a_id = next(n for n in result.graph.nodes if n.endswith("a.js"))
    u_id = next(n for n in result.graph.nodes if n.endswith("utils.js"))
    assert result.graph.edges[a_id, u_id]["symbols"] == ["*"]


def test_require_destructure_captures_symbol_names(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.js").write_text("const { query, close } = require('./db');\n")
    (src / "db.js").write_text("module.exports = { query() {}, close() {} };\n")

    result = build_dependency_graph(str(tmp_path))
    a_id = next(n for n in result.graph.nodes if n.endswith("a.js"))
    db_id = next(n for n in result.graph.nodes if n.endswith("db.js"))
    assert set(result.graph.edges[a_id, db_id]["symbols"]) == {"query", "close"}


def test_cyclic_graph_has_expected_structure(cyclic_repo):
    result = build_dependency_graph(str(cyclic_repo))
    g = result.graph
    assert g.number_of_nodes() == 3
    assert g.number_of_edges() == 3
    for node in g.nodes:
        assert g.out_degree(node) == 1
        assert g.in_degree(node) == 1
