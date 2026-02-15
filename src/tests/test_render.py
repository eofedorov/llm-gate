"""Проверка рендера: шаблон подставляет параметры, важные блоки не теряются."""
import pytest

from app.contracts.schemas import ClassifyV1Out, ExtractV1Out
from app.prompts.registry import get_prompt
from app.prompts.render import RenderContext, get_schema_description, render


def test_get_schema_description():
    desc = get_schema_description(ClassifyV1Out)
    assert "label" in desc
    assert "confidence" in desc
    assert "rationale" in desc
    assert "bug" in desc or "enum" in desc


def test_render_classify_v1_substitutes_task_and_input():
    spec = get_prompt("classify_v1")
    assert spec is not None
    ctx = RenderContext(
        task="Классифицировать задачу",
        input_data="После релиза 2.1.3 на странице оплаты 500 ошибка.",
        output_contract=get_schema_description(ClassifyV1Out),
    )
    system, user = render(spec, ctx)
    assert "Классифицировать задачу" in user
    assert "После релиза 2.1.3" in user
    assert "500 ошибка" in user
    assert "label" in user or "rationale" in user
    assert system
    assert "JSON" in system


def test_render_classify_v1_includes_schema_block():
    spec = get_prompt("classify_v1")
    ctx = RenderContext(
        task="Classify",
        input_data="Fix login button.",
        output_contract=get_schema_description(ClassifyV1Out),
    )
    _, user = render(spec, ctx)
    assert "bug" in user or "feature" in user
    assert "confidence" in user
    assert "rationale" in user
    assert "Fix login button" in user


def test_render_extract_v1_substitutes_and_includes_schema():
    spec = get_prompt("extract_v1")
    assert spec is not None
    ctx = RenderContext(
        task="Извлечь сущности",
        input_data="Вакансия: Python-разработчик, опыт 3 года.",
        output_contract=get_schema_description(ExtractV1Out),
    )
    system, user = render(spec, ctx)
    assert "Извлечь сущности" in user
    assert "Python-разработчик" in user
    assert "entities" in user
    assert "summary" in user
    assert system


def test_render_no_empty_required_parts():
    spec = get_prompt("classify_v1")
    ctx = RenderContext(
        task="T",
        input_data="x",
        output_contract='{"label":"bug","confidence":0.5,"rationale":"x"}',
    )
    _, user = render(spec, ctx)
    assert "T" in user
    assert "x" in user
    assert "  " not in user or user.count("  ") < 5  # без избыточных пустых блоков
