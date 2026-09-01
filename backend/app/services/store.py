"""
In-memory project store.

Holds analyzed projects keyed by project_id so repeated API calls (get
graph, get file detail, run impact analysis) don't re-run the whole
scan/parse/resolve/graph-build pipeline every time.

MVP-appropriate limitation, documented rather than hidden: this is a plain
module-level dict. It resets whenever the server restarts, and isn't safe
for multiple worker processes (fine for `uvicorn` running a single process
locally, which is the target deployment for this project). A real product
would use Redis or a DB-backed cache instead.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

import networkx as nx

from graph.builder import BuildResult
from graph.cycles import detect_cycles, nodes_in_cycles
from graph.metrics import compute_graph_metrics
from graph.risk import compute_risk
from analyzer.architecture import classify_architecture


@dataclass
class ProjectRecord:
    project_id: str
    root: str
    graph: nx.DiGraph
    cycles: list[dict]
    nodes_in_cycles: set[str]
    metrics: dict
    external_dependencies: dict[str, int]
    unresolved_imports: list[dict]
    parse_errors: list[dict]
    architecture: dict[str, str] = field(default_factory=dict)  # node_id -> category
    risk: dict[str, dict] = field(default_factory=dict)          # node_id -> {score, level, reasons}
    source_type: str = "local"   # "local" | "github"
    source_label: str = ""       # local abs path, or "owner/repo@ref" for GitHub
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


_store: dict[str, ProjectRecord] = {}


def create_project(
    build_result: BuildResult,
    source_type: str = "local",
    source_label: str | None = None,
) -> ProjectRecord:
    """Runs cycle detection + metrics once, then caches everything under a new id."""
    graph = build_result.graph
    cycles = detect_cycles(graph)
    in_cycle_set = nodes_in_cycles(cycles)
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

    record = ProjectRecord(
        project_id=str(uuid.uuid4()),
        root=build_result.root,
        graph=graph,
        cycles=cycles,
        nodes_in_cycles=in_cycle_set,
        metrics=metrics,
        external_dependencies=build_result.external_dependencies,
        unresolved_imports=build_result.unresolved_imports,
        parse_errors=build_result.parse_errors,
        architecture=architecture,
        risk=risk,
        source_type=source_type,
        source_label=source_label or build_result.root,
    )
    _store[record.project_id] = record
    return record


def get_project(project_id: str) -> ProjectRecord | None:
    return _store.get(project_id)


def clear_all() -> None:
    """Used by tests to avoid state leaking between test cases."""
    _store.clear()
