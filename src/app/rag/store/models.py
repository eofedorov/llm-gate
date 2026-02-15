"""Pydantic-модели для чанков и метаданных документов. Формат chunk_id: doc:{doc_id}#chunk:{chunk_index}."""
from pydantic import BaseModel, ConfigDict, Field


class DocumentMeta(BaseModel):
    """Метаданные исходного документа."""
    model_config = ConfigDict(extra="forbid")

    doc_id: str
    title: str
    path: str = ""
    document_type: str = ""
    created_at: str = ""
    section: str = ""


class ChunkMeta(BaseModel):
    """Метаданные одного чанка (хранятся вместе с FAISS)."""
    model_config = ConfigDict(extra="forbid")

    chunk_id: str  # doc:{doc_id}#chunk:{index} — формат идентификатора
    doc_id: str
    title: str
    path: str = ""
    document_type: str = ""
    created_at: str = ""
    section: str = ""
    chunk_index: int = 0
    text: str = ""


def make_chunk_id(doc_id: str, chunk_index: int) -> str:
    """Собрать chunk_id в формате doc:{doc_id}#chunk:{chunk_index}."""
    return f"doc:{doc_id}#chunk:{chunk_index}"
