"""Audit UI: proxy к audit-service и Jinja2-страницы (KPI, метрики, runs, trace)."""
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from gateway.settings import Settings

router = APIRouter()
logger = logging.getLogger(__name__)
_settings = Settings()

_templates_dir = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))
templates.env.filters["tojson"] = lambda v: json.dumps(v, ensure_ascii=False) if v is not None else "null"

# Дефолтные данные при недоступности audit-service
_DEFAULT_OVERVIEW = {
    "total_runs": 0,
    "ok_rate": 0.0,
    "error_rate": 0.0,
    "insufficient_rate": 0.0,
    "p95_latency_ms": None,
    "avg_tokens": 0,
    "avg_tool_calls": 0,
}
_DEFAULT_TIMESERIES = {"labels": [], "datasets": []}
_DEFAULT_TOOLS = []
_DEFAULT_CONTRACTS = {"schema_fail_rate": 0.0, "repair_rate": 0.0, "repair_success_rate": 0.0, "finish_reason": []}
_DEFAULT_RUNS = []
_DEFAULT_TRACE = []


def _timeseries_to_chart(raw: dict | list, dataset_label: str = "Value") -> dict:
    """Приводит ответ audit-service /v1/metrics/timeseries к формату Chart.js (labels + datasets)."""
    if isinstance(raw, dict) and "labels" in raw and "datasets" in raw:
        return raw
    if isinstance(raw, list) and raw and isinstance(raw[0], dict) and "bucket" in raw[0] and "value" in raw[0]:
        labels = [row["bucket"] for row in raw]
        data = [row["value"] for row in raw]
        return {"labels": labels, "datasets": [{"label": dataset_label, "data": data}]}
    return _DEFAULT_TIMESERIES


def _default_time_range() -> tuple[str, str]:
    """Дефолтный диапазон: последние 24 часа в ISO."""
    now = datetime.now(timezone.utc)
    return (now - timedelta(hours=24)).isoformat(), now.isoformat()


async def _proxy_get(path: str, params: dict | None = None) -> dict | list:
    """GET к audit-service; при ошибке или пустом URL возвращает пустые данные."""
    base = (_settings.audit_service_url or "").rstrip("/")
    if not base:
        return {}
    url = f"{base}{path}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, params=params or {})
            if r.status_code == 200:
                return r.json()
            logger.warning("audit proxy GET %s status=%s", path, r.status_code)
    except Exception as e:
        logger.warning("audit proxy GET %s: %s", path, e)
    return {}


def _layout_ctx(active: str) -> dict:
    return {
        "audit_active": active,
        "nav": [
            ("health", "/audit/", "Health"),
            ("rag", "/audit/rag", "RAG Quality"),
            ("tools", "/audit/tools", "Tools & Policy"),
            ("contracts", "/audit/contracts", "Contracts & Repair"),
            ("runs", "/audit/runs", "Run Explorer"),
        ],
    }


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def audit_health(request: Request):
    """Health dashboard: KPI tiles + latency vs tokens chart."""
    from_ts, to_ts = _default_time_range()
    overview = await _proxy_get("/v1/metrics/overview", {"from_ts": from_ts, "to_ts": to_ts}) or _DEFAULT_OVERVIEW
    # run_ok_rate всегда даёт точки при наличии run.finish; run_p95_latency_ms пустой, если duration_ms не задан
    ts_raw = await _proxy_get("/v1/metrics/timeseries", {"metric": "run_ok_rate", "interval": "1h", "from_ts": from_ts, "to_ts": to_ts})
    ts = _timeseries_to_chart(ts_raw, "Success rate")
    ctx = {
        **_layout_ctx("health"),
        "overview": overview,
        "timeseries": ts,
    }
    return templates.TemplateResponse(request, "audit/health.html", ctx)


