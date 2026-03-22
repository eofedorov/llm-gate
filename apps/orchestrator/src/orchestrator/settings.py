"""Настройки orchestrator: LLM, MCP, RAG."""
from settings import BaseAppSettings


class Settings(BaseAppSettings):
    llm_base_url: str = "https://models.github.ai/inference/v1"
    llm_model: str = "openai/gpt-4.1-nano"
    llm_max_tokens: int = 4096
    llm_timeout: int = 120
    llm_max_retries: int = 4
    llm_retry_backoff_base: float = 2.0
    llm_retry_backoff_max: float = 120.0
    enable_token_meter: bool = False
    rag_default_k: int = 5
    mcp_server_url: str = ""
    mcp_timeout: int = 600
    datastore_url: str = ""
    audit_service_url: str = ""
