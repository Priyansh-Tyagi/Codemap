import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import networkx as nx
from graph.metrics import (
    compute_degrees,
    compute_dependency_depth,
    compute_graph_metrics,
    BETWEENNESS_NODE_LIMIT,
)


def linear_graph():
    """a -> b -> c"""
    g = nx.DiGraph()
    g.add_edge("a", "b")
    g.add_edge("b", "c")
    return g


def cyclic_graph():
    """a -> b -> c -> a"""
    g = nx.DiGraph()
    g.add_edge("a", "b")
    g.add_edge("b", "c")
    g.add_edge("c", "a")
    return g


def test_degrees_on_linear_chain():
    degrees = compute_degrees(linear_graph())
    assert degrees["a"] == {"inDegree": 0, "outDegree": 1}
    assert degrees["b"] == {"inDegree": 1, "outDegree": 1}
    assert degrees["c"] == {"inDegree": 1, "outDegree": 0}


def test_dependency_depth_on_linear_chain():
    depths = compute_dependency_depth(linear_graph())
    assert depths["a"] == 2  # a -> b -> c
    assert depths["b"] == 1  # b -> c
    assert depths["c"] == 0  # leaf


def test_dependency_depth_does_not_infinite_loop_on_cycle():
    # must terminate and return *some* finite depth, not hang or crash
    depths = compute_dependency_depth(cyclic_graph())
    assert all(isinstance(v, int) for v in depths.values())


def test_graph_metrics_totals_on_linear_chain():
    metrics = compute_graph_metrics(linear_graph())
    assert metrics["fileCount"] == 3
    assert metrics["edgeCount"] == 2
    assert metrics["connectedComponentCount"] == 1
    assert metrics["largestComponentSize"] == 3
    assert metrics["avgDependencies"] == round(2 / 3, 2)
    assert metrics["betweennessSkipped"] is False


def test_disconnected_components_counted_separately():
    g = nx.DiGraph()
    g.add_edge("a", "b")
    g.add_node("isolated")
    metrics = compute_graph_metrics(g)
    assert metrics["connectedComponentCount"] == 2


def test_betweenness_skipped_flag_respects_node_limit(monkeypatch):
    import graph.metrics as metrics_module

    monkeypatch.setattr(metrics_module, "BETWEENNESS_NODE_LIMIT", 1)
    metrics = compute_graph_metrics(linear_graph())  # 3 nodes > limit of 1
    assert metrics["betweennessSkipped"] is True
    for node_metrics in metrics["perNode"].values():
        assert node_metrics["betweennessCentrality"] is None
