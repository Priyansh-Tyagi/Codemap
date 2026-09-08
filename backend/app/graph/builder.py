"""
Graph builder.

Runs the full Day 1/2 pipeline (scan -> parse -> classify -> resolve) and
assembles the results into a NetworkX DiGraph:

    node  = a source file, identified by its path relative to the project root
             (forward slashes, so ids are consistent across OSes)
    edge  = A -> B meaning "A imports B"

Also returns side information the pipeline produced along the way (external
dependency counts, unresolved imports) since callers need those for stats
even though they never became graph edges.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import networkx as nx

from analyzer.scanner import scan_repository
from analyzer.parser_bridge import parse_files
from analyzer.classifier import classify_imports
from analyzer.resolver import resolve_specifier


def _to_node_id(absolute_path: str, root: str) -> str:
    """Relative path from project root, forward-slash separated."""
    rel = os.path.relpath(absolute_path, root)
    return rel.replace(os.sep, "/")


@dataclass
class BuildResult:
    graph: nx.DiGraph
    root: str
    unresolved_imports: list[dict] = field(default_factory=list)
    external_dependencies: dict[str, int] = field(default_factory=dict)
    parse_errors: list[dict] = field(default_factory=list)


def build_dependency_graph(root_path: str) -> BuildResult:
    """
    Full pipeline: scan repo -> parse files -> classify imports ->
    resolve local specifiers -> build directed graph.

    Raises whatever scan_repository raises (FileNotFoundError, NotADirectoryError)
    if root_path is invalid - callers (the API layer) are expected to turn
    those into proper HTTP error responses.
    """
    root = os.path.abspath(root_path)
    scan_result = scan_repository(root)
    parsed_files = parse_files(scan_result.files)

    graph = nx.DiGraph()
    unresolved_imports: list[dict] = []
    external_dependencies: dict[str, int] = {}
    parse_errors: list[dict] = []

    # First pass: add every scanned file as a node, even ones with zero
    # edges, so isolated files still show up in the graph/stats.
    for file_result in parsed_files:
        node_id = _to_node_id(file_result["filePath"], root)
        graph.add_node(
            node_id,
            filePath=node_id,
            name=os.path.basename(node_id),
            linesOfCode=file_result.get("linesOfCode", 0),
        )
        if file_result.get("error"):
            parse_errors.append({"file": node_id, "error": file_result["error"]})

    # Second pass: classify + resolve imports into edges.
    for file_result in parsed_files:
        source_id = _to_node_id(file_result["filePath"], root)
        local_imports, external_imports = classify_imports(file_result.get("imports", []))

        for imp in external_imports:
            spec = imp["specifier"]
            external_dependencies[spec] = external_dependencies.get(spec, 0) + 1

        for imp in local_imports:
            resolved = resolve_specifier(file_result["filePath"], imp["specifier"], root)
            if resolved is None:
                unresolved_imports.append(
                    {
                        "file": source_id,
                        "specifier": imp["specifier"],
                        "type": imp["type"],
                    }
                )
                continue

            target_id = _to_node_id(resolved, root)
            if target_id not in graph:
                # Resolved to a file the scanner didn't pick up (e.g. wrong
                # extension config) - add it defensively so the edge is valid.
                graph.add_node(target_id, filePath=target_id, name=os.path.basename(target_id), linesOfCode=0)

            symbols = imp.get("symbols", [])
            if graph.has_edge(source_id, target_id):
                # Same file imported more than once (e.g. two separate import
                # statements, or an import plus a require of the same
                # target): merge symbols instead of dropping the second
                # statement's data entirely. Order preserved, no duplicates.
                existing = graph.edges[source_id, target_id].get("symbols", [])
                merged = existing + [s for s in symbols if s not in existing]
                graph.edges[source_id, target_id]["symbols"] = merged
                continue
            graph.add_edge(source_id, target_id, type=imp["type"], symbols=symbols)

    return BuildResult(
        graph=graph,
        root=root,
        unresolved_imports=unresolved_imports,
        external_dependencies=external_dependencies,
        parse_errors=parse_errors,
    )
