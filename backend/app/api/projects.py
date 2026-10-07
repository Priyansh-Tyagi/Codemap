from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from graph.builder import build_dependency_graph
from analyzer.github_fetcher import fetch_github_repo, parse_github_url, GitHubFetchError
from api.auth import get_access_token_for_request, get_session_id
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
        isPrivate=record.is_private,
    )


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze_repository(request: AnalyzeRequest, http_request: Request) -> AnalyzeResponse:
    access_token = get_access_token_for_request(http_request)
    session_id = get_session_id(http_request)

    # GitHub sources only: check the cache BEFORE fetching anything. Cache
    # key comes from parsing the URL locally (no network call), so a cache
    # hit costs nothing - not even the metadata lookup that would otherwise
    # count against the GitHub rate limit.
    #
    # Cache key is scoped to the signed-in session when there is one. We
    # can't know a repo is private until AFTER fetching its metadata (that's
    # the whole reason the cache check happens first), so instead of trying
    # to special-case private repos here, EVERY signed-in user's cache is
    # private to them. The cost is a few avoidable re-fetches when two
    # signed-in users both analyze the same public repo; the alternative -
    # one user's session accidentally serving another user's cached private
    # analysis - is a real leak, not a missed optimization.
    if request.githubUrl:
        try:
            owner, repo, ref = parse_github_url(request.githubUrl)
        except GitHubFetchError as e:
            raise HTTPException(status_code=400, detail=str(e))
        base_key = f"{owner}/{repo}@{ref or 'default'}"
        cache_key = f"{session_id}:{base_key}" if session_id else base_key

        if not request.forceRefresh:
            cached_project_id = store.get_cached_github_project_id(cache_key)
            if cached_project_id:
                record = store.get_project(cached_project_id)
                if record:
                    return _record_to_analyze_response(record, cached=True)

    fetched = None

    if request.githubUrl:
        try:
            fetched = fetch_github_repo(request.githubUrl, access_token=access_token)
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

        is_private = bool(fetched and fetched.is_private)
        if is_private and not session_id:
            # Shouldn't be reachable (a private repo 404s for an anonymous
            # token-less request before we get here), but if GitHub's API
            # ever behaves differently, fail safe rather than store a
            # private repo's graph with no owner to restrict it to.
            raise HTTPException(status_code=400, detail="Sign in with GitHub to analyze a private repository.")

        record = store.create_project(
            build_result, source_type=source_type, source_label=source_label,
            is_private=is_private, owner_session_id=session_id if is_private else None,
        )

        if request.githubUrl:
            store.set_github_cache(cache_key, record.project_id)

        return _record_to_analyze_response(record, cached=False)
    finally:
        # The graph is fully built and stored in memory at this point - the
        # extracted files themselves are no longer needed, whether analysis
        # succeeded or raised. Always clean up the temp directory.
        if fetched:
            fetched.cleanup()


def _get_record_or_404(project_id: str, http_request: Request):
    """
    The single chokepoint every project-read route goes through (here, and
    imported into graph.py / files.py), so private-project access control
    lives in exactly one place. A private project is invisible to anyone
    but the session that created it - returning 404 rather than 403, so a
    shared link to someone else's private analysis looks identical to a
    stale/wrong link, not "something exists here you can't see."
    """
    record = store.get_project(project_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"unknown project_id: {project_id}")
    if record.is_private and record.owner_session_id != get_session_id(http_request):
        raise HTTPException(status_code=404, detail=f"unknown project_id: {project_id}")
    return record


@router.get("/projects/{project_id}", response_model=ProjectSummary)
def get_project_summary(project_id: str, http_request: Request) -> ProjectSummary:
    record = _get_record_or_404(project_id, http_request)
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
        isPrivate=record.is_private,
    )


@router.get("/projects/{project_id}/graph", response_model=GraphResponse)
def get_project_graph(project_id: str, http_request: Request) -> GraphResponse:
    record = _get_record_or_404(project_id, http_request)
    nodes = [_node_to_out(record, n) for n in record.graph.nodes]
    edges = [
        EdgeOut(source=u, target=v, type=data.get("type", "import"), symbols=data.get("symbols", []))
        for u, v, data in record.graph.edges(data=True)
    ]
    return GraphResponse(nodes=nodes, edges=edges)


@router.get("/projects/{project_id}/files", response_model=list[FileListItem])
def list_project_files(project_id: str, http_request: Request) -> list[FileListItem]:
    record = _get_record_or_404(project_id, http_request)
    return [
        FileListItem(
            id=n,
            name=record.graph.nodes[n]["name"],
            filePath=record.graph.nodes[n]["filePath"],
        )
        for n in record.graph.nodes
    ]
