"""RAG API: POST /ingest, GET /search, POST /ask."""
import logging
from pathlib import Path

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.contracts.rag_schemas import AnswerContract
from app.rag.ask_service import ask
from app.rag.formats import truncate_preview
from app.rag.ingest.indexer import run_ingestion
from app.rag.ingest.loader import DEFAULT_KB_PATH
from app.rag.retrieve import retrieve
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
    """Индексация документов из data/ (все *.json) в FAISS. Возвращает статистику."""
    logger.info("[RAG] POST /ingest starting")
    result = run_ingestion(kb_path=DEFAULT_KB_PATH)
    logger.info("[RAG] POST /ingest done docs=%s chunks=%s duration_ms=%s", result.get("docs_indexed"), result.get("chunks_indexed"), result.get("duration_ms"))
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
    """Поиск top-k чанков по запросу. Возвращает chunk_id, score, doc_title, path, text_preview."""
    chunks = retrieve(query=q, k=k)
    doc_ids = [m.get("doc_id") for _, _, m in chunks]
    logger.info("[RAG] GET /search q_len=%d chunks=%d doc_ids=%s", len(q), len(chunks), doc_ids)
    out = [
        SearchHit(
            chunk_id=cid,
            score=score,
            doc_title=meta.get("title") or "",
            path=meta.get("path") or "",
            text_preview=truncate_preview(meta.get("text") or ""),
        )
        for cid, score, meta in chunks
    ]
    if debug:
        return out  # Можно добавить отладочные поля в ответ; пока то же тело
    return out


@router.post("/ask", response_model=AnswerContract)
def post_ask(body: AskRequestBody, debug: bool = Query(default=False)):
    """Ответ на вопрос по базе знаний с цитатами. Возвращает AnswerContract."""
    logger.info("[RAG] POST /ask question_len=%d k=%d", len(body.question), body.k)
    contract = ask(
        question=body.question,
        k=body.k,
        filters=body.filters,
        strict_mode=body.strict_mode,
    )
    if debug:
        pass  # chunks_used/doc_ids уже логируются в ask_service
    return contract
