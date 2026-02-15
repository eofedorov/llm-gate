"""
Подсчёт токенов промпта до вызова LLM (tiktoken).

Используется для логирования, проверки лимита контекста и оценки стоимости.
Формат сообщений: [{"role": "system"|"user"|"assistant", "content": "..."}, ...].
"""
import logging
from typing import Any

import tiktoken

logger = logging.getLogger(__name__)

# Накладные расходы на сообщение и на ответ (как в документации OpenAI)
TOKENS_PER_MESSAGE = 3
TOKENS_PER_REPLY_PRIMER = 3


def _get_encoding(model: str) -> tiktoken.Encoding:
    """Кодировка для модели; при неизвестной модели — o200k_base (gpt-4o и др.)."""
    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        logger.debug("tiktoken: model %s not found, using o200k_base", model)
        return tiktoken.get_encoding("o200k_base")


def count_tokens(messages: list[dict[str, Any]], model: str) -> int:
    """
    Оценка числа токенов для списка сообщений в формате chat API.

    Учитывается служебный overhead (роли, формат). Для неизвестных моделей
    используется кодировка o200k_base. Результат может немного отличаться
    от фактического usage в ответе API.
    """
    if not model or not messages:
        return 0
    encoding = _get_encoding(model)
    num_tokens = 0
    for message in messages:
        num_tokens += TOKENS_PER_MESSAGE
        for key, value in message.items():
            if value is None:
                continue
            num_tokens += len(encoding.encode(str(value)))
            if key == "name":
                num_tokens += 1
    num_tokens += TOKENS_PER_REPLY_PRIMER
    return num_tokens
