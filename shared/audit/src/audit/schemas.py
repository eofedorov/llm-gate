"""Unified audit event contract."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AuditEvent(BaseModel):
    """Single audit event sent to audit-service."""

    ts: datetime = Field(default_factory=datetime.utcnow)
    trace_id: str
    service: str
    env: str = "dev"
    event_type: str  # e.g. "run.start", "tool.call.finish"
    span_id: str
    parent_span_id: str | None = None
    severity: str = "info"
    attrs: dict[str, Any] = Field(default_factory=dict)
