"""
Graph builder.

Runs the full scan -> parse -> classify -> resolve pipeline for BOTH
supported languages and assembles the results into one NetworkX DiGraph:

    node  = a source file, identified by its path relative to the project root
             (forward slashes, so ids are consistent across OSes)
    edge  = A -> B meaning "A imports B"

JS/TS and Python files are parsed and resolved through entirely separate
pipelines (different parser, different resolver - Python's import system
genuinely isn't "JS with different syntax"), then merged into the same
graph. Node ids are always relative file paths WITH extension, so a
".py" file and a ".js" file can never collide, and each language's
resolver only ever looks for files with its own extensions - so there is
no mechanism by which a Python import could resolve to a JS file or vice
versa. See test_graph_builder.py's cross-language test for a concrete
proof of that, not just an assertion in a comment.

Also returns side information the pipeline produced along the way (external
dependency counts, unresolved imports) since callers need those for stats
even though they never became graph edges.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import networkx as nx

from analyzer.scanner import scan_repository, PYTHON_EXTENSIONS
from analyzer.parser_bridge import parse_files
from analyzer.classifier import classify_imports
from analyzer.resolver import resolve_specifier
from analyzer.python_parser import parse_python_files
from analyzer.python_resolver import resolve_python_import, ResolutionKind


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


def _add_node_if_missing(graph: nx.DiGraph, node_id: str, language: str, lines_of_code: int = 0) -> None:
    if node_id not in graph:
        graph.add_node(
            node_id,
            filePath=node_id,
            name=os.path.basename(node_id),
            linesOfCode=lines_of_code,
            language=language,
        )


def _add_or_merge_edge(graph: nx.DiGraph, source_id: str, target_id: str, edge_type: str, symbols: list[str]) -> None:
    """
    Shared by both language pipelines so the "same file imported twice"
    merge behavior can't drift between them the way it nearly did when
    only the JS path had this logic (see graph_builder tests for the
    regression this guards against).
    """
    if graph.has_edge(source_id, target_id):
        existing = graph.edges[source_id, target_id].get("symbols", [])
        merged = existing + [s for s in symbols if s not in existing]
        graph.edges[source_id, target_id]["symbols"] = merged
        return
    graph.add_edge(source_id, target_id, type=edge_type, symbols=symbols)


def _process_js_files(graph, parsed_files, root, external_dependencies, unresolved_imports, parse_errors):
    for file_result in parsed_files:
        node_id = _to_node_id(file_result["filePath"], root)
        _add_node_if_missing(graph, node_id, "javascript", file_result.get("linesOfCode", 0))
        if file_result.get("error"):
            parse_errors.append({"file": node_id, "error": file_result["error"]})

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
                    {"file": source_id, "specifier": imp["specifier"], "type": imp["type"]}
                )
                continue

            target_id = _to_node_id(resolved, root)
            _add_node_if_missing(graph, target_id, "javascript")
            _add_or_merge_edge(graph, source_id, target_id, imp["type"], imp.get("symbols", []))


def _process_python_files(graph, parsed_files, root, external_dependencies, unresolved_imports, parse_errors):
    for file_result in parsed_files:
        node_id = _to_node_id(file_result["filePath"], root)
        _add_node_if_missing(graph, node_id, "python", file_result.get("linesOfCode", 0))
        if file_result.get("error"):
            parse_errors.append({"file": node_id, "error": file_result["error"]})

    for file_result in parsed_files:
        source_id = _to_node_id(file_result["filePath"], root)

        for imp in file_result.get("imports", []):
            resolved, kind = resolve_python_import(
                file_result["filePath"], imp["module_path"], imp["level"], root
            )

            if kind == ResolutionKind.EXTERNAL:
                external_dependencies[imp["module_path"]] = (
                    external_dependencies.get(imp["module_path"], 0) + 1
                )
                continue

            if kind == ResolutionKind.UNRESOLVED:
                unresolved_imports.append(
                    {"file": source_id, "specifier": imp["module_path"], "type": "import"}
                )
                continue

            target_id = _to_node_id(resolved, root)
            _add_node_if_missing(graph, target_id, "python")
            _add_or_merge_edge(graph, source_id, target_id, "import", imp.get("symbols", []))


def build_dependency_graph(root_path: str) -> BuildResult:
    """
    Full pipeline: scan repo -> parse files (per-language) -> classify ->
    resolve -> build one directed graph covering every supported language.

    Raises whatever scan_repository raises (FileNotFoundError, NotADirectoryError)
    if root_path is invalid - callers (the API layer) are expected to turn
    those into proper HTTP error responses.
    """
    root = os.path.abspath(root_path)
    scan_result = scan_repository(root)

    py_files = [f for f in scan_result.files if os.path.splitext(f)[1] in PYTHON_EXTENSIONS]
    js_files = [f for f in scan_result.files if f not in py_files]

    parsed_js = parse_files(js_files) if js_files else []
    parsed_py = parse_python_files(py_files) if py_files else []

    graph = nx.DiGraph()
    unresolved_imports: list[dict] = []
    external_dependencies: dict[str, int] = {}
    parse_errors: list[dict] = []

    _process_js_files(graph, parsed_js, root, external_dependencies, unresolved_imports, parse_errors)
    _process_python_files(graph, parsed_py, root, external_dependencies, unresolved_imports, parse_errors)

    return BuildResult(
        graph=graph,
        root=root,
        unresolved_imports=unresolved_imports,
        external_dependencies=external_dependencies,
        parse_errors=parse_errors,
    )
