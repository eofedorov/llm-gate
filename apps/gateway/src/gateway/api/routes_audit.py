"""Audit UI: proxy к audit-service и Jinja2-страницы (KPI, метрики, runs, trace)."""
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

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
    "avg_tokens": None,
    "avg_tool_calls": None,
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


def _merge_timeseries_charts(
    raw_a: dict | list,
    label_a: str,
    raw_b: dict | list,
    label_b: str,
) -> dict:
    """Два списка {bucket, value} в один Chart.js с общими labels (порядок как в raw_a)."""
    if not (isinstance(raw_a, list) and raw_a and isinstance(raw_a[0], dict) and "bucket" in raw_a[0]):
        return _DEFAULT_TIMESERIES
    labels = [row["bucket"] for row in raw_a]
    data_a = [row.get("value") for row in raw_a]
    map_b: dict[Any, Any] = {}
    if isinstance(raw_b, list):
        for row in raw_b:
            if isinstance(row, dict) and "bucket" in row:
                map_b[row["bucket"]] = row.get("value")
    data_b = [map_b.get(b) for b in labels]
    return {
        "labels": labels,
        "datasets": [
            {"label": label_a, "data": data_a},
            {"label": label_b, "data": data_b},
        ],
    }


def _default_time_range() -> tuple[str, str]:
    """Дефолтный диапазон: последние 24 часа в ISO."""
    now = datetime.now(timezone.utc)
    return (now - timedelta(hours=24)).isoformat(), now.isoformat()


async def _proxy_get(path: str, params: dict | None = None) -> tuple[Any, str | None]:
    """
    GET к audit-service.
    Возвращает (тело JSON или пустой dict/list, сообщение об ошибке при сбое/пустом URL).
    """
    base = (_settings.audit_service_url or "").rstrip("/")
    if not base:
        return {}, "AUDIT_SERVICE_URL не задан — метрики недоступны."
    url = f"{base}{path}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, params=params or {})
            if r.status_code == 200:
                return r.json(), None
            logger.warning("audit proxy GET %s status=%s", path, r.status_code)
            return {}, f"audit-service {path}: HTTP {r.status_code}"
    except Exception as e:
        logger.warning("audit proxy GET %s: %s", path, e)
        return {}, f"audit-service {path}: {e!s}"


