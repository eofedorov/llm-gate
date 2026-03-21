"""Подсчёт токенов промпта до вызова LLM (tiktoken)."""
from typing import Any

import tiktoken

TOKENS_PER_MESSAGE = 3
TOKENS_PER_REPLY_PRIMER = 3


def count_tokens(messages: list[dict[str, Any]]) -> int:
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
