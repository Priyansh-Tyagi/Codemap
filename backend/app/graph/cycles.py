"""
Circular dependency detection.

Wraps networkx.simple_cycles, which finds every elementary cycle in a
directed graph, and shapes the result the way the API/UI needs it: a stable
id per cycle plus the file chain in order (with the first node repeated at
the end, matching the "A -> B -> C -> A" display format from the spec).
"""

from __future__ import annotations

import networkx as nx


def detect_cycles(graph: nx.DiGraph) -> list[dict]:
    """
    Returns a list of:
        {"id": "cycle-0", "chain": ["auth.js", "user.js", "database.js", "auth.js"]}

    Cycles are found on the graph as-is; if it's large and densely connected,
    simple_cycles can be expensive (cycle count can be combinatorially large
    in the worst case). For MVP-scale repos this is fine; documented as a
    known scaling limit rather than optimized away.
    """
    cycles = []
    for i, cycle_nodes in enumerate(nx.simple_cycles(graph)):
        chain = list(cycle_nodes) + [cycle_nodes[0]]
        cycles.append({"id": f"cycle-{i}", "chain": chain})
    return cycles


def nodes_in_cycles(cycles: list[dict]) -> set[str]:
    """Flat set of every node id that participates in at least one cycle."""
    in_cycle = set()
    for cycle in cycles:
        # chain includes the repeated closing node; every entry except
        # the trailing duplicate is a distinct participant.
        in_cycle.update(cycle["chain"][:-1])
    return in_cycle
