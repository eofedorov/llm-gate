"""Конфигурация приложения из переменных окружения."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Корень проекта: src/app/settings.py
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_base_url: str = ""
    llm_model: str = ""
    llm_max_tokens: int = 0
    llm_timeout: int = 0
    llm_max_retries: int = 0
    enable_token_meter: bool = False
    # RAG: модель эмбеддингов, размер чанка, перекрытие, дефолтный k, порог relevance
    rag_embedding_model: str = ""
    rag_chunk_size: int = 512
    rag_chunk_overlap: int = 64
    rag_default_k: int = 5
    rag_relevance_threshold: float = 0.3
    # RAG: путь к базе знаний (пусто = project_root/data)
    kb_path: str = ""
    # Phase 3: Postgres + Qdrant + MCP
    database_url: str = ""
    qdrant_url: str = ""
    qdrant_collection: str = "kb_chunks_v1"
    mcp_server_url: str = ""
    mcp_timeout: int = 600
