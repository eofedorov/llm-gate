"""Базовые настройки из env (database_url, qdrant_*)."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseAppSettings(BaseSettings):
    """Настройки, общие для нескольких сервисов (gateway, mcp_server, db)."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = ""
    qdrant_url: str = ""
    qdrant_collection: str = "kb_chunks_v1"
