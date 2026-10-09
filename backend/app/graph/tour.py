"""
Deterministic "guided tour": a suggested reading order through a codebase,
computed entirely from graph structure - no AI, no network call, no API key.
This is the mandated first layer of Phase G: it must work and be useful on
its own, because the AI layer (analyzer/ai_tour.py) is allowed to be
unavailable, rate limited, or wrong.

Two modes, because people learn a codebase two different ways:

  trace (default) - top-down. Start at the entry points (files nothing else
      imports, e.g. main.jsx) and walk down what they import, breadth-first:
      main -> App -> Dashboard -> its components. This is how most people
      actually onboard, and on a small app it IS the whole story.
  foundation - bottom-up. The most relied-upon files first, ordered
      utilities-before-what-uses-them. Better on a big library with a
      shared core (Flask: app.py, ctx.py, wrappers.py).

Lessons baked in from running this on real repos, each with a regression test:
  * Selection must rank by importance, not depth: depth-first filled all 12
    slots with trivial leaf files on Flask.
  * Ranking by "how many files import me" alone misses the best explainer
    on a small app - the hub that imports many files (Dashboard.jsx, 8
    imports, was buried at stop 10). Importance counts both directions.
  * Stages are named by ROLE, not by depth cutoffs: a depth-ratio threshold
    labelled that same hub "Foundation".
  * Stylesheets, config files and tests are not worth touring.
  * Eight identical sibling components are one stop, not eight.
  * Files with no import connections at all (e.g. a Python backend that
    talks to a React frontend over HTTP) can't be placed in a dependency
    order, so they're left out and the response says so.
"""

from __future__ import annotations

import math
import os
import re
from collections import deque

import networkx as nx

MAX_STOPS = 12
GROUP_MIN = 3          # this many unvisited leaf children collapse into one stop
MAX_TRACE_ROOTS = 3    # entry points followed in trace mode
HUB_MIN_OUT = 3        # imports at least this many files => "Orchestrator"

STAGE_ENTRY = "Entry points"
STAGE_HUB = "Orchestrators"
STAGE_CORE = "Core logic"
STAGE_LEAF = "Building blocks"

CODE_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".py"}
# Directories whose files illustrate or support a project rather than being
# it. Found on Flask/Express: their examples/ apps are the only files nothing
# imports, so a trace "from the entry points" started in demo code and never
# reached the library itself.
NOISE_DIRS = {"examples", "example", "docs", "doc", "demo", "demos", "sample", "samples",
              "benchmarks", "benchmark", "fixtures", "e2e", "scripts",
              "test", "tests", "__tests__", "spec", "specs"}
_NOISE_NAME = re.compile(r"(^|/)([^/]*\.config\.(js|cjs|mjs|ts)|conftest\.py|setupTests\.(js|ts))$")


def _basename(path: str) -> str:
    return path.replace("\\", "/").rsplit("/", 1)[-1]


def _eligible_nodes(graph, architecture, file_paths, relaxed=False) -> list[str]:
    out = []
    for n in graph.nodes:
        path = file_paths[n]
        if os.path.splitext(path)[1].lower() not in CODE_EXTENSIONS:
            continue
        norm = path.replace("\\", "/")
        if not relaxed and (
            _NOISE_NAME.search(norm)
            or architecture.get(n) == "Test"
            or any(part.lower() in NOISE_DIRS for part in norm.split("/")[:-1])
        ):
            continue
        out.append(n)
    return out


def _role(sub, n) -> str:
    i, o = sub.in_degree(n), sub.out_degree(n)
    if i == 0 and o > 0:
        return STAGE_ENTRY
    if o == 0:
        return STAGE_LEAF
    if o >= HUB_MIN_OUT and o > i:  # wires others together more than it is wired into
        return STAGE_HUB
    return STAGE_CORE


def _reasons(n, sub, architecture, in_cycle_set, role, parent_path=None) -> list[str]:
    i, o = sub.in_degree(n), sub.out_degree(n)
    reasons = []
    if parent_path:
        reasons.append(f"Imported by {_basename(parent_path)}")
    if role == STAGE_ENTRY:
        reasons.append("Nothing else in this project imports it - likely where execution starts")
    if role == STAGE_HUB:
        reasons.append(f"Imports {o} files - it wires them together")
    if i > 1 or (i == 1 and not parent_path):
        noun, verb = ("file", "depends") if i == 1 else ("files", "depend")
        reasons.append(f"{i} other {noun} {verb} on this")
    category = architecture.get(n)
    if category and category != "Unknown":
        reasons.append(f"Classified as {category}")
    if n in in_cycle_set:
        reasons.append("Part of a circular dependency - worth understanding the tangle")
    return reasons


