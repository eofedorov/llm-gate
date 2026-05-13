"""Точка входа MCP-сервера: Streamable HTTP на порту 8001."""
from starlette.responses import JSONResponse
from starlette.routing import Route

from mcp_server.app import mcp

import mcp_server.tools  # noqa: F401


async def _mcp_audit_startup() -> None:
    """Инициализация audit-клиента до приёма запросов (run.start в middleware)."""
    from audit import AuditClient, set_global_client
    from mcp_server.settings import Settings

    s = Settings()
    if not s.audit_service_url:
        return
    client = AuditClient(s.audit_service_url, service="mcp_server", env="dev")
    set_global_client(client)
    await client.start()


async def _mcp_audit_shutdown() -> None:
    from audit import set_global_client as _set_global_client
    from audit.span import get_global_client

    client = get_global_client()
    if client is not None:
        await client.stop()
        _set_global_client(None)


async def _health(_):
    return JSONResponse({"status": "ok"})


app = mcp.streamable_http_app()
app.routes.insert(0, Route("/health", _health, methods=["GET"]))

app.add_event_handler("startup", _mcp_audit_startup)
app.add_event_handler("shutdown", _mcp_audit_shutdown)

from audit import AuditMiddleware  # noqa: E402

app.add_middleware(AuditMiddleware)
