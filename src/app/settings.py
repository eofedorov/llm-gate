"""Конфигурация приложения из переменных окружения."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Корень проекта: src/app/settings.py -> parent.parent.parent
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
    # RAG: путь к директории индекса FAISS (по умолчанию project_root/data/faiss_index)
    rag_index_dir: str = ""
    # RAG: модель эмбеддингов, размер чанка, перекрытие, дефолтный k, порог relevance
    rag_embedding_model: str = "intfloat/multilingual-e5-small"
    rag_chunk_size: int = 512
    rag_chunk_overlap: int = 64
    rag_default_k: int = 5
    rag_relevance_threshold: float = 0.3
    # RAG: путь к базе знаний (пусто = project_root/data)
    rag_kb_path: str = ""
