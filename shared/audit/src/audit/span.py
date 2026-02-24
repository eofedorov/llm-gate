"""@audited_span decorator and audit_event() for instant events."""

import asyncio
import functools
import time
from datetime import datetime
from typing import Any, Callable, TypeVar

from audit.context import get_span_id, get_trace_id, set_span_id
from audit.schemas import AuditEvent

F = TypeVar("F", bound=Callable[..., Any])

# Module-level client; set by app (e.g. middleware) via set_global_client
_global_client: Any = None


def set_global_client(client: Any) -> None:
    """Set the global AuditClient used by audit_event and @audited_span."""
    global _global_client
    _global_client = client


def get_global_client() -> Any:
    """Get the global AuditClient (may be None)."""
    return _global_client


async def _emit(event: AuditEvent) -> None:
    client = get_global_client()
    if client is not None:
        await client.emit(event)


def audit_event(
    event_type: str,
    *,
    severity: str = "info",
    **attrs: Any,
) -> None:
    """
    Emit an instant audit event (no span). Uses current trace_id/span_id from context.
    Schedules emit on the running event loop; no-op if no loop (e.g. sync test).
    """
    client = get_global_client()
    if client is None:
        return
    ev = AuditEvent(
        ts=datetime.utcnow(),
        trace_id=get_trace_id(),
        service=getattr(client, "_service", "unknown"),
        env=getattr(client, "_env", "dev"),
        event_type=event_type,
        span_id=get_span_id(),
        parent_span_id=None,
        severity=severity,
        attrs=attrs,
    )
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_emit(ev))
    except RuntimeError:
        pass


def audited_span(
    name: str,
    *,
    kind: str = "span",
    attrs: dict[str, Any] | None = None,
) -> Callable[[F], F]:
    """
    Decorator: record span start, then on exit record finish with duration_ms,
    status (ok/error), and optional error message. Uses context span_id.
    """

    def decorator(f: F) -> F:
        @functools.wraps(f)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            parent_span = get_span_id()
            span_id = set_span_id()
            client = get_global_client()
            start = time.perf_counter()
            status = "ok"
            error_msg: str | None = None
            try:
                if client is not None:
                    ev_start = AuditEvent(
                        ts=datetime.utcnow(),
                        trace_id=get_trace_id(),
                        service=getattr(client, "_service", "unknown"),
                        env=getattr(client, "_env", "dev"),
                        event_type=f"{kind}.start",
                        span_id=span_id,
                        parent_span_id=parent_span,
                        severity="info",
                        attrs={**(attrs or {}), "name": name},
                    )
                    await client.emit(ev_start)
                result = await f(*args, **kwargs)
                return result
            except Exception as e:
                status = "error"
                error_msg = str(e)
                raise
            finally:
                duration_ms = int((time.perf_counter() - start) * 1000)
                if client is not None:
                    ev_finish = AuditEvent(
                        ts=datetime.utcnow(),
                        trace_id=get_trace_id(),
                        service=getattr(client, "_service", "unknown"),
                        env=getattr(client, "_env", "dev"),
                        event_type=f"{kind}.finish",
                        span_id=span_id,
                        parent_span_id=parent_span,
                        severity="error" if status != "ok" else "info",
                        attrs={
                            **(attrs or {}),
                            "name": name,
                            "duration_ms": duration_ms,
                            "status": status,
                            **({"error": error_msg} if error_msg else {}),
                        },
                    )
                    await client.emit(ev_finish)

        @functools.wraps(f)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            parent_span = get_span_id()
            span_id = set_span_id()
            client = get_global_client()
            start = time.perf_counter()
            status = "ok"
            error_msg = None
            try:
                if client is not None:
                    ev_start = AuditEvent(
                        ts=datetime.utcnow(),
                        trace_id=get_trace_id(),
                        service=getattr(client, "_service", "unknown"),
                        env=getattr(client, "_env", "dev"),
                        event_type=f"{kind}.start",
                        span_id=span_id,
                        parent_span_id=parent_span,
                        severity="info",
                        attrs={**(attrs or {}), "name": name},
                    )
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(client.emit(ev_start))
                    except RuntimeError:
                        pass
                result = f(*args, **kwargs)
                return result
            except Exception as e:
                status = "error"
                error_msg = str(e)
                raise
            finally:
                duration_ms = int((time.perf_counter() - start) * 1000)
                if client is not None:
                    ev_finish = AuditEvent(
                        ts=datetime.utcnow(),
                        trace_id=get_trace_id(),
                        service=getattr(client, "_service", "unknown"),
                        env=getattr(client, "_env", "dev"),
                        event_type=f"{kind}.finish",
                        span_id=span_id,
                        parent_span_id=parent_span,
                        severity="error" if status != "ok" else "info",
                        attrs={
                            **(attrs or {}),
                            "name": name,
                            "duration_ms": duration_ms,
                            "status": status,
                            **({"error": error_msg} if error_msg else {}),
                        },
                    )
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(client.emit(ev_finish))
                    except RuntimeError:
                        pass

        if asyncio.iscoroutinefunction(f):
            return async_wrapper  # type: ignore[return-value]
        return sync_wrapper  # type: ignore[return-value]

    return decorator
