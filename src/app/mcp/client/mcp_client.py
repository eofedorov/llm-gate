"""Синхронный MCP-клиент: подключение к Streamable HTTP, list_tools, call_tool."""
import asyncio
import json
import logging
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app.settings import Settings

logger = logging.getLogger(__name__)


class MCPConnectionError(Exception):
    """MCP-сервер недоступен (не запущен или сеть недоступна)."""

    def __init__(self, url: str, cause: Exception | None = None):
        self.url = url
        self.cause = cause
        super().__init__(f"MCP-сервер недоступен: {url}. Убедитесь, что сервер запущен.")


def _run_async(coro):
    """Выполнить корутину из синхронного кода (любой поток)."""
    return asyncio.run(coro)


def _format_mcp_error(exc: BaseException) -> str:
    """Читаемое сообщение об ошибке (в т.ч. из ExceptionGroup)."""
    if isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        return _format_mcp_error(exc.exceptions[0])
    return str(exc)


def _raise_if_connection_error(url: str, exc: BaseException) -> None:
    """Перевести ошибку соединения с MCP в MCPConnectionError."""
    if isinstance(exc, httpx.ConnectError):
        raise MCPConnectionError(url, exc) from exc
    if isinstance(exc, BaseExceptionGroup):
        for e in exc.exceptions:
            if isinstance(e, httpx.ConnectError):
                raise MCPConnectionError(url, e) from exc


def list_tools(mcp_url: str | None = None) -> list[dict[str, Any]]:
    """
    Подключиться к MCP-серверу, получить список инструментов.
    Возвращает список в формате OpenAI tools: [{"type": "function", "function": {"name", "description", "parameters"}}].
    """
    url = Settings().mcp_server_url if mcp_url is None else mcp_url
    if not url:
        logger.warning("mcp_server_url not set, returning empty tools")
        return []

    async def _list():
        async with streamable_http_client(url) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                response = await session.list_tools()
                return list(response.tools) if response.tools else []

    try:
        mcp_tools = _run_async(_list())
    except (httpx.ConnectError, BaseExceptionGroup) as e:
        logger.error("MCP connection failed (list_tools) url=%s: %s", url, _format_mcp_error(e))
        _raise_if_connection_error(url, e)
        raise
    openai_tools: list[dict[str, Any]] = []
    for t in mcp_tools:
        name = getattr(t, "name", None) or ""
        description = getattr(t, "description", None) or ""
        input_schema = getattr(t, "inputSchema", None) or {}
        openai_tools.append({
            "type": "function",
            "function": {
                "name": name,
                "description": description or name,
                "parameters": input_schema if isinstance(input_schema, dict) else {},
            },
        })
    return openai_tools


def call_tool(
    name: str,
    arguments: dict[str, Any],
    mcp_url: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """
    Вызвать инструмент MCP по имени с аргументами.
    При переданном run_id добавляет его в arguments для аудита на сервере.
    Возвращает JSON-результат (dict).
    """
    url = Settings().mcp_server_url if mcp_url is None else mcp_url
    if not url:
        raise RuntimeError("mcp_server_url not set")

    args = dict(arguments)
    if run_id is not None:
        args["run_id"] = str(run_id)

    async def _call():
        async with streamable_http_client(url) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(name, arguments=args)
                if getattr(result, "isError", False):
                    err = getattr(result, "content", [])
                    err_text = err[0].text if err and hasattr(err[0], "text") else "unknown error"
                    raise RuntimeError(f"MCP tool error: {err_text}")
                if hasattr(result, "structuredContent") and result.structuredContent is not None:
                    return result.structuredContent
                content = getattr(result, "content", []) or []
                if not content:
                    return {}
                first = content[0]
                if hasattr(first, "text"):
                    text = first.text
                    try:
                        return json.loads(text)
                    except json.JSONDecodeError as e:
                        logger.error("MCP tool response JSON decode error: %s", e)
                        return {"result": text}
                return {}

    try:
        return _run_async(_call())
    except (httpx.ConnectError, BaseExceptionGroup) as e:
        logger.error(
            "MCP connection failed (call_tool) url=%s name=%s: %s",
            url,
            name,
            _format_mcp_error(e),
        )
        _raise_if_connection_error(url, e)
        raise
