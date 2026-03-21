"""Настройки gateway: URL orchestrator и audit-service."""
from common.settings import BaseAppSettings


class Settings(BaseAppSettings):
    orchestrator_url: str = "http://localhost:8004"
    audit_service_url: str = ""
