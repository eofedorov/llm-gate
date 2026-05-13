"""SQL-запросы для метрик и drill-down по events."""
from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

# Убираем таймзону из ISO-строки для корректного сравнения с ts в БД (формат без timezone)
_TS_TZ_PATTERN = re.compile(r"[+-]\d{2}:?\d{2}$|Z$", re.IGNORECASE)


def _normalize_ts(ts: str) -> str:
    """Нормализация ISO timestamp: убираем суффикс таймзоны для сравнения с полем ts в SQLite."""
    if not ts:
        return ts
    return _TS_TZ_PATTERN.sub("", ts.strip()).strip()


def _where_clause(service: str | None) -> tuple[str, list[Any]]:
    if service:
        return " AND service = ? ", [service]
    return " ", []


def _service_clause(alias: str, service: str | None) -> tuple[str, list[Any]]:
    """Фильтр service для таблицы с алиасом (rf, t, e, …)."""
    if service:
        return f" AND {alias}.service = ? ", [service]
    return " ", []


def _insufficient_exists_sql(alias: str = "rf") -> str:
    """EXISTS: decision insufficient_context по тому же trace_id."""
    return f"""EXISTS (
        SELECT 1 FROM events AS d
        WHERE d.trace_id = {alias}.trace_id
          AND d.event_type = 'decision'
          AND json_extract(d.attrs_json, '$.status') = 'insufficient_context'
    )"""


def get_overview(
    conn: sqlite3.Connection,
    from_ts: str,
    to_ts: str,
    service: str | None = None,
) -> dict[str, Any]:
    """
    KPI по run.finish: total_runs, ok_rate, error_rate, insufficient_rate,
    p95_latency_ms, avg_tokens (из attrs run.finish при наличии),
    avg_tool_calls (среднее число tool.call.finish на trace с run.finish).
    insufficient_rate: decision.status=insufficient_context по trace_id или legacy attrs.
    """
    from_ts = _normalize_ts(from_ts)
    to_ts = _normalize_ts(to_ts)
    w, p = _where_clause(service)
    w_rf, p_rf = _service_clause("rf", service)
    params = [from_ts, to_ts] + p_rf
    base = f"""
        SELECT
            COUNT(*) AS total_runs,
            SUM(CASE WHEN rf.status = 'ok' THEN 1 ELSE 0 END) AS ok_count,
            SUM(CASE WHEN rf.status = 'error' OR rf.status = 'failed' THEN 1 ELSE 0 END) AS error_count,
            AVG(rf.duration_ms) AS avg_latency_ms,
            AVG(CASE WHEN json_extract(rf.attrs_json, '$.tokens_total') IS NOT NULL
                THEN CAST(json_extract(rf.attrs_json, '$.tokens_total') AS REAL) END) AS avg_tokens,
            SUM(CASE WHEN {_insufficient_exists_sql('rf')} OR
                json_extract(rf.attrs_json, '$.insufficient') IN (1, 'true', 'True') OR
                json_extract(rf.attrs_json, '$.finish_reason') IN ('parse_failed', 'error')
                THEN 1 ELSE 0 END) AS insufficient_count
        FROM events AS rf
        WHERE rf.event_type = 'run.finish' AND rf.ts >= ? AND rf.ts <= ?
    """ + w_rf
    row = conn.execute(base, params).fetchone()
    if not row or row["total_runs"] == 0:
        return {
            "total_runs": 0,
            "ok_rate": 0.0,
            "error_rate": 0.0,
            "insufficient_rate": 0.0,
            "p95_latency_ms": None,
            "avg_tokens": None,
            "avg_tool_calls": None,
        }
    total = row["total_runs"]
    ok_rate = row["ok_count"] / total if total else 0.0
    error_rate = row["error_count"] / total if total else 0.0
    insufficient_rate = row["insufficient_count"] / total if total else 0.0

    p95_params = [from_ts, to_ts] + p
    durations = [
        r[0]
        for r in conn.execute(
            """
            SELECT duration_ms FROM events
            WHERE event_type = 'run.finish' AND duration_ms IS NOT NULL AND ts >= ? AND ts <= ?
            """
            + w
            + " ORDER BY duration_ms",
            p95_params,
        ).fetchall()
    ]
    p95_val = None
    if durations:
        idx = max(0, int(len(durations) * 0.95) - 1)
        p95_val = durations[idx]

    # Среднее число tool.call.finish на run (по trace_id с run.finish в окне; без фильтра service на t — tools часто с другого сервиса)
    w_rf2, p_rf2 = _service_clause("rf", service)
    avg_tool_row = conn.execute(
        f"""
        SELECT AVG(tc.cnt) AS avg_tool_calls FROM (
            SELECT COUNT(*) AS cnt
            FROM events AS t
            WHERE t.event_type = 'tool.call.finish'
              AND t.ts >= ? AND t.ts <= ?
              AND EXISTS (
                SELECT 1 FROM events AS rf
                WHERE rf.trace_id = t.trace_id
                  AND rf.event_type = 'run.finish'
                  AND rf.ts >= ? AND rf.ts <= ?
                  {w_rf2}
              )
            GROUP BY t.trace_id
        ) AS tc
        """,
        [from_ts, to_ts, from_ts, to_ts] + p_rf2,
    ).fetchone()
    avg_tool_calls = avg_tool_row["avg_tool_calls"] if avg_tool_row else None

    return {
        "total_runs": total,
        "ok_rate": round(ok_rate, 4),
        "error_rate": round(error_rate, 4),
        "insufficient_rate": round(insufficient_rate, 4),
        "p95_latency_ms": p95_val,
        "avg_tokens": round(row["avg_tokens"], 2) if row["avg_tokens"] is not None else None,
        "avg_tool_calls": round(avg_tool_calls, 2) if avg_tool_calls is not None else None,
    }


