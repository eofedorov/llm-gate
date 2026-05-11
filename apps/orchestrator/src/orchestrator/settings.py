"""Настройки orchestrator: LLM, MCP, RAG."""
from settings import BaseAppSettings


class Settings(BaseAppSettings):
    # Основной backend после миграции: cursor_sdk. Старый внешний LLM путь остаётся как external_poc.
    llm_backend: str = "cursor_sdk"
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
    cursor_api_key: str = ""
    cursor_model: str = "composer-2"
    cursor_agent_cwd: str = ""
    cursor_cli_script: str = ""
    cursor_node_command: str = "node"
    cursor_cli_timeout: int = 600
