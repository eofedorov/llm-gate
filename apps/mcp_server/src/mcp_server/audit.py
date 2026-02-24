"""Аудит вызовов инструментов через audit-lib (HTTP в audit-service). Реэкспорт и хелперы."""

from audit import audit_event

__all__ = ["audit_event"]


def log_tool_call(
    tool_name: str,
    args: dict,
    result_meta: dict,
    status: str = "ok",
    error_message: str | None = None,
    duration_ms: int | None = None,
    run_id: str | None = None,
) -> None:
    """Отправить событие вызова инструмента в audit-service (для обратной совместимости)."""
    attrs = {
        "tool_name": tool_name,
        "args": args,
        "result_meta": result_meta,
        "status": status,
    }
    if error_message is not None:
        attrs["error_message"] = error_message
    if duration_ms is not None:
        attrs["duration_ms"] = duration_ms
    if run_id is not None:
        attrs["run_id"] = str(run_id)
    audit_event("tool.call.finish", **attrs)
