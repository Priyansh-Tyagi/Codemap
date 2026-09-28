from __future__ import annotations

from fastapi import APIRouter, HTTPException

from graph.builder import build_dependency_graph
from analyzer.github_fetcher import fetch_github_repo, parse_github_url, GitHubFetchError
from models.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    ProjectSummary,
    GraphResponse,
    NodeOut,
    EdgeOut,
    FileListItem,
)
from services import store

router = APIRouter(tags=["projects"])


def _node_to_out(record, node_id: str) -> NodeOut:
    data = record.graph.nodes[node_id]
    node_metrics = record.metrics["perNode"].get(node_id, {})
    node_risk = record.risk.get(node_id, {})
    return NodeOut(
        id=node_id,
        filePath=data["filePath"],
        name=data["name"],
        language=data.get("language", "javascript"),
        linesOfCode=data.get("linesOfCode", 0),
        inDegree=node_metrics.get("inDegree", 0),
        outDegree=node_metrics.get("outDegree", 0),
        dependencyDepth=node_metrics.get("dependencyDepth", 0),
        degreeCentrality=node_metrics.get("degreeCentrality", 0.0),
        betweennessCentrality=node_metrics.get("betweennessCentrality"),
        inCycle=node_id in record.nodes_in_cycles,
        architectureType=record.architecture.get(node_id, "Unknown"),
        riskScore=node_risk.get("score"),
        riskLevel=node_risk.get("level"),
        riskReasons=node_risk.get("reasons", []),
    )


def _record_to_analyze_response(record, cached: bool) -> AnalyzeResponse:
    return AnalyzeResponse(
        projectId=record.project_id,
        rootPath=record.root,
        sourceType=record.source_type,
        sourceLabel=record.source_label,
        fileCount=record.graph.number_of_nodes(),
        edgeCount=record.graph.number_of_edges(),
        cycleCount=len(record.cycles),
        cyclesTruncated=record.cycles_truncated,
        cyclicComponentCount=len(record.cycle_components),
        externalDependencyCount=len(record.external_dependencies),
        unresolvedImportCount=len(record.unresolved_imports),
        cached=cached,
    )


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze_repository(request: AnalyzeRequest) -> AnalyzeResponse:
    # GitHub sources only: check the cache BEFORE fetching anything. Cache
    # key comes from parsing the URL locally (no network call), so a cache
    # hit costs nothing - not even the metadata lookup that would otherwise
    # count against the GitHub rate limit.
    if request.githubUrl:
        try:
            owner, repo, ref = parse_github_url(request.githubUrl)
        except GitHubFetchError as e:
            raise HTTPException(status_code=400, detail=str(e))
        cache_key = f"{owner}/{repo}@{ref or 'default'}"

        if not request.forceRefresh:
            cached_project_id = store.get_cached_github_project_id(cache_key)
            if cached_project_id:
                record = store.get_project(cached_project_id)
                if record:
                    return _record_to_analyze_response(record, cached=True)

    fetched = None

    if request.githubUrl:
        try:
            fetched = fetch_github_repo(request.githubUrl)
        except GitHubFetchError as e:
            raise HTTPException(status_code=400, detail=str(e))
        target_path = fetched.local_path
        source_type = "github"
        source_label = f"{fetched.owner}/{fetched.repo}@{fetched.ref}"
    else:
        target_path = request.path
        source_type = "local"
        source_label = target_path

    try:
        try:
            build_result = build_dependency_graph(target_path)
        except FileNotFoundError:
            raise HTTPException(status_code=400, detail=f"path does not exist: {target_path}")
        except NotADirectoryError:
            raise HTTPException(status_code=400, detail=f"path is not a directory: {target_path}")

        record = store.create_project(build_result, source_type=source_type, source_label=source_label)

        if request.githubUrl:
            store.set_github_cache(cache_key, record.project_id)

        return _record_to_analyze_response(record, cached=False)
    finally:
        # The graph is fully built and stored in memory at this point - the
        # extracted files themselves are no longer needed, whether analysis
        # succeeded or raised. Always clean up the temp directory.
        if fetched:
            fetched.cleanup()


def _get_record_or_404(project_id: str):
    record = store.get_project(project_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"unknown project_id: {project_id}")
    return record


@router.get("/projects/{project_id}", response_model=ProjectSummary)
def get_project_summary(project_id: str) -> ProjectSummary:
    record = _get_record_or_404(project_id)
    high_risk_count = sum(
        1
        for node_risk in record.risk.values()
        if node_risk.get("level") in ("High", "Critical")
    )
    return ProjectSummary(
        projectId=record.project_id,
        rootPath=record.root,
        sourceType=record.source_type,
        sourceLabel=record.source_label,
        fileCount=record.graph.number_of_nodes(),
        edgeCount=record.graph.number_of_edges(),
        cycleCount=len(record.cycles),
        cyclesTruncated=record.cycles_truncated,
        cyclicComponentCount=len(record.cycle_components),
        highRiskCount=high_risk_count,
        avgDependencies=record.metrics["avgDependencies"],
        createdAt=record.created_at,
    )


@router.get("/projects/{project_id}/graph", response_model=GraphResponse)
def get_project_graph(project_id: str) -> GraphResponse:
    record = _get_record_or_404(project_id)
    nodes = [_node_to_out(record, n) for n in record.graph.nodes]
    edges = [
        EdgeOut(source=u, target=v, type=data.get("type", "import"), symbols=data.get("symbols", []))
        for u, v, data in record.graph.edges(data=True)
    ]
    return GraphResponse(nodes=nodes, edges=edges)


@router.get("/projects/{project_id}/files", response_model=list[FileListItem])
def list_project_files(project_id: str) -> list[FileListItem]:
    record = _get_record_or_404(project_id)
    return [
        FileListItem(
            id=n,
            name=record.graph.nodes[n]["name"],
            filePath=record.graph.nodes[n]["filePath"],
        )
        for n in record.graph.nodes
    ]
