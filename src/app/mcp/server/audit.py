"""Аудит вызовов инструментов: Python logging и запись в llm.tool_calls (Postgres)."""
import json
import logging
from uuid import UUID

from app.db.connection import get_pool
from app.db.queries import log_tool_call as db_log_tool_call

logger = logging.getLogger(__name__)


def log_tool_call(
    tool_name: str,
    args: dict,
    result_meta: dict,
    status: str = "ok",
    error_message: str | None = None,
    duration_ms: int | None = None,
    run_id: UUID | str | None = None,
) -> None:
    """Логировать вызов инструмента: structured logging и при наличии run_id — запись в llm.tool_calls."""
    logger.info(
        "tool_call tool_name=%s status=%s duration_ms=%s run_id=%s",
        tool_name,
        status,
        duration_ms,
        run_id,
        extra={
            "tool_name": tool_name,
            "args": args,
            "result_meta": result_meta,
            "status": status,
            "error_message": error_message,
            "duration_ms": duration_ms,
        },
    )
    if run_id is None:
        return
    try:
        uid = UUID(str(run_id)) if isinstance(run_id, str) else run_id
    except (ValueError, TypeError) as e:
        logger.error("invalid run_id for audit: %s", e)
        return
    try:
        pool = get_pool()
        with pool.connection() as conn:
            db_log_tool_call(
                conn,
                run_id=uid,
                tool_name=tool_name,
                args=args,
                result_meta=result_meta,
                status=status,
                error_message=error_message,
                duration_ms=duration_ms,
            )
            conn.commit()
    except Exception as e:
        logger.error("audit db log_tool_call failed: %s", e)
