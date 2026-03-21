import logging

import httpx
from fastapi import APIRouter, HTTPException, Request, Response

from gateway.settings import Settings


logger = logging.getLogger(__name__)
router = APIRouter()
_settings = Settings()


@router.post("/{prompt_name}")
async def run_prompt(prompt_name: str, request: Request):
    """Проксировать выполнение промпта в orchestrator."""
    url = (_settings.orchestrator_url or "").rstrip("/") + f"/run/{prompt_name}"
    body = await request.body()
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                url,
                content=body,
                headers={"content-type": request.headers.get("content-type", "application/json")},
            )
    except httpx.RequestError as e:
        logger.error("orchestrator proxy failed for prompt=%s: %s", prompt_name, e)
        raise HTTPException(status_code=502, detail=f"orchestrator: {e}") from e
    media_type = resp.headers.get("content-type")
    return Response(content=resp.content, status_code=resp.status_code, media_type=media_type)