def _bucket_expr(interval: str, ts_col: str = "ts") -> str:
    """SQL-выражение bucket по времени."""
    if interval == "1m":
        return f"strftime('%Y-%m-%d %H:%M', {ts_col})"
    if interval == "5m":
        return f"datetime((strftime('%s', {ts_col}) / 300) * 300, 'unixepoch')"
    if interval == "1h":
        return f"strftime('%Y-%m-%d %H:00', {ts_col})"
    return f"datetime((strftime('%s', {ts_col}) / 300) * 300, 'unixepoch')"


def get_timeseries(
    conn: sqlite3.Connection,
    metric: str,
    interval: str,
    from_ts: str,
    to_ts: str,
    service: str | None = None,
) -> list[dict[str, Any]]:
    """
    Точки для графиков. metric: run_ok_rate, run_p95_latency_ms, tokens_avg,
    tool_calls_avg, insufficient_rate, schema_fail_rate, repair_rate, repair_success_bucket_rate,
    policy_block_rate, low_top1_proxy_rate (заглушка 0 — нет поля top1 в событиях).
    """
    from_ts = _normalize_ts(from_ts)
    to_ts = _normalize_ts(to_ts)
    bucket_sql = _bucket_expr(interval, "rf.ts")
    w_rf, p_rf = _service_clause("rf", service)
    w_e, p_e = _service_clause("e", service)
    params: list[Any] = [from_ts, to_ts] + p_rf

    if metric == "run_ok_rate":
        q = f"""
            SELECT {bucket_sql} AS bucket,
                   CAST(SUM(CASE WHEN rf.status = 'ok' THEN 1 ELSE 0 END) AS REAL) / NULLIF(COUNT(*), 0) AS value
            FROM events AS rf
            WHERE rf.event_type = 'run.finish' AND rf.ts >= ? AND rf.ts <= ?
            {w_rf}
            GROUP BY {bucket_sql}
            ORDER BY bucket
            """
    elif metric == "run_p95_latency_ms":
        q = f"""
            SELECT {bucket_sql} AS bucket, AVG(rf.duration_ms) AS value
            FROM events AS rf
            WHERE rf.event_type = 'run.finish' AND rf.duration_ms IS NOT NULL AND rf.ts >= ? AND rf.ts <= ?
            {w_rf}
            GROUP BY {bucket_sql}
            ORDER BY bucket
            """
    elif metric == "tokens_avg":
        q = f"""
            SELECT {bucket_sql} AS bucket,
                   AVG(CAST(json_extract(rf.attrs_json, '$.tokens_total') AS REAL)) AS value
            FROM events AS rf
            WHERE rf.event_type = 'run.finish' AND rf.ts >= ? AND rf.ts <= ?
            {w_rf}
            GROUP BY {bucket_sql}
            ORDER BY bucket
            """
    elif metric == "tool_calls_avg":
        q = f"""
            SELECT b.bucket AS bucket, AVG(b.tool_n) AS value FROM (
                SELECT {bucket_sql} AS bucket,
                       (SELECT COUNT(*) FROM events AS t
                        WHERE t.trace_id = rf.trace_id
                          AND t.event_type = 'tool.call.finish'
                          AND t.ts >= ? AND t.ts <= ?
                       ) AS tool_n
                FROM events AS rf
                WHERE rf.event_type = 'run.finish' AND rf.ts >= ? AND rf.ts <= ?
                {w_rf}
            ) AS b
            GROUP BY b.bucket
            ORDER BY bucket
            """
        params = [from_ts, to_ts, from_ts, to_ts] + p_rf
    elif metric == "insufficient_rate":
        ins = _insufficient_exists_sql("rf")
        q = f"""
            SELECT {bucket_sql} AS bucket,
                   CAST(SUM(CASE WHEN {ins} OR
                     json_extract(rf.attrs_json, '$.insufficient') IN (1, 'true', 'True') OR
                     json_extract(rf.attrs_json, '$.finish_reason') IN ('parse_failed', 'error')
                     THEN 1 ELSE 0 END) AS REAL) / NULLIF(COUNT(*), 0) AS value
            FROM events AS rf
            WHERE rf.event_type = 'run.finish' AND rf.ts >= ? AND rf.ts <= ?
            {w_rf}
            GROUP BY {bucket_sql}
            ORDER BY bucket
            """
    elif metric == "schema_fail_rate":
        b = _bucket_expr(interval, "e.ts")
        q = f"""
            SELECT {b} AS bucket,
                   CAST(SUM(CASE WHEN json_extract(e.attrs_json, '$.result') = 'fail' THEN 1 ELSE 0 END) AS REAL)
                   / NULLIF(COUNT(*), 0) AS value
            FROM events AS e
            WHERE e.event_type = 'schema_validation' AND e.ts >= ? AND e.ts <= ?
            {w_e}
            GROUP BY {b}
            ORDER BY bucket
            """
        params = [from_ts, to_ts] + p_e
    elif metric == "repair_rate":
        b = _bucket_expr(interval, "e.ts")
        q = f"""
            SELECT {b} AS bucket,
                   CAST(SUM(CASE WHEN json_extract(e.attrs_json, '$.attempted') IN (1, 'true', 'True') THEN 1 ELSE 0 END) AS REAL)
                   / NULLIF(COUNT(*), 0) AS value
            FROM events AS e
            WHERE e.event_type = 'repair' AND e.ts >= ? AND e.ts <= ?
            {w_e}
            GROUP BY {b}
            ORDER BY bucket
            """
        params = [from_ts, to_ts] + p_e
    elif metric == "repair_success_bucket_rate":
        b = _bucket_expr(interval, "e.ts")
        q = f"""
            SELECT {b} AS bucket,
                   CAST(SUM(CASE WHEN json_extract(e.attrs_json, '$.success') IN (1, 'true', 'True') THEN 1 ELSE 0 END) AS REAL)
                   / NULLIF(COUNT(*), 0) AS value
            FROM events AS e
            WHERE e.event_type = 'repair' AND e.ts >= ? AND e.ts <= ?
            {w_e}
            GROUP BY {b}
            ORDER BY bucket
            """
        params = [from_ts, to_ts] + p_e
    elif metric == "policy_block_rate":
        b = _bucket_expr(interval, "e.ts")
        q = f"""
            SELECT {b} AS bucket,
                   CAST(SUM(CASE WHEN e.event_type = 'policy.blocked' THEN 1 ELSE 0 END) AS REAL) / NULLIF(COUNT(*), 0) AS value
            FROM events AS e
            WHERE e.ts >= ? AND e.ts <= ?
            {w_e}
            GROUP BY {b}
            ORDER BY bucket
            """
        params = [from_ts, to_ts] + p_e
    elif metric == "low_top1_proxy_rate":
        # Нет отдельных событий с top1 в БД — стабильные нули по бакетам run.finish
        q = f"""
            SELECT {bucket_sql} AS bucket, 0.0 AS value
            FROM events AS rf
            WHERE rf.event_type = 'run.finish' AND rf.ts >= ? AND rf.ts <= ?
            {w_rf}
            GROUP BY {bucket_sql}
            ORDER BY bucket
            """
    else:
        return []

    rows = conn.execute(q, params).fetchall()
    return [{"bucket": row["bucket"], "value": row["value"]} for row in rows]


