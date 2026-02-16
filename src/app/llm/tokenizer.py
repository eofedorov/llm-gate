"""
Подсчёт токенов промпта до вызова LLM (tiktoken).
Формат сообщений: [{"role": "system"|"user"|"assistant", "content": "..."}, ...].
"""
from typing import Any

import tiktoken

# Накладные расходы на сообщение и на ответ (как в документации OpenAI)
TOKENS_PER_MESSAGE = 3
TOKENS_PER_REPLY_PRIMER = 3

def count_tokens(messages: list[dict[str, Any]]) -> int:
    """
    Оценка числа токенов для списка сообщений в формате chat API.
    Учитывается служебный overhead (роли, формат).
    """
    encoding = tiktoken.get_encoding("o200k_base")
    num_tokens = 0
    for message in messages:
        num_tokens += TOKENS_PER_MESSAGE
        for key, value in message.items():
            num_tokens += len(encoding.encode(str(value)))
            if key == "name":
                num_tokens += 1
    num_tokens += TOKENS_PER_REPLY_PRIMER
    return num_tokens
