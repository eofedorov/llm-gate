"""GET /v1/metrics/*: overview, timeseries, tools, contracts — SQL-агрегации по events."""
from fastapi import APIRouter, Depends, Query

from audit_service.database import get_connection
from audit_service.queries import get_contracts, get_overview, get_timeseries, get_tools
from audit_service.settings import Settings

router = APIRouter(prefix="/v1/metrics", tags=["metrics"])


def _get_settings() -> Settings:
    return Settings()


@router.get("/overview")
def get_metrics_overview(
    from_ts: str = Query(..., description="ISO datetime from"),
    to_ts: str = Query(..., description="ISO datetime to"),
    service: str | None = Query(None),
    settings: Settings = Depends(_get_settings),
):
    """KPI-плитки: total_runs, ok_rate, error_rate, insufficient_rate, p95_latency_ms, avg_tokens, avg_tool_calls."""
    conn = get_connection(settings.audit_db_path)
    try:
        return get_overview(conn, from_ts, to_ts, service)
    finally:
        conn.close()


@router.get("/timeseries")
def get_metrics_timeseries(
    metric: str = Query(..., description="run_ok_rate | run_p95_latency_ms | tokens_avg | tool_calls_avg | insufficient_rate | schema_fail_rate | repair_rate | policy_block_rate"),
    interval: str = Query("5m", description="1m | 5m | 1h"),
    from_ts: str = Query(...),
    to_ts: str = Query(...),
    service: str | None = Query(None),
    settings: Settings = Depends(_get_settings),
):
    """Точки для графиков по выбранной метрике."""
    conn = get_connection(settings.audit_db_path)
    try:
        return get_timeseries(conn, metric, interval, from_ts, to_ts, service)
    finally:
        conn.close()


@router.get("/tools")
def get_metrics_tools(
    from_ts: str = Query(...),
    to_ts: str = Query(...),
    service: str | None = Query(None),
    settings: Settings = Depends(_get_settings),
):
    """По каждому tool_name: call_count, p95_latency_ms, error_rate, block_rate."""
    conn = get_connection(settings.audit_db_path)
    try:
        return get_tools(conn, from_ts, to_ts, service)
    finally:
        conn.close()


@router.get("/contracts")
def get_metrics_contracts(
    from_ts: str = Query(...),
    to_ts: str = Query(...),
    service: str | None = Query(None),
    settings: Settings = Depends(_get_settings),
):
    """schema_fail_rate, repair_rate, repair_success_rate, finish_reason distribution."""
    conn = get_connection(settings.audit_db_path)
    try:
        return get_contracts(conn, from_ts, to_ts, service)
    finally:
        conn.close()
