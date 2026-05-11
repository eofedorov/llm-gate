"""PoC-клиент внешней OpenAI-compatible LLM.

Оставлен рядом с Cursor SDK backend для сравнения поведения и быстрого отката.
"""
import logging
import os
import time
from typing import Any, cast

from openai import APIStatusError, OpenAI
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionMessageParam,
    ChatCompletionToolUnionParam,
)

from orchestrator.settings import Settings

logger = logging.getLogger(__name__)
_settings = Settings()


def _log_api_error(
    e: APIStatusError,
    *,
    model: str,
    messages: list,
    level: int = logging.ERROR,
) -> None:
    url = str(e.response.url) if e.response else _settings.llm_base_url
    body = e.body if hasattr(e, "body") else None
    roles = [m.get("role", "?") for m in messages[:5]]
    logger.log(
        level,
        "External LLM API error: %s %s | url=%s model=%s roles=%s | response_body=%s",
        e.status_code,
        type(e).__name__,
        url,
        model,
        roles,
        body,
    )


def _log_response_headers_on_429(e: APIStatusError) -> None:
    """При 429 логируем заголовки ответа (диагностика rate limit)."""
    if e.status_code != 429:
        return
    if e.response is None:
        logger.error("External LLM 429: нет объекта response, заголовки недоступны")
        return
    headers = dict(e.response.headers)
    logger.error("External LLM 429 response headers: %s", headers)


def _is_retriable_llm_http_status(status_code: int) -> bool:
    """Временные ошибки сервера/шлюза — повтор с фиксированной паузой (429 не ретраим)."""
    return status_code in (500, 502, 503, 504)


def _sleep_before_llm_retry() -> None:
    """Пауза перед повтором после 5xx/таймаута (отдельно от паузы Airflow между задачами)."""
    sec = _settings.llm_retry_sleep_seconds
    if sec > 0:
        logger.warning("External LLM retry after 5xx/timeout: sleep %.1fs before next attempt", sec)
        time.sleep(sec)


def _make_client() -> OpenAI:
    return OpenAI(
        base_url=_settings.llm_base_url,
        api_key=os.environ.get("GITHUB_TOKEN", "").strip(),
    )


def call_llm(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    max_tokens: int | None = None,
    timeout: int | None = None,
    max_retries: int | None = None,
) -> str:
    model = model or _settings.llm_model
    max_tokens = max_tokens if max_tokens is not None else _settings.llm_max_tokens
    timeout = timeout if timeout is not None else _settings.llm_timeout
    max_retries = max_retries if max_retries is not None else _settings.llm_max_retries

    client = _make_client()
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            completion = client.chat.completions.create(
                model=model,
                messages=[_normalize_message(m) for m in messages],
                max_tokens=max_tokens,
                timeout=timeout,
            )
            if completion.choices:
                content = completion.choices[0].message.content
                if content:
                    return content.strip()
            return ""
        except APIStatusError as e:
            if e.status_code == 429:
                _log_api_error(e, model=model, messages=messages, level=logging.ERROR)
                _log_response_headers_on_429(e)
                raise
            will_retry = attempt < max_retries and _is_retriable_llm_http_status(e.status_code)
            _log_api_error(
                e,
                model=model,
                messages=messages,
                level=logging.WARNING if will_retry else logging.ERROR,
            )
            if will_retry:
                _sleep_before_llm_retry()
                continue
            raise
        except Exception as e:
            logger.error("external call_llm attempt=%s failed: %s", attempt + 1, e)
            last_error = e
            if attempt == max_retries:
                raise
            if "timeout" in str(e).lower() or "503" in str(e) or "502" in str(e) or "500" in str(e):
                _sleep_before_llm_retry()
                continue
            raise
    raise last_error or RuntimeError("External LLM call failed")


def _normalize_message(m: dict[str, Any]) -> ChatCompletionMessageParam:
    role = str(m.get("role", "user"))
    out: dict[str, Any] = {"role": role}
    if "content" in m:
        out["content"] = str(m.get("content", ""))
    if "tool_calls" in m and m["tool_calls"]:
        out["tool_calls"] = m["tool_calls"]
    if "tool_call_id" in m and m.get("tool_call_id"):
        out["tool_call_id"] = m["tool_call_id"]
    if "name" in m and m.get("name"):
        out["name"] = m["name"]
    return cast(ChatCompletionMessageParam, out)


def call_llm_with_tools(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    *,
    model: str | None = None,
    max_tokens: int | None = None,
    timeout: int | None = None,
    max_retries: int | None = None,
) -> ChatCompletion:
    model = model or _settings.llm_model
    max_tokens = max_tokens if max_tokens is not None else _settings.llm_max_tokens
    timeout = timeout if timeout is not None else _settings.llm_timeout
    max_retries = max_retries if max_retries is not None else _settings.llm_max_retries

    client = _make_client()
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            completion = client.chat.completions.create(
                model=model,
                messages=[_normalize_message(m) for m in messages],
                tools=cast(list[ChatCompletionToolUnionParam], tools),
                max_tokens=max_tokens,
                timeout=timeout,
            )
            return completion
        except APIStatusError as e:
            if e.status_code == 429:
                _log_api_error(e, model=model, messages=messages, level=logging.ERROR)
                _log_response_headers_on_429(e)
                raise
            will_retry = attempt < max_retries and _is_retriable_llm_http_status(e.status_code)
            _log_api_error(
                e,
                model=model,
                messages=messages,
                level=logging.WARNING if will_retry else logging.ERROR,
            )
            if will_retry:
                _sleep_before_llm_retry()
                continue
            raise
        except Exception as e:
            logger.error("external call_llm_with_tools attempt=%s failed: %s", attempt + 1, e)
            last_error = e
            if attempt == max_retries:
                raise
            if "timeout" in str(e).lower() or "503" in str(e) or "502" in str(e) or "500" in str(e):
                _sleep_before_llm_retry()
                continue
            raise
    raise last_error or RuntimeError("External LLM call failed")
