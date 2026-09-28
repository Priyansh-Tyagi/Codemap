"""
Circular dependency detection.

Two views of the same fact, deliberately kept separate:

1. cyclic_components(): strongly connected components with a cycle in them.
   Linear time, exact, and unaffected by graph density. This is the source of
   truth for "is this file in a cycle?" (drives risk scoring and node badges).

2. detect_cycles(): the *listed* elementary cycles ("A -> B -> C -> A") shown
   to the user. The number of elementary cycles can grow combinatorially with
   a tightly-knit cluster (Flask's 19-file core produces 9,629 of them), which
   is both unreadable and an unbounded-cost enumeration. So listing is capped
   at MAX_CYCLES; when the cap is hit, the shortest cycles are kept (they're
   the most actionable) and the result is flagged as truncated.
"""

from __future__ import annotations

from itertools import islice

import networkx as nx

MAX_CYCLES = 200
SHORT_CYCLE_LENGTH = 6   # when truncating, prefer cycles up to this many files long
SAMPLE_LIMIT = 20_000    # hard ceiling on cycles examined per pass (bounds worst-case cost)


def _shape(cycles_nodes) -> list[dict]:
    out = []
    for i, cycle_nodes in enumerate(cycles_nodes):
        out.append({"id": f"cycle-{i}", "chain": list(cycle_nodes) + [cycle_nodes[0]]})
    return out


def _canonical(cycle: list[int]) -> tuple[int, ...]:
    """Rotate so the smallest id comes first: same cycle, one representation."""
    i = cycle.index(min(cycle))
    return tuple(cycle[i:] + cycle[:i])


def _shortest_cycles(graph: nx.DiGraph, fallback: list[list[str]]) -> list[list[str]]:
    """
    Picks up to MAX_CYCLES cycles, shortest first, deterministically.

    Nodes are relabelled to integers in sorted order first: integer hashing is
    stable, so the search (which uses sets internally) visits nodes in the same
    order on every run - string hashing is randomized per process, which would
    make the chosen subset differ between server restarts.

    The length bound is raised one step at a time and stops as soon as enough
    cycles exist, so the kept cycles are the shortest available. Each pass
    examines at most SAMPLE_LIMIT cycles, bounding worst-case cost; on a truly
    pathological graph "shortest" is therefore shortest among those examined.
    """
    names = sorted(graph.nodes)
    ids = {name: i for i, name in enumerate(names)}
    h = nx.DiGraph()
    h.add_nodes_from(range(len(names)))
    h.add_edges_from(sorted((ids[u], ids[v]) for u, v in graph.edges))

    sample: list[tuple[int, ...]] = []
    for bound in range(1, SHORT_CYCLE_LENGTH + 1):
        sample = [
            _canonical(c)
            for c in islice(nx.simple_cycles(h, length_bound=bound), SAMPLE_LIMIT)
        ]
        if len(sample) >= MAX_CYCLES:
            break

    if len(sample) < MAX_CYCLES:
        # Few short cycles but many long ones: top up from the unbounded search.
        seen = set(sample)
        for cycle_names in fallback:
            canon = _canonical([ids[n] for n in cycle_names])
            if canon not in seen:
                seen.add(canon)
                sample.append(canon)
            if len(sample) >= MAX_CYCLES:
                break

    sample = sorted(set(sample), key=lambda c: (len(c), c))[:MAX_CYCLES]
    return [[names[i] for i in c] for c in sample]


def detect_cycles_capped(graph: nx.DiGraph) -> tuple[list[dict], bool]:
    """
    Returns (cycles, truncated). Each cycle is
        {"id": "cycle-0", "chain": ["auth.js", "user.js", "database.js", "auth.js"]}

    Below the cap, behavior is plain enumeration (generation order preserved).
    At the cap, enumeration stops early (bounded cost) and the kept set is the
    shortest cycles, sorted shortest-first, deterministically.
    """
    found = list(islice(nx.simple_cycles(graph), MAX_CYCLES + 1))
    if len(found) <= MAX_CYCLES:
        return _shape(found), False
    return _shape(_shortest_cycles(graph, found)), True


def detect_cycles(graph: nx.DiGraph) -> list[dict]:
    """Capped list of elementary cycles (see detect_cycles_capped)."""
    return detect_cycles_capped(graph)[0]


def cyclic_components(graph: nx.DiGraph) -> list[list[str]]:
    """
    Node groups that are mutually reachable (every file in a group can reach
    every other through imports). Only groups that actually contain a cycle
    are returned, largest first, each sorted for stable output.
    """
    components = []
    for comp in nx.strongly_connected_components(graph):
        if len(comp) > 1 or any(graph.has_edge(n, n) for n in comp):
            components.append(sorted(comp))
    components.sort(key=lambda c: (-len(c), c))
    return components


def nodes_in_cycles(cycles: list[dict]) -> set[str]:
    """Flat set of every node id that participates in at least one listed cycle."""
    in_cycle = set()
    for cycle in cycles:
        # chain includes the repeated closing node; every entry except
        # the trailing duplicate is a distinct participant.
        in_cycle.update(cycle["chain"][:-1])
    return in_cycle
