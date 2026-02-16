"""
Рендеринг шаблона и сбор контекста для LLM.

Формирует краткое описание выходной схемы (пример полей и типов) для вставки в промпт,
чтобы модель возвращала данные в нужном формате, а не полную JSON Schema.
"""
import json
import logging
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.prompts.registry import PromptSpec, TEMPLATES_DIR

logger = logging.getLogger(__name__)


def get_schema_description(schema_class: type) -> str:
    """
    Построить краткое описание формата ответа по Pydantic-схеме.

    Используется пример полей и типов (не полная JSON Schema), чтобы LLM
    возвращала данные, а не схему со служебными полями ($defs, properties и т.д.).

    Возвращает:
        Строка вида «Только этот JSON, без других полей: { "field": ..., ... }».
    """
    raw = schema_class.model_json_schema()
    props = raw.get("properties") or {}
    required = raw.get("required") or []
    defs = raw.get("$defs") or raw.get("definitions") or {}

    # Порядок: сначала обязательные поля, затем остальные
    ordered_names = list(dict.fromkeys([*required, *props.keys()]))
    parts = []
    for name in ordered_names:
        if name not in props:
            continue
        part = _describe_property(name, props[name], defs)
        if part:
            parts.append(part)

    result = "Только этот JSON, без других полей:\n{" + ", ".join(parts) + "}"
    logger.debug("schema_description schema=%s fields=%d", schema_class.__name__, len(parts))
    return result


def _describe_property(name: str, prop: dict[str, Any], defs: dict[str, Any] | None = None) -> str:
    """
    Описать одно поле схемы для промпта: тип и ограничения.

    Поддерживаются: array (в т.ч. Entity, вложенные модели по $ref), number (0–1), enum/const, string (с maxLength).
    """
    defs = defs or {}
    ptype = prop.get("type", "string")

    if ptype == "array":
        return _describe_array_field(name, prop.get("items") or {}, defs)
    if ptype == "number" or (ptype == "integer" and "confidence" in name):
        return _describe_number_field(name, prop)
    if "enum" in prop or "const" in prop:
        return _describe_enum_field(name, prop)
    return _describe_string_field(name, prop)


def _describe_array_field(name: str, items_schema: dict[str, Any], defs: dict[str, Any] | None = None) -> str:
    """
    Описание поля-массива. Для $ref — разрешаем через $defs и описываем поля вложенной модели.
    """
    defs = defs or {}
    ref = items_schema.get("$ref", "")
    if ref:
        # "#/$defs/SourceCitation" -> имя "SourceCitation"
        ref_name = ref.split("/")[-1] if isinstance(ref, str) else ""
        if ref_name in defs:
            nested = defs[ref_name]
            nprops = nested.get("properties") or {}
            nrequired = nested.get("required") or []
            nordered = list(dict.fromkeys([*nrequired, *nprops.keys()]))
            inner_parts = []
            for nname in nordered:
                if nname not in nprops:
                    continue
                inner_parts.append(_describe_property(nname, nprops[nname], defs))
            inner = ", ".join(inner_parts)
            return f'"{name}": [{{{inner}}}, ...]'
        if "Entity" in str(ref):
            return f'"{name}": [{{"type": "<string>", "value": "<string>"}}, ...]'
    return f'"{name}": [...]'


def _describe_number_field(name: str, prop: dict[str, Any]) -> str:
    """Числовое поле (в т.ч. confidence 0–1)."""
    return f'"{name}": <float 0-1>'


def _describe_enum_field(name: str, prop: dict[str, Any]) -> str:
    """Поле с перечислением допустимых значений (enum/const)."""
    enum_vals = prop.get("enum")
    if enum_vals is None and "const" in prop:
        enum_vals = [prop["const"]]
    enum_vals = enum_vals or []
    first = enum_vals[0] if enum_vals else ""
    options = ", ".join(str(x) for x in enum_vals)
    return f'"{name}": "{first}" (один из: {options})'


def _describe_string_field(name: str, prop: dict[str, Any]) -> str:
    """Строковое поле, опционально с maxLength."""
    max_len = prop.get("maxLength")
    suffix = f", max {max_len} chars" if max_len else ""
    return f'"{name}": "<string>{suffix}"'


class RenderContext:
    """Контекст для рендера: задача, вход, ограничения, описание схемы вывода, произвольные extras для шаблона."""
    def __init__(
        self,
        task: str,
        input_data: str | dict | Any,
        constraints: dict[str, Any] | None = None,
        output_contract: str | None = None,
        extras: dict[str, Any] | None = None,
    ):
        self.task = task
        self.input = input_data if isinstance(input_data, str) else json.dumps(input_data, ensure_ascii=False)
        self.constraints = constraints or {}
        self.output_contract = output_contract or ""
        self.extras = extras or {}


def render(spec: PromptSpec, context: RenderContext) -> tuple[str, str]:
    """
    Собрать сообщения для LLM: (system_message, user_message).
    Шаблон рендерится с контекстом; output_contract подставляется в шаблон.
    """
    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape(default=False),
    )
    template = env.get_template(spec.template_path.name)
    user_message = template.render(
        task=context.task,
        input=context.input,
        output_contract=context.output_contract,
        constraints=context.constraints,
        **context.extras,
    ).strip()

    system_message = spec.system_rules
    return system_message, user_message
