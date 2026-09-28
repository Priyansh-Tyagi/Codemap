"""
Regression tests for a scaling problem found by analyzing real repos:
Flask's 19-file core has 9,629 elementary cycles. Listing them all is useless
and enumerating them is unbounded-cost, so listing is capped, while
"is this file in a cycle" stays exact (from strongly connected components).
"""

import os
import random
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import networkx as nx
import pytest
from fastapi.testclient import TestClient

from cli import _find_new_cycles
from graph.analysis import run_full_analysis
from graph.cycles import (
    MAX_CYCLES, cyclic_components, detect_cycles, detect_cycles_capped, nodes_in_cycles,
)
from main import app


def _complete_digraph(n: int) -> nx.DiGraph:
    g = nx.DiGraph()
    for i in range(n):
        g.add_node(f"f{i}.js", filePath=f"f{i}.js", name=f"f{i}.js", linesOfCode=10)
    for i in range(n):
        for j in range(n):
            if i != j:
                g.add_edge(f"f{i}.js", f"f{j}.js")
    return g


def _with_attrs(g: nx.DiGraph) -> nx.DiGraph:
    for n in g.nodes:
        g.nodes[n].setdefault("filePath", n)
        g.nodes[n].setdefault("name", n)
        g.nodes[n].setdefault("linesOfCode", 10)
    return g


def test_small_graph_is_untruncated_and_unchanged():
    g = nx.DiGraph([("a", "b"), ("b", "c"), ("c", "a")])
    cycles, truncated = detect_cycles_capped(g)
    assert truncated is False
    assert len(cycles) == 1
    assert cycles[0]["chain"][0] == cycles[0]["chain"][-1]


def test_dense_graph_is_capped_fast_and_flagged():
    g = _complete_digraph(9)  # ~100k+ elementary cycles if fully enumerated
    start = time.time()
    cycles, truncated = detect_cycles_capped(g)
    assert time.time() - start < 5
    assert truncated is True
    assert len(cycles) == MAX_CYCLES
    lengths = [len(c["chain"]) - 1 for c in cycles]
    assert lengths == sorted(lengths)          # shortest first
    assert lengths[0] == 2                      # mutual 2-file cycles come first


def test_truncated_listing_never_drops_cycle_membership():
    g = _complete_digraph(9)
    analysis = run_full_analysis(g)
    assert analysis["cycles_truncated"] is True
    assert analysis["nodes_in_cycles"] == set(g.nodes)   # exact, not from the capped list
    assert len(analysis["cycle_components"]) == 1
    assert len(analysis["cycle_components"][0]) == 9


def test_component_membership_matches_cycle_membership_on_random_graphs():
    rng = random.Random(7)
    for _ in range(40):
        n = rng.randint(2, 9)
        g = nx.gnp_random_graph(n, rng.uniform(0.1, 0.4), seed=rng.randint(0, 10**6), directed=True)
        from_components = {x for comp in cyclic_components(g) for x in comp}
        from_cycles = nodes_in_cycles(detect_cycles(g))
        assert from_components == from_cycles


def test_acyclic_graph_has_no_components_and_self_loop_counts():
    assert cyclic_components(nx.DiGraph([("a", "b"), ("b", "c")])) == []
    g = nx.DiGraph([("a", "a")])
    assert cyclic_components(g) == [["a"]]


def test_baseline_diff_does_not_flap_when_truncated():
    base_graph = _complete_digraph(9)
    baseline_analysis = run_full_analysis(base_graph)
    baseline = {
        "cycles": baseline_analysis["cycles"],
        "cyclesTruncated": True,
        "cycleComponents": baseline_analysis["cycle_components"],
    }
    # Same tangle, one internal edge removed: the *listed* subset can change,
    # but no new tangle exists, so nothing should be reported.
    changed = base_graph.copy()
    changed.remove_edge("f0.js", "f1.js")
    assert _find_new_cycles(run_full_analysis(changed), baseline) == []


def test_baseline_diff_flags_new_tangle_and_growth_when_truncated():
    base_graph = _complete_digraph(9)
    a = run_full_analysis(base_graph)
    baseline = {"cycles": a["cycles"], "cyclesTruncated": True,
                "cycleComponents": a["cycle_components"]}

    # a brand-new separate two-file cycle
    with_new = base_graph.copy()
    with_new.add_edges_from([("x.js", "y.js"), ("y.js", "x.js")])
    new = _find_new_cycles(run_full_analysis(_with_attrs(with_new)), baseline)
    assert new == [frozenset({"x.js", "y.js"})]

    # an existing tangle growing by one file
    grown = base_graph.copy()
    grown.add_edges_from([("f0.js", "extra.js"), ("extra.js", "f0.js")])
    new = _find_new_cycles(run_full_analysis(_with_attrs(grown)), baseline)
    assert len(new) == 1 and "extra.js" in new[0]


def test_old_style_baseline_without_components_still_works():
    g = nx.DiGraph([("a", "b"), ("b", "a")])
    for n in g.nodes:
        g.nodes[n].update(filePath=n, name=n, linesOfCode=1)
    analysis = run_full_analysis(g)
    old_baseline = {"cycles": analysis["cycles"]}  # no truncation, no components
    assert _find_new_cycles(analysis, old_baseline) == []


def test_api_reports_truncation_and_it_survives_storage(tmp_path):
    repo = tmp_path / "dense"
    repo.mkdir()
    n = 9
    for i in range(n):
        imports = "\n".join(
            f"import {{ v{j} }} from './f{j}';" for j in range(n) if j != i
        )
        (repo / f"f{i}.js").write_text(f"{imports}\nexport const v{i} = {i};\n")

    client = TestClient(app)
    body = client.post("/api/analyze", json={"path": str(repo)}).json()
    assert body["cyclesTruncated"] is True
    assert body["cycleCount"] == MAX_CYCLES
    assert body["cyclicComponentCount"] == 1

    # read back from SQLite via a separate request
    summary = client.get(f"/api/projects/{body['projectId']}").json()
    assert summary["cyclesTruncated"] is True
    assert summary["cyclicComponentCount"] == 1
    graph = client.get(f"/api/projects/{body['projectId']}/graph").json()
    assert all(node["inCycle"] for node in graph["nodes"])


def test_truncated_selection_is_identical_across_processes_with_different_hash_seeds():
    """String hashing is randomized per process; the chosen cycles must not depend on it."""
    import subprocess
    code = (
        "import networkx as nx, json\n"
        "from graph.cycles import detect_cycles_capped\n"
        "g = nx.DiGraph()\n"
        "n = 9\n"
        "g.add_edges_from((f'f{i}.js', f'f{j}.js') for i in range(n) for j in range(n) if i != j)\n"
        "print(json.dumps(detect_cycles_capped(g)))\n"
    )
    app_dir = os.path.join(os.path.dirname(__file__), "..", "app")
    outputs = set()
    for seed in ("1", "2", "3"):
        result = subprocess.run(
            [sys.executable, "-c", code], cwd=app_dir, capture_output=True, text=True,
            env={**os.environ, "PYTHONHASHSEED": seed}, timeout=60,
        )
        assert result.returncode == 0, result.stderr
        outputs.add(result.stdout)
    assert len(outputs) == 1
