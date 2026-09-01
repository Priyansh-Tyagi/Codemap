import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import networkx as nx
from graph.cycles import detect_cycles, nodes_in_cycles


def test_detects_simple_three_node_cycle():
    g = nx.DiGraph()
    g.add_edge("a", "b")
    g.add_edge("b", "c")
    g.add_edge("c", "a")

    cycles = detect_cycles(g)
    assert len(cycles) == 1
    chain = cycles[0]["chain"]
    assert chain[0] == chain[-1]  # closes the loop
    assert set(chain[:-1]) == {"a", "b", "c"}


def test_no_cycle_in_linear_graph():
    g = nx.DiGraph()
    g.add_edge("a", "b")
    g.add_edge("b", "c")
    assert detect_cycles(g) == []


def test_self_loop_is_a_cycle():
    g = nx.DiGraph()
    g.add_edge("a", "a")
    cycles = detect_cycles(g)
    assert len(cycles) == 1
    assert cycles[0]["chain"] == ["a", "a"]


def test_two_independent_cycles_both_found():
    g = nx.DiGraph()
    g.add_edge("a", "b")
    g.add_edge("b", "a")
    g.add_edge("x", "y")
    g.add_edge("y", "x")

    cycles = detect_cycles(g)
    assert len(cycles) == 2


def test_nodes_in_cycles_flattens_correctly():
    g = nx.DiGraph()
    g.add_edge("a", "b")
    g.add_edge("b", "a")
    g.add_edge("c", "d")  # not in a cycle

    cycles = detect_cycles(g)
    in_cycle = nodes_in_cycles(cycles)
    assert in_cycle == {"a", "b"}
    assert "c" not in in_cycle
    assert "d" not in in_cycle
