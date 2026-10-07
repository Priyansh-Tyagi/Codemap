from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from models.schemas import NodeOut, ImpactResponse
from graph.impact import analyze_impact
from services import store
from api.projects import _node_to_out, _get_record_or_404

router = APIRouter(prefix="/projects/{project_id}/files", tags=["files"])


def _get_node_or_404(record, file_path: str) -> str:
    if file_path not in record.graph:
        raise HTTPException(status_code=404, detail=f"unknown file: {file_path}")
    return file_path


@router.get("/{file_path:path}/dependencies", response_model=list[str])
def get_file_dependencies(project_id: str, file_path: str, http_request: Request) -> list[str]:
    """Files this file directly imports (outgoing edges)."""
    record = _get_record_or_404(project_id, http_request)
    node_id = _get_node_or_404(record, file_path)
    return sorted(record.graph.successors(node_id))


@router.get("/{file_path:path}/dependents", response_model=list[str])
def get_file_dependents(project_id: str, file_path: str, http_request: Request) -> list[str]:
    """Files that directly import this file (incoming edges)."""
    record = _get_record_or_404(project_id, http_request)
    node_id = _get_node_or_404(record, file_path)
    return sorted(record.graph.predecessors(node_id))


@router.get("/{file_path:path}/impact", response_model=ImpactResponse)
def get_file_impact(project_id: str, file_path: str, http_request: Request) -> ImpactResponse:
    record = _get_record_or_404(project_id, http_request)
    node_id = _get_node_or_404(record, file_path)
    result = analyze_impact(record.graph, node_id)
    return ImpactResponse(**result)


# IMPORTANT: this catch-all route must be declared LAST. FastAPI/Starlette
# matches routes in declaration order, and {file_path:path} is a greedy
# converter that matches slashes too - if this were declared first, a
# request for ".../database.js/impact" would match here first, with
# file_path swallowing "database.js/impact" whole, and the dedicated
# /impact route below would never be reached.
@router.get("/{file_path:path}", response_model=NodeOut)
def get_file_detail(project_id: str, file_path: str, http_request: Request) -> NodeOut:
    record = _get_record_or_404(project_id, http_request)
    node_id = _get_node_or_404(record, file_path)
    return _node_to_out(record, node_id)
