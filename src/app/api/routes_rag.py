"""RAG API: POST /ingest, GET /search, POST /ask."""
import logging
from pathlib import Path

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.contracts.rag_schemas import AnswerContract
from app.rag.ask_service import ask
from app.rag.formats import truncate_preview
from app.rag.ingest.indexer import run_ingestion
from app.rag.retrieve import retrieve

router = APIRouter()
logger = logging.getLogger(__name__)

# Project root for default kb path (src/app/api -> 3 parents to src, 4 to project root)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_KB_PATH = _PROJECT_ROOT / "data"


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
    k: int = Field(default=5, ge=1, le=20)
    filters: dict | None = None
    strict_mode: bool = False


@router.post("/ingest", response_model=IngestResponse)
def post_ingest():
    """Index documents from data/ (all *.json) into FAISS. Returns stats."""
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
    k: int = Query(default=5, ge=1, le=20),
    debug: bool = Query(default=False),
):
    """Search for top-k chunks by query. Returns chunk_id, score, doc_title, path, text_preview."""
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
        return out  # Could add debug fields to response; for now same body
    return out


@router.post("/ask", response_model=AnswerContract)
def post_ask(body: AskRequestBody, debug: bool = Query(default=False)):
    """Answer question from knowledge base with citations. Returns AnswerContract."""
    logger.info("[RAG] POST /ask question_len=%d k=%d", len(body.question), body.k)
    contract = ask(
        question=body.question,
        k=body.k,
        filters=body.filters,
        strict_mode=body.strict_mode,
    )
    if debug:
        pass  # Log chunks_used/doc_ids already in ask_service
    return contract
