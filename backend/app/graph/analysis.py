"""
Shared analysis orchestration.

Runs cycle detection, metrics, architecture classification, and risk
scoring against an already-built graph, and returns everything as plain
data - no project_id, no storage, no HTTP concerns.

This exists specifically so the web API (services/store.py) and the CLI
(cli.py) call the EXACT same code for "what does analyzing this graph
produce" rather than each having their own copy that could quietly drift
out of sync with the other over time.
"""

from __future__ import annotations

import networkx as nx

from graph.cycles import detect_cycles_capped, cyclic_components
from graph.metrics import compute_graph_metrics
from graph.risk import compute_risk
from analyzer.architecture import classify_architecture


def run_full_analysis(graph: nx.DiGraph) -> dict:
    """
    Returns:
        {
            "cycles": [...],                      # capped list of elementary cycles
            "cycles_truncated": bool,              # True if more cycles exist than listed
            "cycle_components": [[node_id, ...]],  # groups of mutually-dependent files
            "nodes_in_cycles": {...},              # set of node ids (exact, from components)
            "metrics": {...},                      # from compute_graph_metrics
            "architecture": {node_id: category},
            "risk": {node_id: {"score", "level", "reasons"}},
        }
    """
    cycles, cycles_truncated = detect_cycles_capped(graph)
    components = cyclic_components(graph)
    # Exact membership from components, NOT from the (possibly capped) cycle
    # list - a file must never lose its "in a cycle" flag/risk just because
    # the listing was truncated.
    in_cycle_set = {node_id for comp in components for node_id in comp}
    metrics = compute_graph_metrics(graph)

    architecture = {
        node_id: classify_architecture(graph.nodes[node_id]["filePath"])
        for node_id in graph.nodes
    }

    per_node_metrics = metrics["perNode"]
    risk = {
        node_id: compute_risk(
            in_degree=per_node_metrics[node_id]["inDegree"],
            degree_centrality=per_node_metrics[node_id]["degreeCentrality"],
            lines_of_code=graph.nodes[node_id].get("linesOfCode", 0),
            in_cycle=node_id in in_cycle_set,
        )
        for node_id in graph.nodes
    }

    return {
        "cycles": cycles,
        "cycles_truncated": cycles_truncated,
        "cycle_components": components,
        "nodes_in_cycles": in_cycle_set,
        "metrics": metrics,
        "architecture": architecture,
        "risk": risk,
    }