def generate_tour(
    graph,
    per_node_metrics: dict,
    architecture: dict,
    in_cycle_set: set[str],
    file_paths: dict[str, str] | None = None,
    mode: str = "trace",
    max_stops: int = MAX_STOPS,
) -> dict:
    """
    Returns {"stops": [...], "note": str | None}. Each stop is
        {"fileId", "filePath", "stage", "reasons", "members": [...]}
    where `members` is non-empty only for a collapsed group of sibling files.

    Pure function of already-computed graph data: no I/O, and the same input
    always gives the same output (every sort has a path tie-break), which is
    what lets results be cached forever once a project is immutable.
    """
    if file_paths is None:
        file_paths = {n: graph.nodes[n]["filePath"] for n in graph.nodes}

    nodes = _eligible_nodes(graph, architecture, file_paths)
    if not nodes:  # e.g. a repo that is only tests: better a tour of those than nothing
        nodes = _eligible_nodes(graph, architecture, file_paths, relaxed=True)
    if not nodes:
        return {"stops": [], "note": None}

    sub = graph.subgraph(nodes)
    connected = [n for n in nodes if sub.in_degree(n) + sub.out_degree(n) > 0]
    isolated_count = len(nodes) - len(connected)

    if not connected:
        return {
            "stops": [],
            "note": "No import connections were found between these files, so there is no "
                    "dependency order to tour.",
        }

    def importance(n):
        # both directions: relied-upon files AND the hubs that wire others together
        return (-(sub.in_degree(n) + sub.out_degree(n)),
                -per_node_metrics[n]["degreeCentrality"], file_paths[n])

    def file_stop(n, parent=None):
        role = _role(sub, n)
        return {
            "fileId": n, "filePath": file_paths[n], "stage": role,
            "reasons": _reasons(n, sub, architecture, in_cycle_set, role,
                                file_paths[parent] if parent else None),
            "members": [],
        }

    if mode == "foundation":
        picked = sorted(connected, key=importance)[:max_stops]
        picked.sort(key=lambda n: (per_node_metrics[n]["dependencyDepth"], *importance(n)))
        stops = [file_stop(n) for n in picked]
    else:
        stops = _trace(sub, connected, file_paths, importance, file_stop, max_stops)

    note = None
    if isolated_count:
        noun = "file has" if isolated_count == 1 else "files have"
        note = (f"{isolated_count} other {noun} no import connections to the rest of the project "
                f"(for example code that talks to the rest over HTTP), so can't be placed in this tour.")
    return {"stops": stops, "note": note}


def _trace(sub, connected, file_paths, importance, file_stop, max_stops) -> list[dict]:
    entries = [n for n in connected if _role(sub, n) == STAGE_ENTRY]
    reach = {n: len(nx.descendants(sub, n)) for n in entries}
    entries.sort(key=lambda n: (-reach[n], -sub.out_degree(n), file_paths[n]))
    roots = entries[:MAX_TRACE_ROOTS]
    if not roots:  # everything sits in a cycle: start from the busiest file instead
        roots = [min(connected, key=importance)]

    stops: list[dict] = []
    visited: set[str] = set()

    def walk(root, budget):
        used = 0
        queue = deque([(root, None)])
        while queue and used < budget and len(stops) < max_stops:
            n, parent = queue.popleft()
            if n in visited:
                continue
            visited.add(n)
            stops.append(file_stop(n, parent))
            used += 1
            children = [c for c in sorted(sub.successors(n), key=lambda c: file_paths[c])
                        if c not in visited and c != n]
            leaves = [c for c in children if sub.out_degree(c) == 0]
            grouped = False
            if len(leaves) >= GROUP_MIN and used < budget and len(stops) < max_stops:
                visited.update(leaves)
                stops.append({
                    "fileId": leaves[0],
                    "filePath": f"{len(leaves)} files used by {_basename(file_paths[n])}",
                    "stage": STAGE_LEAF,
                    "reasons": ["Leaf files - none of them import anything else in this project"],
                    "members": [{"fileId": c, "filePath": file_paths[c]} for c in leaves],
                })
                used += 1
                grouped = True
            for c in children:
                if not (grouped and c in visited):
                    queue.append((c, n))

    for i, root in enumerate(roots):
        if root in visited:
            continue
        left = max_stops - len(stops)
        if left <= 0:
            break
        roots_left = len(roots) - i
        walk(root, left if roots_left == 1 else max(3, math.ceil(left / roots_left)))

    if len(stops) < max_stops:  # top up with the busiest unvisited connected files
        rest = sorted((n for n in connected if n not in visited), key=importance)
        for n in rest[: max_stops - len(stops)]:
            visited.add(n)
            stops.append(file_stop(n))
    return stops


def generate_deterministic_tour(graph, per_node_metrics, architecture, in_cycle_set,
                                file_paths=None, mode="trace", max_stops=MAX_STOPS) -> list[dict]:
    """Stops only (see generate_tour for the note about omitted files)."""
    return generate_tour(graph, per_node_metrics, architecture, in_cycle_set,
                         file_paths, mode, max_stops)["stops"]
