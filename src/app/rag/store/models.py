"""Pydantic models for chunks and document metadata. chunk_id format: doc:{doc_id}#chunk:{chunk_index}."""
from pydantic import BaseModel, ConfigDict, Field


class DocumentMeta(BaseModel):
    """Metadata for a source document."""
    model_config = ConfigDict(extra="forbid")

    doc_id: str
    title: str
    path: str = ""
    document_type: str = ""
    created_at: str = ""
    section: str = ""


class ChunkMeta(BaseModel):
    """Metadata for a single chunk (stored with FAISS)."""
    model_config = ConfigDict(extra="forbid")

    chunk_id: str  # doc:{doc_id}#chunk:{index}
    doc_id: str
    title: str
    path: str = ""
    document_type: str = ""
    created_at: str = ""
    section: str = ""
    chunk_index: int = 0
    text: str = ""


def make_chunk_id(doc_id: str, chunk_index: int) -> str:
    """Build chunk_id in format doc:{doc_id}#chunk:{chunk_index}."""
    return f"doc:{doc_id}#chunk:{chunk_index}"
