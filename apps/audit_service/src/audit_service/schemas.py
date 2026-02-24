"""Pydantic-модели для API audit_service (приём событий и ответы)."""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AuditEventIn(BaseModel):
    """Один событие для POST /v1/events/batch (контракт audit-lib)."""
    ts: datetime
    trace_id: str = Field(..., min_length=1)
    service: str = Field(..., min_length=1)
    env: str = "dev"
    event_type: str = Field(..., min_length=1)
    span_id: str = Field(..., min_length=1)
    parent_span_id: str | None = None
    severity: str = "info"
    attrs: dict[str, Any] = Field(default_factory=dict)


class EventsBatchIn(BaseModel):
    """Тело запроса POST /v1/events/batch."""
    events: list[AuditEventIn] = Field(..., max_length=500)


class EventsBatchOut(BaseModel):
    """Ответ после приёма батча."""
    accepted: int
    rejected: int = 0
