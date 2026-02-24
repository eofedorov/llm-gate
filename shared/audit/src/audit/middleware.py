"""FastAPI/Starlette middleware: trace_id propagation, run.start / run.finish events."""

import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from audit.context import set_trace_id
from audit.span import audit_event

TRACE_HEADER = "X-Trace-Id"


class AuditMiddleware(BaseHTTPMiddleware):
    """
    On request: read or generate trace_id, set in context, emit run.start.
    On response: emit run.finish (status, duration_ms), add X-Trace-Id to response.
    """

    async def dispatch(self, request: Request, call_next: callable) -> Response:
        trace_id = set_trace_id(request.headers.get(TRACE_HEADER))
        request.state.trace_id = trace_id

        audit_event("run.start", path=request.url.path, method=request.method)

        start = time.perf_counter()
        status = "ok"
        response = None
        try:
            response = await call_next(request)
            status = "ok" if response.status_code < 400 else "error"
            return response
        except Exception:
            status = "error"
            raise
        finally:
            duration_ms = int((time.perf_counter() - start) * 1000)
            audit_event("run.finish", status=status, duration_ms=duration_ms)
            if response is not None and TRACE_HEADER not in response.headers:
                response.headers[TRACE_HEADER] = trace_id
