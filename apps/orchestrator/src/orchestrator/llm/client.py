"""LLM facade.

Основной backend — локальный Cursor SDK CLI. Старый OpenAI-compatible клиент
сохранён в `external_llm_poc` и доступен через `LLM_BACKEND=external_poc`.
"""
import logging
import time
from typing import Any

from openai.types.chat import ChatCompletion

from orchestrator.llm import cursor_sdk_client, external_llm_poc
from orchestrator.settings import Settings

logger = logging.getLogger(__name__)
_settings = Settings()


def _is_external_poc_backend() -> bool:
    return _settings.llm_backend.strip().lower() in {"external_poc", "external", "openai_poc"}


def _is_retriable_llm_http_status(status_code: int) -> bool:
    """Backcompat helper for the preserved external LLM PoC tests."""
    return external_llm_poc._is_retriable_llm_http_status(status_code)


def _sleep_before_llm_retry() -> None:
    """Пауза перед повтором backend-запроса."""
    sec = _settings.llm_retry_sleep_seconds
    if sec > 0:
        logger.warning("LLM retry: sleep %.1fs before next attempt", sec)
        time.sleep(sec)


def _is_retriable_cursor_error(exc: Exception) -> bool:
    return isinstance(exc, cursor_sdk_client.CursorSdkError) and exc.retryable


def call_llm(
    messages: list[dict[str, Any]],
    *,
    model: str | None = None,
    max_tokens: int | None = None,
    timeout: int | None = None,
    max_retries: int | None = None,
) -> str:
    """Выполнить обычный LLM prompt через выбранный backend."""
    if _is_external_poc_backend():
        return external_llm_poc.call_llm(
            messages,  # pyright: ignore[reportArgumentType]
            model=model,
            max_tokens=max_tokens,
            timeout=timeout,
            max_retries=max_retries,
        )

    max_retries = max_retries if max_retries is not None else _settings.llm_max_retries
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return cursor_sdk_client.call_prompt(
                messages,
                model=model or _settings.cursor_model,
                timeout=timeout,
            )
        except Exception as exc:
            last_error = exc
            will_retry = attempt < max_retries and _is_retriable_cursor_error(exc)
            logger.log(
                logging.WARNING if will_retry else logging.ERROR,
                "Cursor SDK LLM call attempt=%s failed: %s",
                attempt + 1,
                exc,
            )
            if will_retry:
                _sleep_before_llm_retry()
                continue
            raise
    raise last_error or RuntimeError("LLM call failed")


def call_llm_with_tools(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    *,
    model: str | None = None,
    max_tokens: int | None = None,
    timeout: int | None = None,
    max_retries: int | None = None,
) -> ChatCompletion:
    """PoC-only OpenAI function-tools path.

    Cursor SDK RAG uses `cursor_sdk_client.call_rag` instead of exposing OpenAI
    tool-call completions through this facade.
    """
    if not _is_external_poc_backend():
        raise RuntimeError("call_llm_with_tools is available only with LLM_BACKEND=external_poc")
    return external_llm_poc.call_llm_with_tools(
        messages,
        tools,
        model=model,
        max_tokens=max_tokens,
        timeout=timeout,
        max_retries=max_retries,
    )
