"""GET /v1/runs (list), GET /v1/runs/{trace_id}/trace (all events)."""
from fastapi import APIRouter, Depends, Query

from audit_service.database import get_connection
from audit_service.queries import get_runs_list, get_trace_events
from audit_service.settings import Settings

router = APIRouter(prefix="/v1/runs", tags=["runs"])


def _get_settings() -> Settings:
    return Settings()


@router.get("")
def list_runs(
    from_ts: str = Query(..., description="ISO datetime from"),
    to_ts: str = Query(..., description="ISO datetime to"),
    status: str | None = Query(None),
    service: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    settings: Settings = Depends(_get_settings),
):
    """Список runs: trace_id, ts, status, duration_ms, tokens_total, tool_calls, top1_score."""
    conn = get_connection(settings.audit_db_path)
    try:
        return get_runs_list(conn, from_ts, to_ts, status, service, limit)
    finally:
        conn.close()


@router.get("/{trace_id}/trace")
def get_trace(
    trace_id: str,
    settings: Settings = Depends(_get_settings),
):
    """Все события по trace_id в хронологическом порядке."""
    conn = get_connection(settings.audit_db_path)
    try:
        events = get_trace_events(conn, trace_id)
        return {"trace_id": trace_id, "events": events}
    finally:
        conn.close()
