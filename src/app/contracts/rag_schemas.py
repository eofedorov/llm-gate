"""RAG answer contract: answer with citations, sources, status ok | insufficient_context."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SourceCitation(BaseModel):
    """One source with chunk_id, doc title, quote, relevance."""
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    doc_title: str
    quote: str
    relevance: float = Field(ge=0.0, le=1.0)


class AnswerContract(BaseModel):
    """Response contract for POST /rag/ask."""
    model_config = ConfigDict(extra="forbid")

    answer: str
    confidence: float = Field(ge=0.0, le=1.0)
    sources: list[SourceCitation] = Field(default_factory=list)
    status: Literal["ok", "insufficient_context"] = "ok"
