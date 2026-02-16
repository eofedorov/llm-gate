"""Тесты подсчёта токенов (tiktoken, o200k_base)."""
from app.llm.tokenizer import TOKENS_PER_REPLY_PRIMER, count_tokens


def test_count_tokens_empty_messages():
    """Пустой список сообщений — только overhead (reply primer)."""
    assert count_tokens([]) == TOKENS_PER_REPLY_PRIMER


def test_count_tokens_single_message():
    messages = [{"role": "user", "content": "Hello"}]
    n = count_tokens(messages)
    assert n > 0
    assert n < 50


def test_count_tokens_system_user():
    messages = [
        {"role": "system", "content": "You are a helper."},
        {"role": "user", "content": "Say OK."},
    ]
    n = count_tokens(messages)
    assert n > 0
    assert n < 100
