"""POST /v1/events/batch: приём, валидация, INSERT батчем."""
import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends

from audit_service.database import get_connection
from audit_service.schemas import AuditEventIn, EventsBatchIn, EventsBatchOut
from audit_service.settings import Settings

log = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/events", tags=["ingest"])


def _get_settings() -> Settings:
    return Settings()


def _denormalize_attrs(attrs: dict) -> tuple[int | None, str | None, str | None]:
    """Извлекает duration_ms, status, tool_name из attrs для индексов."""
    duration_ms = attrs.get("duration_ms")
    if duration_ms is not None and not isinstance(duration_ms, int):
        try:
            duration_ms = int(duration_ms)
        except (TypeError, ValueError):
            duration_ms = None
    status = attrs.get("status")
    if status is not None and not isinstance(status, str):
        status = str(status)
    tool_name = attrs.get("tool_name")
    if tool_name is not None and not isinstance(tool_name, str):
        tool_name = str(tool_name)
    return duration_ms, status, tool_name


def _event_to_row(e: AuditEventIn) -> tuple:
    """Преобразует событие в строку для INSERT."""
    ts_str = e.ts.isoformat() if isinstance(e.ts, datetime) else str(e.ts)
    attrs_json = json.dumps(e.attrs) if e.attrs else "{}"
    duration_ms, status, tool_name = _denormalize_attrs(e.attrs)
    return (
        ts_str,
        e.trace_id,
        e.service,
        e.env,
        e.event_type,
        e.span_id,
        e.parent_span_id,
        e.severity,
        attrs_json,
        duration_ms,
        status,
        tool_name,
    )


@router.post("/batch", response_model=EventsBatchOut)
def post_events_batch(body: EventsBatchIn, settings: Settings = Depends(_get_settings)):
    """
    Принимает пачку событий, валидация через Pydantic уже выполнена.
    INSERT одной транзакцией. Денормализация duration_ms, status, tool_name из attrs.
    """
    if not body.events:
        return EventsBatchOut(accepted=0, rejected=0)

    conn = get_connection(settings.audit_db_path)
    try:
        rows = [_event_to_row(e) for e in body.events]
        conn.executemany(
            """
            INSERT INTO events (
                ts, trace_id, service, env, event_type, span_id, parent_span_id,
                severity, attrs_json, duration_ms, status, tool_name
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()
        accepted = len(rows)
        log.debug("ingested batch of %d events", accepted)
        return EventsBatchOut(accepted=accepted, rejected=0)
    except Exception as e:
        conn.rollback()
        log.exception("batch insert failed: %s", e)
        raise
    finally:
        conn.close()
