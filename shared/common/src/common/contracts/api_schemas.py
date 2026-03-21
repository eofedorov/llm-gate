"""Pydantic-модели API-запросов/ответов для gateway/orchestrator."""
from pydantic import BaseModel, Field


class RunRequest(BaseModel):
    task: str = ""
    input: str | dict
    constraints: dict | None = None


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


class UploadStubResponse(BaseModel):
    message: str
    files_count: int
    error: str | None = None
    ingest_docs_indexed: int | None = None
    ingest_chunks_indexed: int | None = None
    ingest_duration_ms: float | None = None
