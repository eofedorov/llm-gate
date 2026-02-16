"""Runner с замоканным LLM: happy path, repair path, оба невалидны."""
from app.services.runner import run


VALID_CLASSIFY_JSON = '{"label": "bug", "confidence": 0.93, "rationale": "Ошибка на странице оплаты."}'
VALID_EXTRACT_JSON = '{"entities": [{"type": "component", "value": "payment"}], "summary": "Bug in payment."}'
# Почти JSON: текст вокруг + невалидный объект (нет rationale), чтобы сработал repair
ALMOST_JSON_FIRST = "Вот ответ:\n" + '{"label": "bug", "confidence": 0.9}' + "\nГотово."
INVALID_JSON = '{"label": "bug", "confidence": 0.9}'  # нет rationale


def test_runner_valid_first_response_no_repair():
    call_count = 0

    def mock_llm(messages):
        nonlocal call_count
        call_count += 1
        return VALID_CLASSIFY_JSON

    result = run(
        "classify",
        "v1",
        "Classify",
        "После релиза 2.1.3 на странице оплаты 500.",
        _call_llm=mock_llm,
    )
    assert result["ok"] is True
    assert result["data"]["label"] == "bug"
    assert result["data"]["confidence"] == 0.93
    assert call_count == 1


def test_runner_almost_json_then_repair_returns_valid():
    call_count = 0

    def mock_llm(messages):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return ALMOST_JSON_FIRST  # невалидно: нет rationale
        return VALID_CLASSIFY_JSON

    result = run(
        "classify",
        "v1",
        "Classify",
        "Payment 500.",
        _call_llm=mock_llm,
    )
    assert result["ok"] is True
    assert result["data"]["label"] == "bug"
    assert call_count == 2, "repair must have been called"


def test_runner_both_invalid_returns_error_no_crash():
    call_count = 0

    def mock_llm(messages):
        nonlocal call_count
        call_count += 1
        return INVALID_JSON  # нет обязательного rationale

    result = run(
        "classify",
        "v1",
        "Classify",
        "Some task.",
        _call_llm=mock_llm,
    )
    assert result["ok"] is False
    assert "error" in result
    assert "diagnostics" in result
    assert call_count == 2


def test_runner_unknown_prompt_returns_error():
    result = run(
        "unknown_prompt",
        "v1",
        "Task",
        "input",
        _call_llm=lambda m: "{}",
    )
    assert result["ok"] is False
    assert "unknown prompt" in result.get("error", "")


def test_runner_extract_valid_first():
    def mock_llm(messages):
        return VALID_EXTRACT_JSON

    result = run("extract", "v1", "Extract", "Payment bug in checkout.", _call_llm=mock_llm)
    assert result["ok"] is True
    assert len(result["data"]["entities"]) == 1
    assert result["data"]["entities"][0]["type"] == "component"
    assert result["data"]["summary"] == "Bug in payment."
