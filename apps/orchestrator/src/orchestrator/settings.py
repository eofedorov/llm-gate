"""Настройки orchestrator: LLM, MCP, RAG."""
from settings import BaseAppSettings


class Settings(BaseAppSettings):
    llm_base_url: str = "https://models.github.ai/inference/v1"
    llm_model: str = "openai/gpt-4.1-nano"
    llm_max_tokens: int = 4096
    llm_timeout: int = 120
    llm_max_retries: int = 4
    # Пауза только между повторными попытками при 5xx (не путать с паузой в Airflow между задачами).
    llm_retry_sleep_seconds: float = 2.0
    enable_token_meter: bool = False
    rag_default_k: int = 5
    mcp_server_url: str = ""
    mcp_timeout: int = 600
    datastore_url: str = ""
    audit_service_url: str = ""