def _layout_ctx(active: str, audit_errors: list[str] | None = None) -> dict:
    return {
        "audit_active": active,
        "audit_errors": audit_errors or [],
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
    errors: list[str] = []
    overview_raw, e_ov = await _proxy_get("/v1/metrics/overview", {"from_ts": from_ts, "to_ts": to_ts})
    if e_ov:
        errors.append(e_ov)
    overview = (
        {**_DEFAULT_OVERVIEW, **overview_raw}
        if isinstance(overview_raw, dict) and overview_raw
        else _DEFAULT_OVERVIEW
    )
    ts_raw, e1 = await _proxy_get(
        "/v1/metrics/timeseries",
        {"metric": "run_ok_rate", "interval": "1h", "from_ts": from_ts, "to_ts": to_ts},
    )
    if e1:
        errors.append(e1)
    ts = _timeseries_to_chart(ts_raw, "Success rate")
    ctx = {
        **_layout_ctx("health", errors),
        "overview": overview,
        "timeseries": ts,
    }
    return templates.TemplateResponse(request, "audit/health.html", ctx)


@router.get("/rag", response_class=HTMLResponse)
async def audit_rag(request: Request):
    """RAG Quality: insufficient vs low_top1, sources histogram, top docs."""
    from_ts, to_ts = _default_time_range()
    errors: list[str] = []
    overview_raw, e_ov = await _proxy_get("/v1/metrics/overview", {"from_ts": from_ts, "to_ts": to_ts})
    if e_ov:
        errors.append(e_ov)
    overview = (
        {**_DEFAULT_OVERVIEW, **overview_raw}
        if isinstance(overview_raw, dict) and overview_raw
        else _DEFAULT_OVERVIEW
    )
    ts_ins, e1 = await _proxy_get(
        "/v1/metrics/timeseries",
        {"metric": "insufficient_rate", "interval": "1h", "from_ts": from_ts, "to_ts": to_ts},
    )
    ts_low, e2 = await _proxy_get(
        "/v1/metrics/timeseries",
        {"metric": "low_top1_proxy_rate", "interval": "1h", "from_ts": from_ts, "to_ts": to_ts},
    )
    if e1:
        errors.append(e1)
    if e2:
        errors.append(e2)
    ts = _merge_timeseries_charts(ts_ins, "Insufficient rate", ts_low, "Low top1 (proxy)")
    ctx = {
        **_layout_ctx("rag", errors),
        "overview": overview,
        "timeseries": ts,
    }
    return templates.TemplateResponse(request, "audit/rag_quality.html", ctx)


@router.get("/tools", response_class=HTMLResponse)
async def audit_tools(request: Request):
    """Tools & Policy: tool p95 latency, tool calls vs success, policy blocks."""
    from_ts, to_ts = _default_time_range()
    errors: list[str] = []
    tools_raw, e_tools = await _proxy_get("/v1/metrics/tools", {"from_ts": from_ts, "to_ts": to_ts})
    if e_tools:
        errors.append(e_tools)
    tools = tools_raw if isinstance(tools_raw, list) else _DEFAULT_TOOLS
    ts_blocks, e1 = await _proxy_get(
        "/v1/metrics/timeseries",
        {"metric": "policy_block_rate", "interval": "1h", "from_ts": from_ts, "to_ts": to_ts},
    )
    ts_calls, e2 = await _proxy_get(
        "/v1/metrics/timeseries",
        {"metric": "tool_calls_avg", "interval": "1h", "from_ts": from_ts, "to_ts": to_ts},
    )
    if e1:
        errors.append(e1)
    if e2:
        errors.append(e2)
    ts = _merge_timeseries_charts(ts_blocks, "Policy block rate", ts_calls, "Tool calls / run (avg)")
    ctx = {
        **_layout_ctx("tools", errors),
        "tools": tools,
        "timeseries": ts,
    }
    return templates.TemplateResponse(request, "audit/tools.html", ctx)


@router.get("/contracts", response_class=HTMLResponse)
async def audit_contracts(request: Request):
    """Contracts & Repair: schema fail vs repair success, finish_reason distribution."""
    from_ts, to_ts = _default_time_range()
    errors: list[str] = []
    data_raw, e_data = await _proxy_get("/v1/metrics/contracts", {"from_ts": from_ts, "to_ts": to_ts})
    if e_data:
        errors.append(e_data)
    data = (
        {**_DEFAULT_CONTRACTS, **data_raw}
        if isinstance(data_raw, dict) and data_raw
        else _DEFAULT_CONTRACTS
    )
    ts_schema, e1 = await _proxy_get(
        "/v1/metrics/timeseries",
        {"metric": "schema_fail_rate", "interval": "1h", "from_ts": from_ts, "to_ts": to_ts},
    )
    ts_repair, e2 = await _proxy_get(
        "/v1/metrics/timeseries",
        {"metric": "repair_success_bucket_rate", "interval": "1h", "from_ts": from_ts, "to_ts": to_ts},
    )
    if e1:
        errors.append(e1)
    if e2:
        errors.append(e2)
    ts = _merge_timeseries_charts(ts_schema, "Schema fail rate", ts_repair, "Repair success (per bucket)")
    ctx = {
        **_layout_ctx("contracts", errors),
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
    runs_raw, e_runs = await _proxy_get("/v1/runs", params)
    errors: list[str] = []
    if e_runs:
        errors.append(e_runs)
    runs = runs_raw if isinstance(runs_raw, list) else _DEFAULT_RUNS
    if isinstance(runs_raw, dict) and "runs" in runs_raw:
        runs = runs_raw["runs"]
    ctx = {
        **_layout_ctx("runs", errors),
        "runs": runs or _DEFAULT_RUNS,
        "filter_status": status,
        "filter_service": service,
        "limit": limit,
    }
    return templates.TemplateResponse(request, "audit/runs.html", ctx)


@router.get("/runs/{trace_id}", response_class=HTMLResponse)
async def audit_run_trace(request: Request, trace_id: str):
    """Run Trace: вертикальный таймлайн событий по trace_id."""
    trace_raw, e_tr = await _proxy_get(f"/v1/runs/{trace_id}/trace")
    errors: list[str] = []
    if e_tr:
        errors.append(e_tr)
    trace = trace_raw if isinstance(trace_raw, list) else _DEFAULT_TRACE
    if isinstance(trace_raw, dict) and "events" in trace_raw:
        trace = trace_raw["events"]
    ctx = {
        **_layout_ctx("runs", errors),
        "trace_id": trace_id,
        "events": trace or _DEFAULT_TRACE,
    }
    return templates.TemplateResponse(request, "audit/run_trace.html", ctx)
