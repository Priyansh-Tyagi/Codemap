"""
SQLite-backed project store.

Same public functions as the earlier in-memory version (create_project,
get_project, get_cached_github_project_id, set_github_cache, clear_all),
so the API layer needed no changes when storage moved to disk.

Why SQLite and not Postgres/an ORM: this is a single-process deployment
with almost no concurrent writes, and each project is one row holding JSON
blobs. stdlib sqlite3 is enough; heavier tooling would add moving parts
without adding capability.

Where the file lives: CODEMAP_DB_PATH (env var), default ./codemap.db in
the process working directory. On a host with an ephemeral filesystem
(Render, Railway, Fly without a volume) that file is wiped on every
redeploy, taking every shareable link with it. Point CODEMAP_DB_PATH at a
mounted persistent disk in production (see README).

Lazy initialization: tables are created on first real connection, never at
import time. Creating them on import meant merely importing this module
(e.g. during a test run) silently created a real database file.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timezone

import networkx as nx

from graph.builder import BuildResult
from graph.analysis import run_full_analysis

# GitHub-only: local paths are never cached, because caching a path the
# user may be editing would silently serve stale results.
GITHUB_CACHE_TTL_SECONDS = 600  # 10 minutes

DEFAULT_DB_PATH = "codemap.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    project_id TEXT PRIMARY KEY,
    root TEXT NOT NULL,
    graph_json TEXT NOT NULL,
    cycles_json TEXT NOT NULL,
    nodes_in_cycles_json TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    external_dependencies_json TEXT NOT NULL,
    unresolved_imports_json TEXT NOT NULL,
    parse_errors_json TEXT NOT NULL,
    architecture_json TEXT NOT NULL,
    risk_json TEXT NOT NULL,
    cycle_info_json TEXT NOT NULL DEFAULT '{}',
    source_type TEXT NOT NULL,
    source_label TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS github_cache (
    cache_key TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    cached_at REAL NOT NULL
);
"""


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
    architecture: dict[str, str] = field(default_factory=dict)
    risk: dict[str, dict] = field(default_factory=dict)
    cycles_truncated: bool = False               # more cycles exist than are listed
    cycle_components: list[list[str]] = field(default_factory=list)
    source_type: str = "local"
    source_label: str = ""
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# Tracks which DB path has had CREATE TABLE run against it in this process.
_initialized_path: str | None = None


def _db_path() -> str:
    return os.environ.get("CODEMAP_DB_PATH", DEFAULT_DB_PATH)


def _connect() -> sqlite3.Connection:
    global _initialized_path
    path = _db_path()
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    if _initialized_path != path:
        conn.executescript(_SCHEMA)
        conn.commit()
        _initialized_path = path
    return conn


def _serialize_graph(graph: nx.DiGraph) -> str:
    # edges="links" pins the key name so behavior doesn't vary by networkx version
    return json.dumps(nx.node_link_data(graph, edges="links"))


def _deserialize_graph(text: str) -> nx.DiGraph:
    return nx.node_link_graph(json.loads(text), edges="links", directed=True)


def create_project(
    build_result: BuildResult,
    source_type: str = "local",
    source_label: str | None = None,
) -> ProjectRecord:
    """Runs the shared analysis once, then persists everything under a new id."""
    graph = build_result.graph
    analysis = run_full_analysis(graph)

    record = ProjectRecord(
        project_id=str(uuid.uuid4()),
        root=build_result.root,
        graph=graph,
        cycles=analysis["cycles"],
        nodes_in_cycles=analysis["nodes_in_cycles"],
        metrics=analysis["metrics"],
        external_dependencies=build_result.external_dependencies,
        unresolved_imports=build_result.unresolved_imports,
        parse_errors=build_result.parse_errors,
        architecture=analysis["architecture"],
        risk=analysis["risk"],
        cycles_truncated=analysis["cycles_truncated"],
        cycle_components=analysis["cycle_components"],
        source_type=source_type,
        source_label=source_label or build_result.root,
    )

    with closing(_connect()) as conn:
        with conn:  # commits on success, rolls back on error
            conn.execute(
                "INSERT INTO projects (project_id, root, graph_json, cycles_json,"
                " nodes_in_cycles_json, metrics_json, external_dependencies_json,"
                " unresolved_imports_json, parse_errors_json, architecture_json,"
                " risk_json, cycle_info_json, source_type, source_label, created_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    record.project_id,
                    record.root,
                    _serialize_graph(record.graph),
                    json.dumps(record.cycles),
                    json.dumps(sorted(record.nodes_in_cycles)),
                    json.dumps(record.metrics),
                    json.dumps(record.external_dependencies),
                    json.dumps(record.unresolved_imports),
                    json.dumps(record.parse_errors),
                    json.dumps(record.architecture),
                    json.dumps(record.risk),
                    json.dumps({
                        "truncated": record.cycles_truncated,
                        "components": record.cycle_components,
                    }),
                    record.source_type,
                    record.source_label,
                    record.created_at,
                ),
            )
    return record


def get_project(project_id: str) -> ProjectRecord | None:
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT project_id, root, graph_json, cycles_json, nodes_in_cycles_json,"
            " metrics_json, external_dependencies_json, unresolved_imports_json,"
            " parse_errors_json, architecture_json, risk_json, cycle_info_json,"
            " source_type, source_label, created_at FROM projects WHERE project_id = ?",
            (project_id,),
        ).fetchone()
    if row is None:
        return None
    cycle_info = json.loads(row[11])
    return ProjectRecord(
        project_id=row[0],
        root=row[1],
        graph=_deserialize_graph(row[2]),
        cycles=json.loads(row[3]),
        nodes_in_cycles=set(json.loads(row[4])),
        metrics=json.loads(row[5]),
        external_dependencies=json.loads(row[6]),
        unresolved_imports=json.loads(row[7]),
        parse_errors=json.loads(row[8]),
        architecture=json.loads(row[9]),
        risk=json.loads(row[10]),
        cycles_truncated=cycle_info.get("truncated", False),
        cycle_components=cycle_info.get("components", []),
        source_type=row[12],
        source_label=row[13],
        created_at=row[14],
    )


def get_cached_github_project_id(cache_key: str) -> str | None:
    """Still-valid cached project_id for this key, else None (expired or
    dangling entries are deleted as a side effect)."""
    with closing(_connect()) as conn:
        with conn:
            row = conn.execute(
                "SELECT project_id, cached_at FROM github_cache WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()
            if row is None:
                return None
            project_id, cached_at = row
            expired = time.time() - cached_at > GITHUB_CACHE_TTL_SECONDS
            exists = conn.execute(
                "SELECT 1 FROM projects WHERE project_id = ?", (project_id,)
            ).fetchone()
            if expired or not exists:
                conn.execute("DELETE FROM github_cache WHERE cache_key = ?", (cache_key,))
                return None
            return project_id


def set_github_cache(cache_key: str, project_id: str) -> None:
    with closing(_connect()) as conn:
        with conn:
            conn.execute(
                "INSERT OR REPLACE INTO github_cache (cache_key, project_id, cached_at)"
                " VALUES (?,?,?)",
                (cache_key, project_id, time.time()),
            )


def clear_all() -> None:
    """Used by tests to avoid state leaking between test cases."""
    with closing(_connect()) as conn:
        with conn:
            conn.execute("DELETE FROM projects")
            conn.execute("DELETE FROM github_cache")
