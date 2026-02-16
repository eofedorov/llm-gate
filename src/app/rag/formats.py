"""Нормализация и очистка текста перед чанкингом и перед отправкой в LLM."""
import re


def normalize_text(text: str) -> str:
    """
    Нормализация текста: схлопнуть пробелы, trim, убрать лишние переносы строк.
    Используется перед чанкингом и при подготовке контекста для LLM.
    """
    t = text.strip()
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def truncate_preview(text: str, max_chars: int = 300) -> str:
    """Обрезать текст для превью результата поиска."""
    normalized = normalize_text(text)
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3].rstrip() + "..."