def get_tools(
    conn: sqlite3.Connection,
    from_ts: str,
    to_ts: str,
    service: str | None = None,
) -> list[dict[str, Any]]:
    """По каждому tool_name: call_count, p95_latency_ms, error_rate, block_rate."""
    from_ts = _normalize_ts(from_ts)
    to_ts = _normalize_ts(to_ts)
    w, p = _where_clause(service)
    params = [from_ts, to_ts] + p
    q = """
        SELECT
            tool_name,
            COUNT(*) AS call_count,
            AVG(duration_ms) AS avg_latency_ms,
            SUM(CASE WHEN status IN ('error', 'failed') THEN 1 ELSE 0 END) AS error_count,
            SUM(CASE WHEN status = 'blocked' THEN 1 ELSE 0 END) AS block_count
        FROM events
        WHERE event_type = 'tool.call.finish' AND tool_name IS NOT NULL AND tool_name != '' AND ts >= ? AND ts <= ?
    """ + w + """
        GROUP BY tool_name
        ORDER BY call_count DESC
    """
    rows = conn.execute(q, params).fetchall()
    out = []
    for row in rows:
        total = row["call_count"]
        out.append({
            "tool_name": row["tool_name"],
            "call_count": total,
            "p95_latency_ms": row["avg_latency_ms"],
            "error_rate": round((row["error_count"] or 0) / total, 4) if total else 0.0,
            "block_rate": round((row["block_count"] or 0) / total, 4) if total else 0.0,
        })
    return out


