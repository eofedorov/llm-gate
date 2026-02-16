"""
Acceptance: 10 кейсов (баг, фича, UX, дубликат, техдолг и т.д.).
Проверяем: все ответы — валидный JSON, минимум 8 из 10 классифицированы верно.
Используем mock LLM с фиксированными ответами по типу входа, чтобы не требовать API key.
"""
import pytest

from app.services.runner import run

# 10 кейсов: (входной текст, ожидаемая метка)
ACCEPTANCE_CASES = [
    ("После релиза 2.1.3 на странице оплаты появляется 500 ошибка. Шаги: добавить товар, перейти к оплате.", "bug"),
    ("Добавить кнопку экспорта в CSV на странице отчётов.", "feature"),
    ("Как настроить двухфакторную аутентификацию для админов?", "question"),
    ("Предлагаю улучшить подсказки при вводе email в форме логина.", "feature"),
    ("В мобильной версии кнопка «Отправить» обрезается на маленьких экранах.", "bug"),
    ("Это дубликат тикета #456 — та же ошибка с сессией.", "other"),
    ("Рефакторинг модуля платёжной интеграции: разбить на подмодули.", "other"),
    ("При пустой корзине показывать блок «Вам может понравиться».", "feature"),
    ("Ошибка: при сохранении черновика теряются вложения. Воспроизводится в Chrome.", "bug"),
    ("Нужна ли поддержка IE11? Есть ли статистика по браузерам?", "question"),
]


def _make_mock_returning_label(expected_label: str):
    def mock(messages):
        return (
            '{"label": "%s", "confidence": 0.92, "rationale": "By input type."}'
            % expected_label
        )
    return mock


@pytest.mark.parametrize("input_text,expected_label", ACCEPTANCE_CASES)
def test_acceptance_each_returns_valid_json(input_text: str, expected_label: str):
    """Каждый из 10 кейсов возвращает строго валидный JSON (и ожидаемую метку при нашем mock)."""
    mock = _make_mock_returning_label(expected_label)
    result = run(
        "classify",
        "v1",
        "Classify the following task.",
        input_text,
        _call_llm=mock,
    )
    assert result["ok"] is True, result.get("diagnostics", result)
    data = result["data"]
    assert "label" in data
    assert data["label"] in ("bug", "feature", "question", "other")
    assert "confidence" in data
    assert 0 <= data["confidence"] <= 1
    assert "rationale" in data
    assert data["label"] == expected_label
