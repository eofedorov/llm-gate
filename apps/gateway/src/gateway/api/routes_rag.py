"""RAG API: тонкий прокси в orchestrator."""
import logging

import httpx
from fastapi import APIRouter, File, HTTPException, Query, Request, Response, UploadFile

from gateway.settings import Settings

router = APIRouter()
logger = logging.getLogger(__name__)
_settings = Settings()


@router.post("/upload")
async def post_upload(files: list[UploadFile] = File(...)):
    """Проксировать upload в orchestrator."""
    url = (_settings.orchestrator_url or "").rstrip("/") + "/rag/upload"
    parts = []
    for uf in files:
        body = await uf.read()
        name = uf.filename or "document.json"
        parts.append(("files", (name, body, "application/json")))
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, files=parts)
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"orchestrator: {e}") from e
    return Response(content=resp.content, status_code=resp.status_code, media_type=resp.headers.get("content-type"))


@router.post("/ingest")
async def post_ingest():
    """Проксировать ingest в orchestrator."""
    url = (_settings.orchestrator_url or "").rstrip("/") + "/rag/ingest"
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url)
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"orchestrator: {e}") from e
    return Response(content=resp.content, status_code=resp.status_code, media_type=resp.headers.get("content-type"))


@router.get("/search")
async def get_search(
    q: str = Query(..., min_length=1),
    k: int = Query(default=5, ge=1, le=20),
    debug: bool = Query(default=False),
):
    """Проксировать search в orchestrator."""
    url = (_settings.orchestrator_url or "").rstrip("/") + "/rag/search"
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.get(url, params={"q": q, "k": k, "debug": debug})
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"orchestrator: {e}") from e
    return Response(content=resp.content, status_code=resp.status_code, media_type=resp.headers.get("content-type"))


@router.post("/ask")
async def post_ask(request: Request, debug: bool = Query(default=False)):
    """Проксировать ask в orchestrator."""
    url = (_settings.orchestrator_url or "").rstrip("/") + "/rag/ask"
    body = await request.body()
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                url,
                params={"debug": debug},
                content=body,
                headers={"content-type": request.headers.get("content-type", "application/json")},
            )
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"orchestrator: {e}") from e
    return Response(content=resp.content, status_code=resp.status_code, media_type=resp.headers.get("content-type"))