def get_contracts(
    conn: sqlite3.Connection,
    from_ts: str,
    to_ts: str,
    service: str | None = None,
) -> dict[str, Any]:
    """schema_fail_rate, repair_rate, repair_success_rate по событиям schema_validation / repair; finish_reason с run.finish."""
    from_ts = _normalize_ts(from_ts)
    to_ts = _normalize_ts(to_ts)
    w, p = _where_clause(service)
    params = [from_ts, to_ts] + p

    total_schema = conn.execute(
        "SELECT COUNT(*) AS n FROM events WHERE event_type = 'schema_validation' AND ts >= ? AND ts <= ?" + w,
        params,
    ).fetchone()["n"] or 0

    schema_fail = conn.execute(
        """
        SELECT COUNT(*) AS n FROM events
        WHERE event_type = 'schema_validation' AND ts >= ? AND ts <= ?
        """
        + w
        + " AND json_extract(attrs_json, '$.result') = 'fail'",
        params,
    ).fetchone()["n"] or 0

    repair_count = conn.execute(
        """
        SELECT COUNT(*) AS n FROM events
        WHERE event_type = 'repair' AND ts >= ? AND ts <= ?
        """
        + w
        + " AND json_extract(attrs_json, '$.attempted') IN (1, 'true', 'True')",
        params,
    ).fetchone()["n"] or 0

    repair_success = conn.execute(
        """
        SELECT COUNT(*) AS n FROM events
        WHERE event_type = 'repair' AND ts >= ? AND ts <= ?
        """
        + w
        + " AND json_extract(attrs_json, '$.attempted') IN (1, 'true', 'True')"
        + " AND json_extract(attrs_json, '$.success') IN (1, 'true', 'True')",
        params,
    ).fetchone()["n"] or 0

    finish_reason_rows = conn.execute(
        """
        SELECT json_extract(attrs_json, '$.finish_reason') AS reason, COUNT(*) AS cnt
        FROM events
        WHERE event_type = 'run.finish' AND ts >= ? AND ts <= ?
        """
        + w
        + """
        GROUP BY reason
        ORDER BY cnt DESC
        """,
        params,
    ).fetchall()

    finish_reason_dist = [
        {"reason": row["reason"] or "null", "count": row["cnt"]}
        for row in finish_reason_rows
    ]

    return {
        "schema_fail_rate": round(schema_fail / total_schema, 4) if total_schema else 0.0,
        "repair_rate": round(repair_count / total_schema, 4) if total_schema else 0.0,
        "repair_success_rate": round(repair_success / repair_count, 4) if repair_count else 0.0,
        "finish_reason": finish_reason_dist,
    }


