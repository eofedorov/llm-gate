"""Настройки mcp_server: RAG (эмбеддинги, чанки), datastore."""
from common.settings import BaseAppSettings


class Settings(BaseAppSettings):
    """MCP-server-специфичные поля поверх базовых (database_url, qdrant_* из common)."""

    audit_service_url: str = ""
    datastore_url: str = ""
    rag_embedding_model: str = ""
    rag_chunk_size: int = 512
    rag_chunk_overlap: int = 64
    rag_default_k: int = 5
    rag_relevance_threshold: float = 0.3
