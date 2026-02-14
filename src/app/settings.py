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
    # RAG: path to FAISS index dir (default: project_root/data/faiss_index)
    rag_index_dir: str = ""
