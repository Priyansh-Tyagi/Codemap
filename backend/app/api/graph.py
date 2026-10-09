from __future__ import annotations

from fastapi import APIRouter, Query, Request

from models.schemas import CycleOut, MetricsResponse, TourResponse, TourStopOut
from api.projects import _get_record_or_404
from graph.tour import generate_tour
from analyzer.ai_tour import narrate_tour, AINarrationError
from services import store
import collections

router = APIRouter(prefix="/projects/{project_id}", tags=["graph"])


@router.get("/cycles", response_model=list[CycleOut])
def get_project_cycles(project_id: str, http_request: Request) -> list[CycleOut]:
    record = _get_record_or_404(project_id, http_request)
    return [CycleOut(**c) for c in record.cycles]


@router.get("/metrics", response_model=MetricsResponse)
def get_project_metrics(project_id: str, http_request: Request) -> MetricsResponse:
    record = _get_record_or_404(project_id, http_request)
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


TourMode = Query("trace", pattern="^(trace|foundation)$")


def _build_tour(record, mode: str) -> dict:
    return generate_tour(
        record.graph, record.metrics["perNode"], record.architecture,
        record.nodes_in_cycles, mode=mode,
    )


@router.get("/tour", response_model=TourResponse)
def get_project_tour(project_id: str, http_request: Request, mode: str = TourMode) -> TourResponse:
    """
    The deterministic guided tour (see graph/tour.py) - zero AI, always
    available, computed from already-stored analysis data (cheap; no need
    to cache). `mode`: "trace" walks top-down from entry points, "foundation"
    goes bottom-up from the most relied-upon files. For the AI-narrated
    version see POST /tour/narrate.
    """
    record = _get_record_or_404(project_id, http_request)
    tour = _build_tour(record, mode)
    return TourResponse(stops=[TourStopOut(**s) for s in tour["stops"]], mode=mode, note=tour["note"])


@router.post("/tour/narrate", response_model=TourResponse)
def narrate_project_tour(project_id: str, http_request: Request, mode: str = TourMode) -> TourResponse:
    """
    The opt-in AI layer. Always computes the deterministic tour first and
    returns it regardless of what happens next - narration can only ADD
    text to stops that already work, never replace them with something that
    might fail. Any problem getting a narration (not configured, rate
    limited, network error, malformed AI response) degrades to the plain
    deterministic tour plus a `narrationError` explaining why.
    """
    record = _get_record_or_404(project_id, http_request)
    tour = _build_tour(record, mode)
    stops, note = tour["stops"], tour["note"]
    if not stops:
        return TourResponse(stops=[], mode=mode, note=note)

    def respond(narrated=False, error=None):
        return TourResponse(stops=[TourStopOut(**s) for s in stops], mode=mode, note=note,
                            narrated=narrated, narrationError=error)

    # Keyed by project AND mode: the two modes produce different stops, so a
    # narration for one must never be attached to the other. (The column is
    # still called project_id; it holds "<project_id>:<mode>" - no schema
    # change, so existing databases need no migration.)
    cache_key = f"{project_id}:{mode}"
    cached = store.get_cached_tour_narratives(cache_key)
    if cached is not None and len(cached) == len(stops):
        for stop, text in zip(stops, cached):
            stop["narrative"] = text
        return respond(narrated=True)

    architecture_summary = dict(collections.Counter(record.architecture.values()))
    try:
        narratives = narrate_tour(record.source_label, stops, architecture_summary)
    except AINarrationError as e:
        return respond(error=str(e))

    store.set_cached_tour_narratives(cache_key, narratives)
    for stop, text in zip(stops, narratives):
        stop["narrative"] = text
    return respond(narrated=True)