@router.get("/rag", response_class=HTMLResponse)
async def audit_rag(request: Request):
    """RAG Quality: insufficient vs low_top1, sources histogram, top docs."""
    from_ts, to_ts = _default_time_range()
    overview = await _proxy_get("/v1/metrics/overview", {"from_ts": from_ts, "to_ts": to_ts}) or _DEFAULT_OVERVIEW
    ts_raw = await _proxy_get("/v1/metrics/timeseries", {"metric": "insufficient_rate", "interval": "1h", "from_ts": from_ts, "to_ts": to_ts})
    ts = _timeseries_to_chart(ts_raw, "insufficient rate")
    ctx = {
        **_layout_ctx("rag"),
        "overview": overview,
        "timeseries": ts,
    }
    return templates.TemplateResponse(request, "audit/rag_quality.html", ctx)


@router.get("/tools", response_class=HTMLResponse)
async def audit_tools(request: Request):
    """Tools & Policy: tool p95 latency, tool calls vs success, policy blocks."""
    from_ts, to_ts = _default_time_range()
    tools = await _proxy_get("/v1/metrics/tools", {"from_ts": from_ts, "to_ts": to_ts})
    if not tools and not isinstance(tools, list):
        tools = _DEFAULT_TOOLS
    ts_raw = await _proxy_get("/v1/metrics/timeseries", {"metric": "policy_block_rate", "interval": "1h", "from_ts": from_ts, "to_ts": to_ts})
    ts = _timeseries_to_chart(ts_raw, "policy block rate")
    ctx = {
        **_layout_ctx("tools"),
        "tools": tools if isinstance(tools, list) else tools.get("tools", _DEFAULT_TOOLS),
        "timeseries": ts,
    }
    return templates.TemplateResponse(request, "audit/tools.html", ctx)


@router.get("/contracts", response_class=HTMLResponse)
async def audit_contracts(request: Request):
    """Contracts & Repair: schema fail vs repair success, finish_reason distribution."""
    from_ts, to_ts = _default_time_range()
    data = await _proxy_get("/v1/metrics/contracts", {"from_ts": from_ts, "to_ts": to_ts})
    if not data:
        data = _DEFAULT_CONTRACTS
    ts_raw = await _proxy_get("/v1/metrics/timeseries", {"metric": "schema_fail_rate", "interval": "1h", "from_ts": from_ts, "to_ts": to_ts})
    ts = _timeseries_to_chart(ts_raw, "schema fail rate")
    ctx = {
        **_layout_ctx("contracts"),
        "contracts": data,
        "timeseries": ts,
    }
    return templates.TemplateResponse(request, "audit/contracts.html", ctx)


@router.get("/runs", response_class=HTMLResponse)
async def audit_runs(
    request: Request,
    status: str | None = None,
    service: str | None = None,
    limit: int = 50,
):
    """Run Explorer: таблица runs с фильтрами."""
    from_ts, to_ts = _default_time_range()
    params = {"from_ts": from_ts, "to_ts": to_ts, "limit": limit}
    if status:
        params["status"] = status
    if service:
        params["service"] = service
    runs = await _proxy_get("/v1/runs", params)
    if not runs and not isinstance(runs, list):
        runs = _DEFAULT_RUNS
    if isinstance(runs, dict) and "runs" in runs:
        runs = runs["runs"]
    ctx = {
        **_layout_ctx("runs"),
        "runs": runs or _DEFAULT_RUNS,
        "filter_status": status,
        "filter_service": service,
        "limit": limit,
    }
    return templates.TemplateResponse(request, "audit/runs.html", ctx)


@router.get("/runs/{trace_id}", response_class=HTMLResponse)
async def audit_run_trace(request: Request, trace_id: str):
    """Run Trace: вертикальный таймлайн событий по trace_id."""
    trace = await _proxy_get(f"/v1/runs/{trace_id}/trace")
    if not trace and not isinstance(trace, list):
        trace = _DEFAULT_TRACE
    if isinstance(trace, dict) and "events" in trace:
        trace = trace["events"]
    ctx = {
        **_layout_ctx("runs"),
        "trace_id": trace_id,
        "events": trace or _DEFAULT_TRACE,
    }
    return templates.TemplateResponse(request, "audit/run_trace.html", ctx)
