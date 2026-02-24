"""Настройки audit_service: путь к SQLite и окружение."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки приложения (env AUDIT_DB_PATH, ENV)."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="",
    )

    audit_db_path: str = "/app/data/audit.db"
    env: str = "dev"
