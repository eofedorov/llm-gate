"""
Запуск задачи: собрать контекст -> вызвать LLM -> валидировать -> repair при необходимости.
Возвращает валидный Pydantic-объект или результат с ошибкой. Логирование в шаге 8.
"""
import json
import logging
import time
from typing import Any

from app.llm import client as llm_client
from app.llm.tokenizer import count_tokens
from app.prompts.registry import get_prompt_by_name_version
from app.prompts.render import RenderContext, get_schema_description, render
from app.settings import Settings

logger = logging.getLogger(__name__)
_settings = Settings()

REPAIR_SYSTEM = "Преобразуй ответ в валидный JSON по указанной схеме. Выведи только JSON, без пояснений до или после."


def _parse_and_validate(raw: str, schema_class: type):
    """Распарсить JSON и провалидировать схемой. При ошибке — (None, error_message)."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return None, f"JSON decode error: {e}"
    try:
        model = schema_class.model_validate(data)
        return model, None
    except Exception as e:
        return None, f"Validation error: {e}"


def _extract_json_from_text(text: str) -> str:
    """Попытаться вырезать JSON из текста (между первой { и последней })."""
    text = text.strip()
    start = text.find("{")
    if start == -1:
        return text
    end = text.rfind("}")
    if end == -1 or end < start:
        return text
    return text[start : end + 1]


def run(
    prompt_name: str,
    version: str,
    task: str,
    input_data: str | dict,
    constraints: dict[str, Any] | None = None,
    *,
    extras: dict[str, Any] | None = None,
    _call_llm: Any = None,
) -> dict[str, Any]:
    """
    Выполнить промпт: render -> LLM -> validate -> при невалидном repair (1 попытка) -> ответ или ошибка.
    _call_llm: для тестов, подмена вызова LLM (callable(messages) -> str).
    Возврат: {"ok": True, "data": <Pydantic model dict>} или {"ok": False, "error": str, "diagnostics": str}.
    """
    call_llm = _call_llm if _call_llm is not None else llm_client.call_llm

    # --- Реестр промптов ---
    logger.info("[Registry] lookup prompt_name=%s version=%s", prompt_name, version)
    spec = get_prompt_by_name_version(prompt_name, version)
    if not spec:
        logger.warning("[Registry] prompt not found prompt_name=%s version=%s", prompt_name, version)
        return {"ok": False, "error": "unknown prompt", "diagnostics": f"{prompt_name} {version}"}
    logger.info("[Registry] found spec key=%s template=%s", spec.key, spec.template_path.name)

    # --- Сбор контекста ---
    schema_class = spec.output_schema
    output_contract = get_schema_description(schema_class)
    context = RenderContext(
        task=task,
        input_data=input_data,
        constraints=constraints or {},
        output_contract=output_contract,
        extras=extras,
    )
    system_message, user_message = render(spec, context)
    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_message},
    ]
    logger.info(
        "[ContextBuilder] render done system_len=%d user_len=%d",
        len(system_message), len(user_message),
    )

    # --- Подсчёт токенов (до вызова) ---
    prompt_tokens = count_tokens(messages, _settings.llm_model)
    if prompt_tokens > 0:
        logger.info("[Tokenizer] prompt_tokens=%d model=%s", prompt_tokens, _settings.llm_model)

    # --- Вызов LLM ---
    start = time.perf_counter()
    logger.info("[LLM] calling model=%s", _settings.llm_model)
    raw_response = call_llm(messages)
    elapsed = time.perf_counter() - start
    logger.info("[LLM] response received elapsed_sec=%.2f response_len=%d", elapsed, len(raw_response))

    # --- Валидация по схеме ---
    parsed = _extract_json_from_text(raw_response)
    logger.info("[Validator] parse attempt extracted_len=%d", len(parsed))
    model, err = _parse_and_validate(parsed, schema_class)
    if model is not None:
        logger.info("[Validator] ok strict JSON")
        logger.info("[Strict JSON] success prompt=%s version=%s elapsed_sec=%.2f repair=false", prompt_name, version, elapsed)
        return {"ok": True, "data": model.model_dump()}

    logger.warning("[Validator] failed %s", err)

    # --- Repair при невалидном ответе ---
    logger.info("[Repair] triggering repair pass")
    repair_messages = [
        {"role": "system", "content": REPAIR_SYSTEM + "\n\nСхема:\n" + output_contract[:1500]},
        {"role": "user", "content": "Исправь в валидный JSON:\n" + raw_response[:4000]},
    ]
    raw_repair = call_llm(repair_messages)
    elapsed_total = time.perf_counter() - start
    logger.info("[LLM] repair response received elapsed_total_sec=%.2f repair_len=%d", elapsed_total, len(raw_repair))

    parsed_repair = _extract_json_from_text(raw_repair)
    logger.info("[Validator] repair parse attempt extracted_len=%d", len(parsed_repair))
    model_repair, err_repair = _parse_and_validate(parsed_repair, schema_class)
    if model_repair is not None:
        logger.info("[Validator] ok after repair strict JSON")
        logger.info("[Strict JSON] success after repair prompt=%s version=%s elapsed_sec=%.2f repair=true", prompt_name, version, elapsed_total)
        return {"ok": True, "data": model_repair.model_dump()}

    logger.warning("[Validator] repair failed %s", err_repair)
    diagnostics = f"first: {err}; repair: {err_repair}"
    logger.warning(
        "[Strict JSON] validation failed prompt=%s version=%s elapsed_sec=%.2f repair=true diagnostics=%s",
        prompt_name, version, elapsed_total, diagnostics,
    )
    return {"ok": False, "error": "validation failed", "diagnostics": diagnostics}
