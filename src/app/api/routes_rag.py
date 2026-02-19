"""RAG API: POST /ingest, GET /search, POST /ask. Ingest и search идут через MCP."""
import logging

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.contracts.rag_schemas import AnswerContract
from app.mcp.client.mcp_client import MCPConnectionError, call_tool as mcp_call_tool
from app.services.rag_agent import ask
from app.settings import Settings

router = APIRouter()
logger = logging.getLogger(__name__)
_settings = Settings()


class IngestResponse(BaseModel):
    docs_indexed: int
    chunks_indexed: int
    duration_ms: float


class SearchHit(BaseModel):
    chunk_id: str
    score: float
    doc_title: str
    path: str
    text_preview: str


class AskRequestBody(BaseModel):
    question: str = Field(..., min_length=1)
    k: int = Field(default=_settings.rag_default_k, ge=1, le=20)
    filters: dict | None = None
    strict_mode: bool = False


@router.post("/ingest", response_model=IngestResponse)
def post_ingest():
    """Индексация через MCP (kb_ingest). Требуется запущенный MCP-сервер."""
    logger.info("[RAG] POST /ingest start (via MCP)")
    try:
        result = mcp_call_tool("kb_ingest", {})
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
def get_search(
    q: str = Query(..., min_length=1),
    k: int = Query(default=_settings.rag_default_k, ge=1, le=20),
    debug: bool = Query(default=False),
):
    """Поиск top-k чанков через MCP (kb_search). Требуется запущенный MCP-сервер."""
    logger.info("[RAG] GET /search q=%r k=%s (via MCP)", q[:80] if len(q) > 80 else q, k)
    try:
        result = mcp_call_tool("kb_search", {"query": q, "k": k})
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
def post_ask(body: AskRequestBody, debug: bool = Query(default=False)):
    """Ответ на вопрос по базе знаний через agent (MCP tools + LLM). Возвращает AnswerContract."""
    logger.info("[RAG] POST /ask question=%r", body.question[:80] if len(body.question) > 80 else body.question)
    contract = ask(question=body.question)
    if debug:
        pass  # chunks_used/doc_ids уже логируются в ask_service
    return contract
