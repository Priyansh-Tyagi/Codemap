"""
Graph metrics.

Computes per-node and per-graph statistics used by the dashboard and by
risk scoring (Day 6). Kept deliberately cheap: betweenness centrality is
skipped above BETWEENNESS_NODE_LIMIT nodes, per the Phase 1 performance
requirement (don't blindly calculate expensive metrics for huge repos).
"""

from __future__ import annotations

import networkx as nx

BETWEENNESS_NODE_LIMIT = 1500


def compute_degrees(graph: nx.DiGraph) -> dict[str, dict[str, int]]:
    """Per-node {"inDegree": x, "outDegree": y}."""
    return {
        node: {"inDegree": graph.in_degree(node), "outDegree": graph.out_degree(node)}
        for node in graph.nodes
    }


def compute_dependency_depth(graph: nx.DiGraph) -> dict[str, int]:
    """
    For each node, the length of its longest outgoing dependency chain
    (how many "hops" its deepest transitive dependency is).

    Cycle-safe: DFS tracks the current path; if a node reappears in that
    path we stop descending there instead of recursing forever, since the
    cycle itself is already reported separately by cycles.py.
    """
    depth_cache: dict[str, int] = {}

    def dfs(node: str, path: set[str]) -> int:
        if node in depth_cache:
            return depth_cache[node]
        if node in path:
            return 0  # hit a cycle in the current path; don't recurse further here

        path = path | {node}
        max_child_depth = 0
        for neighbor in graph.successors(node):
            child_depth = dfs(neighbor, path)
            max_child_depth = max(max_child_depth, child_depth + 1)

        depth_cache[node] = max_child_depth
        return max_child_depth

    return {node: dfs(node, set()) for node in graph.nodes}


def compute_centrality(graph: nx.DiGraph) -> dict[str, dict[str, float | None]]:
    """
    Per-node {"degreeCentrality": float, "betweennessCentrality": float|None}.
    Betweenness is None (skipped) above BETWEENNESS_NODE_LIMIT nodes.
    """
    degree_centrality = nx.degree_centrality(graph)

    if graph.number_of_nodes() <= BETWEENNESS_NODE_LIMIT:
        betweenness = nx.betweenness_centrality(graph)
    else:
        betweenness = {node: None for node in graph.nodes}

    return {
        node: {
            "degreeCentrality": degree_centrality.get(node, 0.0),
            "betweennessCentrality": betweenness.get(node),
        }
        for node in graph.nodes
    }


def compute_connected_components(graph: nx.DiGraph) -> list[list[str]]:
    """
    Weakly connected components (ignoring edge direction) - i.e. clusters
    of files that are related to each other but disconnected from the rest
    of the codebase. Returned as a list of node-id lists, largest first.
    """
    components = [list(c) for c in nx.weakly_connected_components(graph)]
    components.sort(key=len, reverse=True)
    return components


def compute_graph_metrics(graph: nx.DiGraph) -> dict:
    """Aggregate: everything above, merged per-node, plus a few graph-level totals."""
    degrees = compute_degrees(graph)
    depths = compute_dependency_depth(graph)
    centrality = compute_centrality(graph)
    components = compute_connected_components(graph)

    per_node = {}
    for node in graph.nodes:
        per_node[node] = {
            **degrees[node],
            "dependencyDepth": depths[node],
            **centrality[node],
        }

    avg_dependencies = (
        sum(d["outDegree"] for d in degrees.values()) / len(degrees) if degrees else 0
    )

    return {
        "perNode": per_node,
        "fileCount": graph.number_of_nodes(),
        "edgeCount": graph.number_of_edges(),
        "connectedComponentCount": len(components),
        "largestComponentSize": len(components[0]) if components else 0,
        "avgDependencies": round(avg_dependencies, 2),
        "betweennessSkipped": graph.number_of_nodes() > BETWEENNESS_NODE_LIMIT,
    }
