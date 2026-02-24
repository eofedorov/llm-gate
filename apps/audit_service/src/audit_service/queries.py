"""SQL-запросы для метрик и drill-down по events."""
from __future__ import annotations

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


def get_overview(
    conn: sqlite3.Connection,
    from_ts: str,
    to_ts: str,
    service: str | None = None,
) -> dict[str, Any]:
    """
    KPI по run.finish: total_runs, ok_rate, error_rate, insufficient_rate,
    p95_latency_ms, avg_tokens, avg_tool_calls.
    """
    from_ts = _normalize_ts(from_ts)
    to_ts = _normalize_ts(to_ts)
    w, p = _where_clause(service)
    params = [from_ts, to_ts] + p
    base = """
        SELECT
            COUNT(*) AS total_runs,
            SUM(CASE WHEN status = 'ok' THEN 1 ELSE 0 END) AS ok_count,
            SUM(CASE WHEN status = 'error' OR status = 'failed' THEN 1 ELSE 0 END) AS error_count,
            AVG(duration_ms) AS avg_latency_ms,
            AVG(CAST(json_extract(attrs_json, '$.tokens_total') AS REAL)) AS avg_tokens,
            AVG(CAST(json_extract(attrs_json, '$.tool_calls') AS REAL)) AS avg_tool_calls,
            SUM(CASE WHEN json_extract(attrs_json, '$.insufficient') = 1 OR json_extract(attrs_json, '$.insufficient') = true THEN 1 ELSE 0 END) AS insufficient_count
        FROM events
        WHERE event_type = 'run.finish' AND ts >= ? AND ts <= ?
    """ + w
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

    # p95 latency: fetch ordered durations and take 95th percentile in Python
    p95_params = [from_ts, to_ts] + p
    durations = [
        r[0]
        for r in conn.execute(
            """
            SELECT duration_ms FROM events
            WHERE event_type = 'run.finish' AND duration_ms IS NOT NULL AND ts >= ? AND ts <= ?
            """ + w + " ORDER BY duration_ms",
            p95_params,
        ).fetchall()
    ]
    p95_val = None
    if durations:
        idx = max(0, int(len(durations) * 0.95) - 1)
        p95_val = durations[idx]

    return {
        "total_runs": total,
        "ok_rate": round(ok_rate, 4),
        "error_rate": round(error_rate, 4),
        "insufficient_rate": round(insufficient_rate, 4),
        "p95_latency_ms": p95_val,
        "avg_tokens": round(row["avg_tokens"], 2) if row["avg_tokens"] is not None else None,
        "avg_tool_calls": round(row["avg_tool_calls"], 2) if row["avg_tool_calls"] is not None else None,
    }


