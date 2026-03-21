"""Точка входа FastAPI."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from audit import AuditMiddleware
from orchestrator.api.routes import router
from orchestrator.api import routes_rag, routes_run
from orchestrator.mcp.client.mcp_client import MCPConnectionError, MCPToolError
from orchestrator.settings import Settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logging.getLogger("orchestrator").setLevel(logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("mcp.client.streamable_http").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
    if settings.audit_service_url:
        from audit import AuditClient, set_global_client
        client = AuditClient(
            settings.audit_service_url,
            service="orchestrator",
            env=getattr(settings, "env", "dev"),
        )
        set_global_client(client)
        await client.start()
    try:
        yield
    finally:
        from audit.span import get_global_client
        from audit import set_global_client as _set_global_client
        client = get_global_client()
        if client is not None:
            await client.stop()
            _set_global_client(None)


app = FastAPI(title="LLM-Orchestrator", description="Оркестратор AI-задач", lifespan=lifespan)
app.add_middleware(AuditMiddleware)
app.include_router(router, prefix="", tags=["run"])
app.include_router(routes_run.router, prefix="/run", tags=["run"])
app.include_router(routes_rag.router, prefix="/rag", tags=["rag"])


@app.get("/health")
def health():
    return {"status": "ok"}


@app.exception_handler(MCPConnectionError)
def handle_mcp_connection_error(_request, exc: MCPConnectionError):
    return JSONResponse(
        status_code=503,
        content={"detail": str(exc)},
    )


@app.exception_handler(MCPToolError)
def handle_mcp_tool_error(_request, exc: MCPToolError):
    return JSONResponse(
        status_code=503,
        content={"detail": str(exc)},
    )
