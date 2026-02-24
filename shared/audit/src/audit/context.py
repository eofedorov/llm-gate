"""Context variables for trace_id and span_id; helpers for propagation."""

import uuid
from contextvars import ContextVar

trace_id_var: ContextVar[str | None] = ContextVar("trace_id", default=None)
span_id_var: ContextVar[str | None] = ContextVar("span_id", default=None)


def set_trace_id(trace_id: str | None = None) -> str:
    """Set trace_id in context. If None, generate new UUID. Returns the set value."""
    value = trace_id or str(uuid.uuid4())
    trace_id_var.set(value)
    return value


def get_trace_id() -> str:
    """Get current trace_id; generate and set if not present."""
    current = trace_id_var.get()
    if current is None:
        return set_trace_id()
    return current


def set_span_id(span_id: str | None = None) -> str:
    """Set span_id in context. If None, generate new UUID. Returns the set value."""
    value = span_id or str(uuid.uuid4())
    span_id_var.set(value)
    return value


def get_span_id() -> str:
    """Get current span_id; generate and set if not present."""
    current = span_id_var.get()
    if current is None:
        return set_span_id()
    return current


def clear_trace_context() -> None:
    """Clear trace_id and span_id from context (e.g. for tests)."""
    trace_id_var.set(None)
    span_id_var.set(None)
