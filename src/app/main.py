"""Точка входа FastAPI."""
import logging

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.api import routes_rag
from app.mcp.client.mcp_client import MCPConnectionError, MCPToolError

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logging.getLogger("app").setLevel(logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

app = FastAPI(title="LLM-Gate", description="AI-шлюз для инженерных задач")
app.include_router(router, prefix="", tags=["run"])
app.include_router(routes_rag.router, prefix="/rag", tags=["rag"])


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