def _bucket_expr(interval: str) -> str:
    """Возвращает SQL-выражение для группировки по интервалу (например 5m -> 300 сек)."""
    if interval == "1m":
        return "strftime('%Y-%m-%d %H:%M', ts)"
    if interval == "5m":
        return "datetime((strftime('%s', ts) / 300) * 300, 'unixepoch')"
    if interval == "1h":
        return "strftime('%Y-%m-%d %H:00', ts)"
    return "datetime((strftime('%s', ts) / 300) * 300, 'unixepoch')"


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
    tool_calls_avg, insufficient_rate, schema_fail_rate, repair_rate, policy_block_rate.
    """
    from_ts = _normalize_ts(from_ts)
    to_ts = _normalize_ts(to_ts)
    bucket_sql = _bucket_expr(interval)
    w, p = _where_clause(service)
    params = [from_ts, to_ts] + p

    if metric == "run_ok_rate":
        q = f"""
            SELECT {bucket_sql} AS bucket,
                   CAST(SUM(CASE WHEN status = 'ok' THEN 1 ELSE 0 END) AS REAL) / NULLIF(COUNT(*), 0) AS value
            FROM events
            WHERE event_type = 'run.finish' AND ts >= ? AND ts <= ?
            """ + w + f"""
            GROUP BY {bucket_sql}
            ORDER BY bucket
            """
    elif metric == "run_p95_latency_ms":
        # По bucket нужен p95 — упрощённо: среднее по бакету
        q = f"""
            SELECT {bucket_sql} AS bucket, AVG(duration_ms) AS value
            FROM events
            WHERE event_type = 'run.finish' AND duration_ms IS NOT NULL AND ts >= ? AND ts <= ?
            """ + w + f"""
            GROUP BY {bucket_sql}
            ORDER BY bucket
            """
    elif metric == "tokens_avg":
        q = f"""
            SELECT {bucket_sql} AS bucket, AVG(CAST(json_extract(attrs_json, '$.tokens_total') AS REAL)) AS value
            FROM events
            WHERE event_type = 'run.finish' AND ts >= ? AND ts <= ?
            """ + w + f"""
            GROUP BY {bucket_sql}
            ORDER BY bucket
            """
    elif metric == "tool_calls_avg":
        q = f"""
            SELECT {bucket_sql} AS bucket, AVG(CAST(json_extract(attrs_json, '$.tool_calls') AS REAL)) AS value
            FROM events
            WHERE event_type = 'run.finish' AND ts >= ? AND ts <= ?
            """ + w + f"""
            GROUP BY {bucket_sql}
            ORDER BY bucket
            """
    elif metric == "insufficient_rate":
        q = f"""
            SELECT {bucket_sql} AS bucket,
                   CAST(SUM(CASE WHEN json_extract(attrs_json, '$.insufficient') IN (1, true) THEN 1 ELSE 0 END) AS REAL) / NULLIF(COUNT(*), 0) AS value
            FROM events
            WHERE event_type = 'run.finish' AND ts >= ? AND ts <= ?
            """ + w + f"""
            GROUP BY {bucket_sql}
            ORDER BY bucket
            """
    elif metric == "schema_fail_rate":
        q = f"""
            SELECT {bucket_sql} AS bucket,
                   CAST(SUM(CASE WHEN json_extract(attrs_json, '$.schema_validation') = 'fail' THEN 1 ELSE 0 END) AS REAL) / NULLIF(COUNT(*), 0) AS value
            FROM events
            WHERE event_type IN ('run.finish', 'llm.call.finish') AND ts >= ? AND ts <= ?
            """ + w + f"""
            GROUP BY {bucket_sql}
            ORDER BY bucket
            """
    elif metric == "repair_rate":
        q = f"""
            SELECT {bucket_sql} AS bucket,
                   CAST(SUM(CASE WHEN json_extract(attrs_json, '$.repair') = 1 OR json_extract(attrs_json, '$.repair') = true THEN 1 ELSE 0 END) AS REAL) / NULLIF(COUNT(*), 0) AS value
            FROM events
            WHERE event_type IN ('run.finish', 'llm.call.finish') AND ts >= ? AND ts <= ?
            """ + w + f"""
            GROUP BY {bucket_sql}
            ORDER BY bucket
            """
    elif metric == "policy_block_rate":
        q = f"""
            SELECT {bucket_sql} AS bucket,
                   CAST(SUM(CASE WHEN event_type = 'policy.blocked' THEN 1 ELSE 0 END) AS REAL) / NULLIF(COUNT(*), 0) AS value
            FROM events
            WHERE ts >= ? AND ts <= ?
            """ + w + f"""
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
            SUM(CASE WHEN status = 'error' OR status = 'failed' THEN 1 ELSE 0 END) AS error_count,
            SUM(CASE WHEN json_extract(attrs_json, '$.blocked') = 1 OR json_extract(attrs_json, '$.blocked') = true THEN 1 ELSE 0 END) AS block_count
        FROM events
        WHERE tool_name IS NOT NULL AND tool_name != '' AND ts >= ? AND ts <= ?
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
            "p95_latency_ms": row["avg_latency_ms"],  # упрощённо avg вместо p95
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
    """schema_fail_rate, repair_rate, repair_success_rate, finish_reason distribution."""
    from_ts = _normalize_ts(from_ts)
    to_ts = _normalize_ts(to_ts)
    w, p = _where_clause(service)
    params = [from_ts, to_ts] + p

    total_finish = conn.execute(
        "SELECT COUNT(*) AS n FROM events WHERE event_type = 'run.finish' AND ts >= ? AND ts <= ?" + w,
        params,
    ).fetchone()["n"] or 0

    schema_fail = conn.execute(
        """
        SELECT COUNT(*) AS n FROM events
        WHERE event_type IN ('run.finish', 'llm.call.finish') AND ts >= ? AND ts <= ?
        """ + w + " AND json_extract(attrs_json, '$.schema_validation') = 'fail'",
        params,
    ).fetchone()["n"] or 0

    repair_count = conn.execute(
        """
        SELECT COUNT(*) AS n FROM events
        WHERE event_type IN ('run.finish', 'llm.call.finish') AND ts >= ? AND ts <= ?
        """ + w + " AND (json_extract(attrs_json, '$.repair') = 1 OR json_extract(attrs_json, '$.repair') = true)",
        params,
    ).fetchone()["n"] or 0

    repair_success = conn.execute(
        """
        SELECT COUNT(*) AS n FROM events
        WHERE event_type IN ('run.finish', 'llm.call.finish') AND ts >= ? AND ts <= ?
        """ + w + " AND (json_extract(attrs_json, '$.repair') = 1 OR json_extract(attrs_json, '$.repair') = true)"
        + " AND json_extract(attrs_json, '$.repair_success') IN (1, true)",
        params,
    ).fetchone()["n"] or 0

    total_checked = conn.execute(
        "SELECT COUNT(*) AS n FROM events WHERE event_type IN ('run.finish', 'llm.call.finish') AND ts >= ? AND ts <= ?" + w,
        params,
    ).fetchone()["n"] or 0

    finish_reason_rows = conn.execute(
        """
        SELECT json_extract(attrs_json, '$.finish_reason') AS reason, COUNT(*) AS cnt
        FROM events
        WHERE event_type = 'run.finish' AND ts >= ? AND ts <= ?
        """ + w + """
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
        "schema_fail_rate": round(schema_fail / total_checked, 4) if total_checked else 0.0,
        "repair_rate": round(repair_count / total_checked, 4) if total_checked else 0.0,
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
    w, p = _where_clause(service)
    if status:
        w += " AND status = ? "
    params: list[Any] = [from_ts, to_ts] + p + ([status] if status else []) + [limit]
    q = """
        SELECT
            trace_id,
            ts,
            status,
            duration_ms,
            json_extract(attrs_json, '$.tokens_total') AS tokens_total,
            json_extract(attrs_json, '$.tool_calls') AS tool_calls,
            json_extract(attrs_json, '$.top1_score') AS top1_score,
            service
        FROM events
        WHERE event_type = 'run.finish' AND ts >= ? AND ts <= ?
    """ + w + """
        ORDER BY ts DESC
        LIMIT ?
    """
    rows = conn.execute(q, params).fetchall()
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
    """Все события по trace_id в хронологическом порядке."""
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
    return [
        {
            "ts": row["ts"],
            "trace_id": row["trace_id"],
            "service": row["service"],
            "env": row["env"],
            "event_type": row["event_type"],
            "span_id": row["span_id"],
            "parent_span_id": row["parent_span_id"],
            "severity": row["severity"],
            "attrs": row["attrs_json"],
            "duration_ms": row["duration_ms"],
            "status": row["status"],
            "tool_name": row["tool_name"],
        }
        for row in rows
    ]
