"""Настройки gateway: URL orchestrator и audit-service."""
from settings import BaseAppSettings


class Settings(BaseAppSettings):
    orchestrator_url: str = "http://localhost:8004"
    audit_service_url: str = ""
