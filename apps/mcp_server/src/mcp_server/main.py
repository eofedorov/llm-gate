"""Точка входа MCP-сервера: Streamable HTTP на порту 8001."""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Route

from mcp_server.app import mcp

import mcp_server.tools  # noqa: F401

_audit_client_started = False


async def _ensure_audit_client(request, call_next):
    global _audit_client_started
    if not _audit_client_started:
        from mcp_server.settings import Settings
        from audit import AuditClient, set_global_client
        s = Settings()
        if s.audit_service_url:
            client = AuditClient(s.audit_service_url, service="mcp_server", env="dev")
            set_global_client(client)
            await client.start()
        _audit_client_started = True
    return await call_next(request)


class EnsureAuditClientMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        return await _ensure_audit_client(request, call_next)


async def _health(_):
    return JSONResponse({"status": "ok"})


app = mcp.streamable_http_app()
app.routes.insert(0, Route("/health", _health, methods=["GET"]))
from audit import AuditMiddleware
app.add_middleware(AuditMiddleware)
app.add_middleware(EnsureAuditClientMiddleware)
