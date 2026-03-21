"""RAG API: POST /upload, POST /ingest, GET /search, POST /ask. Upload — в datastore при заданном datastore_url."""
import logging

import httpx
from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile

from common.contracts.api_schemas import (
    AskRequestBody,
    IngestResponse,
    SearchHit,
    UploadStubResponse,
)
from common.contracts.rag_schemas import AnswerContract
from orchestrator.mcp.client.mcp_client import MCPConnectionError, call_tool_async as mcp_call_tool_async
from orchestrator.services.rag_agent import ask
from orchestrator.settings import Settings

router = APIRouter()
logger = logging.getLogger(__name__)
_settings = Settings()


@router.post("/upload", response_model=UploadStubResponse)
async def post_upload(files: list[UploadFile] = File(...)):
    """При заданном datastore_url — проксирует файлы в datastore POST /upload, затем запускает ingest. Иначе заглушка."""
    count = len(files)
    base = (_settings.datastore_url or "").rstrip("/")
    if base:
        upload_url = base + "/upload"
        logger.info("[RAG] POST /upload proxy to datastore files_count=%s", count)
        parts = []
        for uf in files:
            body = await uf.read()
            name = uf.filename or "document.json"
            parts.append(("files", (name, body, "application/json")))
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(upload_url, files=parts)
        except httpx.RequestError as e:
            logger.error("[RAG] POST /upload datastore request error: %s", e)
            raise HTTPException(status_code=502, detail=f"upload: Datastore unreachable — {e}") from e
        if resp.status_code != 200:
            detail = resp.text
            try:
                data = resp.json()
                if "detail" in data:
                    detail = data["detail"]
            except Exception:
                pass
            logger.warning("[RAG] POST /upload datastore status=%s detail=%s", resp.status_code, detail)
            raise HTTPException(status_code=resp.status_code, detail=f"upload: {detail}")
        data = resp.json()
        uploaded = data.get("uploaded") or []
        out = UploadStubResponse(
            message="Uploaded to datastore",
            files_count=len(uploaded),
        )
        try:
            logger.info("[RAG] POST /upload running ingest after upload")
            result = await mcp_call_tool_async("kb_ingest", {})
            out.ingest_docs_indexed = result.get("docs_indexed")
            out.ingest_chunks_indexed = result.get("chunks_indexed")
            out.ingest_duration_ms = result.get("duration_ms")
            logger.info(
                "[RAG] POST /upload ingest done docs=%s chunks=%s duration_ms=%s",
                out.ingest_docs_indexed, out.ingest_chunks_indexed, out.ingest_duration_ms,
            )
        except MCPConnectionError as e:
            logger.error("[RAG] POST /upload ingest failed: %s", e)
            out.error = f"ingest: MCP unavailable — {e}"
        except Exception as e:
            logger.exception("[RAG] POST /upload ingest failed")
            out.error = f"ingest: {e!s}"
        return out
    logger.info("[RAG] POST /upload stub files_count=%s", count)
    return UploadStubResponse(message="Upload received (stub)", files_count=count)


@router.post("/ingest", response_model=IngestResponse)
async def post_ingest():
    """Индексация через MCP (kb_ingest). Требуется запущенный MCP-сервер."""
    logger.info("[RAG] POST /ingest start (via MCP)")
    try:
        result = await mcp_call_tool_async("kb_ingest", {})
    except MCPConnectionError as e:
        logger.error("[RAG] POST /ingest MCP unavailable: %s", e)
        raise
    logger.info(
        "[RAG] POST /ingest done docs=%s chunks=%s duration_ms=%s",
        result.get("docs_indexed"), result.get("chunks_indexed"), result.get("duration_ms"),
    )
    return IngestResponse(
        docs_indexed=result["docs_indexed"],
        chunks_indexed=result["chunks_indexed"],
        duration_ms=result["duration_ms"],
    )


@router.get("/search", response_model=list[SearchHit])
async def get_search(
    q: str = Query(..., min_length=1),
    k: int = Query(default=_settings.rag_default_k, ge=1, le=20),
    debug: bool = Query(default=False),
):
    """Поиск top-k чанков через MCP (kb_search). Требуется запущенный MCP-сервер."""
    logger.info("[RAG] GET /search q=%r k=%s (via MCP)", q[:80] if len(q) > 80 else q, k)
    try:
        result = await mcp_call_tool_async("kb_search", {"query": q, "k": k})
    except MCPConnectionError as e:
        logger.error("[RAG] GET /search MCP unavailable: %s", e)
        raise
    chunks = result.get("chunks") or []
    logger.info("[RAG] GET /search done chunks=%d", len(chunks))
    out = [
        SearchHit(
            chunk_id=str(c.get("id", "")),
            score=float(c.get("score", 0)),
            doc_title=(c.get("doc_meta") or {}).get("title") or "",
            path=(c.get("doc_meta") or {}).get("doc_key") or "",
            text_preview=c.get("preview") or "",
        )
        for c in chunks
    ]
    if debug:
        return out
    return out


@router.post("/ask", response_model=AnswerContract)
def post_ask(body: AskRequestBody, request: Request, debug: bool = Query(default=False)):
    """Ответ на вопрос по базе знаний через agent (MCP tools + LLM). Возвращает AnswerContract."""
    logger.info("[RAG] POST /ask question=%r", body.question[:80] if len(body.question) > 80 else body.question)
    contract = ask(question=body.question, request=request)
    if debug:
        pass
    return contract
