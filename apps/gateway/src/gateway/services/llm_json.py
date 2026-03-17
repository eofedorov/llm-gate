"""
Общие утилиты для разбора и валидации JSON-ответов LLM.
Используются и в prompt-run flow, и в RAG-агенте.
"""
import json
import logging
from typing import Any, TypeVar

from audit import audit_event, audited_span
from pydantic import BaseModel

from gateway.prompts.render import get_schema_description

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

REPAIR_SYSTEM = "Преобразуй ответ в валидный JSON по указанной схеме. Выведи только JSON, без пояснений до или после."


def extract_json_from_text(text: str) -> str:
    """Вырезать JSON-объект из текста (между первой { и последней })."""
    text = text.strip()
    start = text.find("{")
    if start == -1:
        return text
    end = text.rfind("}")
    if end == -1 or end < start:
        return text
    return text[start : end + 1]


def parse_and_validate(raw: str, schema_class: type[T]) -> tuple[T | None, str | None]:
    """
    Распарсить JSON и провалидировать схемой.
    Возвращает (model, None) при успехе или (None, error_message) при ошибке.
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("JSON decode error in parse_and_validate: %s", e)
        return None, f"JSON decode error: {e}"
    try:
        model = schema_class.model_validate(data)
        return model, None
    except Exception as e:
        logger.error("Validation error in parse_and_validate: %s", e)
        return None, f"Validation error: {e}"


def build_repair_messages(
    raw_content: str,
    schema_class: type[BaseModel],
    *,
    schema_description_max: int = 1500,
    content_max: int = 4000,
) -> list[dict[str, str]]:
    """Собрать сообщения для одного repair-прохода LLM (system + user)."""
    output_contract = get_schema_description(schema_class)
    return [
        {"role": "system", "content": REPAIR_SYSTEM + "\n\nСхема:\n" + output_contract[:schema_description_max]},
        {"role": "user", "content": "Исправь в валидный JSON:\n" + (raw_content or "")[:content_max]},
    ]


@audited_span("parse_llm_response_or_repair", kind="llm.call")
def parse_llm_response_or_repair(
    raw_content: str,
    schema_class: type[T],
    call_llm: Any,
) -> tuple[T | None, str | None]:
    """
    Разобрать ответ LLM в модель по схеме; при ошибке — один repair-проход и повторная валидация.
    Возвращает (model, None) при успехе или (None, diagnostics) при неудаче.
    call_llm: callable(messages: list[dict]) -> str.
    """
    parsed = extract_json_from_text(raw_content)
    model, err = parse_and_validate(parsed, schema_class)
    if model is not None:
        audit_event("schema_validation", result="ok")
        return model, None
    audit_event("schema_validation", result="fail", error=err)
    logger.info("Parse/validation failed (%s), attempting LLM repair", err[:80] if err else "unknown")
    repair_messages = build_repair_messages(raw_content, schema_class)
    raw_repair = call_llm(repair_messages)
    parsed_repair = extract_json_from_text(raw_repair)
    model_repair, err_repair = parse_and_validate(parsed_repair, schema_class)
    if model_repair is not None:
        audit_event("repair", attempted=True, success=True)
        return model_repair, None
    audit_event("repair", attempted=True, success=False, error=err_repair)
    return None, f"first: {err}; repair: {err_repair}"
