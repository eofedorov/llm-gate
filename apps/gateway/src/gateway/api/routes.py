"""Старые эндпоинты API."""
import logging

import httpx
from fastapi import APIRouter, HTTPException, Response

from gateway.settings import Settings

router = APIRouter()
logger = logging.getLogger(__name__)
_settings = Settings()


@router.get("/prompts")
async def list_prompts():
    """Проксировать список доступных промптов из orchestrator."""
    url = (_settings.orchestrator_url or "").rstrip("/") + "/prompts"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url)
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"orchestrator: {e}") from e
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        media_type=resp.headers.get("content-type"),
    )
