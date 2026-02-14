"""Normalize and clean text before chunking and before sending to LLM."""
import re


def normalize_text(text: str) -> str:
    """
    Normalize text: collapse whitespace, strip, remove excessive newlines.
    Used before chunking and when preparing context for LLM.
    """
    if not text or not isinstance(text, str):
        return ""
    t = text.strip()
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def truncate_preview(text: str, max_chars: int = 300) -> str:
    """Truncate text for search result preview."""
    if not text:
        return ""
    normalized = normalize_text(text)
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3].rstrip() + "..."
