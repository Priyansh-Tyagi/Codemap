from __future__ import annotations

from fastapi import APIRouter

from models.schemas import CycleOut, MetricsResponse
from api.projects import _get_record_or_404

router = APIRouter(prefix="/projects/{project_id}", tags=["graph"])


@router.get("/cycles", response_model=list[CycleOut])
def get_project_cycles(project_id: str) -> list[CycleOut]:
    record = _get_record_or_404(project_id)
    return [CycleOut(**c) for c in record.cycles]


@router.get("/metrics", response_model=MetricsResponse)
def get_project_metrics(project_id: str) -> MetricsResponse:
    record = _get_record_or_404(project_id)
    m = record.metrics
    return MetricsResponse(
        fileCount=m["fileCount"],
        edgeCount=m["edgeCount"],
        connectedComponentCount=m["connectedComponentCount"],
        largestComponentSize=m["largestComponentSize"],
        avgDependencies=m["avgDependencies"],
        betweennessSkipped=m["betweennessSkipped"],
        externalDependencies=record.external_dependencies,
        unresolvedImportCount=len(record.unresolved_imports),
    )