def get_runs_list(
    conn: sqlite3.Connection,
    from_ts: str,
    to_ts: str,
    status: str | None = None,
    service: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Список runs (run.finish): trace_id, ts, status, duration_ms, tokens_total, tool_calls, top1_score."""
    from_ts = _normalize_ts(from_ts)
    to_ts = _normalize_ts(to_ts)
    w_rf, p_rf = _service_clause("rf", service)

    insufficient_sql = (
        "(" + _insufficient_exists_sql("rf") + " OR "
        "json_extract(rf.attrs_json, '$.insufficient') IN (1, 'true', 'True') OR "
        "json_extract(rf.attrs_json, '$.finish_reason') IN ('parse_failed', 'error'))"
    )

    status_clause = ""
    status_params: list[Any] = []
    if status == "insufficient":
        status_clause = f" AND {insufficient_sql} "
    elif status:
        status_clause = " AND rf.status = ? "
        status_params = [status]

    q = f"""
        SELECT
            rf.trace_id,
            rf.ts,
            rf.status,
            rf.duration_ms,
            json_extract(rf.attrs_json, '$.tokens_total') AS tokens_total,
            (SELECT COUNT(*) FROM events AS t
             WHERE t.trace_id = rf.trace_id AND t.event_type = 'tool.call.finish'
               AND t.ts >= ? AND t.ts <= ?) AS tool_calls,
            json_extract(rf.attrs_json, '$.top1_score') AS top1_score,
            rf.service
        FROM events AS rf
        WHERE rf.event_type = 'run.finish' AND rf.ts >= ? AND rf.ts <= ?
        {w_rf}
        {status_clause}
        ORDER BY rf.ts DESC
        LIMIT ?
    """
    list_params: list[Any] = (
        [from_ts, to_ts, from_ts, to_ts] + p_rf + status_params + [limit]
    )

    rows = conn.execute(q, list_params).fetchall()
    return [
        {
            "trace_id": row["trace_id"],
            "ts": row["ts"],
            "status": row["status"],
            "duration_ms": row["duration_ms"],
            "tokens_total": row["tokens_total"],
            "tool_calls": row["tool_calls"],
            "top1_score": row["top1_score"],
            "service": row["service"],
        }
        for row in rows
    ]


def get_trace_events(conn: sqlite3.Connection, trace_id: str) -> list[dict[str, Any]]:
    """Все события по trace_id в хронологическом порядке; attrs — dict."""
    rows = conn.execute(
        """
        SELECT ts, trace_id, service, env, event_type, span_id, parent_span_id,
               severity, attrs_json, duration_ms, status, tool_name
        FROM events
        WHERE trace_id = ?
        ORDER BY ts
        """,
        (trace_id,),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        raw = row["attrs_json"]
        attrs: Any
        if raw is None or raw == "":
            attrs = {}
        else:
            try:
                attrs = json.loads(raw)
            except json.JSONDecodeError:
                attrs = {"_raw": raw}
        out.append({
            "ts": row["ts"],
            "trace_id": row["trace_id"],
            "service": row["service"],
            "env": row["env"],
            "event_type": row["event_type"],
            "span_id": row["span_id"],
            "parent_span_id": row["parent_span_id"],
            "severity": row["severity"],
            "attrs": attrs,
            "duration_ms": row["duration_ms"],
            "status": row["status"],
            "tool_name": row["tool_name"],
        })
    return out
