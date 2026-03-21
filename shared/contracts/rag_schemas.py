"""Контракт ответа RAG: ответ с цитатами, sources, status ok | insufficient_context."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SourceCitation(BaseModel):
    """Один источник: chunk_id, заголовок документа, цитата, relevance."""
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    doc_title: str
    quote: str
    relevance: float = Field(ge=0.0, le=1.0)


class AnswerContract(BaseModel):
    """Контракт ответа для POST /rag/ask."""
    model_config = ConfigDict(extra="forbid")

    answer: str
    confidence: float = Field(ge=0.0, le=1.0)
    sources: list[SourceCitation] = Field(default_factory=list)
    status: Literal["ok", "insufficient_context"] = "ok"
