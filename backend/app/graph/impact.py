"""
Change-impact analysis.

Given a file, answers "what breaks if I change this?" by traversing the
REVERSE dependency graph: if A imports B, then changing B might affect A.
So we walk backwards from the target node along in-edges.

Direct dependents = distance 1 in the reverse graph.
Indirect dependents = everything reachable at distance > 1.
"""

from __future__ import annotations

import networkx as nx


def analyze_impact(graph: nx.DiGraph, file_id: str) -> dict:
    """
    Raises KeyError if file_id isn't a node in the graph - callers (the API
    layer) are expected to turn that into a 404.
    """
    if file_id not in graph:
        raise KeyError(file_id)

    reverse = graph.reverse(copy=False)

    direct_dependents = sorted(reverse.successors(file_id))

    # BFS the reverse graph from file_id, excluding file_id itself and the
    # direct dependents (already captured above), to get everything further out.
    distances = nx.single_source_shortest_path_length(reverse, file_id)
    indirect_dependents = sorted(
        node
        for node, dist in distances.items()
        if dist > 1  # dist 0 = file_id itself, dist 1 = direct dependents
    )

    estimated_affected = len(direct_dependents) + len(indirect_dependents)

    return {
        "fileId": file_id,
        "directDependents": direct_dependents,
        "indirectDependents": indirect_dependents,
        "estimatedAffected": estimated_affected,
    }
