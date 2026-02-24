"""Audit library: context, schemas, client, spans, middleware."""

from audit.context import (
    clear_trace_context,
    get_span_id,
    get_trace_id,
    set_span_id,
    set_trace_id,
)
from audit.schemas import AuditEvent
from audit.client import AuditClient
from audit.span import audit_event, audited_span, set_global_client
from audit.middleware import AuditMiddleware

__all__ = [
    "AuditEvent",
    "AuditClient",
    "AuditMiddleware",
    "audit_event",
    "audited_span",
    "set_global_client",
    "set_trace_id",
    "get_trace_id",
    "set_span_id",
    "get_span_id",
    "clear_trace_context",
]
