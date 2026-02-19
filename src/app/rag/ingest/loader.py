"""Загрузка документов из директории базы знаний: все *.json с массивом 'documents'."""
import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

from app.rag.formats import normalize_text
from app.settings import Settings

_settings = Settings()
DEFAULT_KB_PATH = Path(_settings.kb_path)


def load_documents() -> list[dict[str, Any]]:
    """
    Загрузить документы из папки базы знаний (путь из env kb_path или project_root/data).
    Берёт все *.json в папке, из каждого — массив 'documents'.
    Возвращает список dict: doc_id, title, path, document_type, created_at, content.
    """
    p = DEFAULT_KB_PATH
    if not p.exists():
        log.error("Knowledge base path does not exist: %s", p)
        raise FileNotFoundError(f"Knowledge base path does not exist: {p}")
    if not p.is_dir():
        log.error("Knowledge base path is not a directory: %s", p)
        raise NotADirectoryError(f"Knowledge base path is not a directory: {p}")

    json_files = sorted(p.glob("*.json"))
    if not json_files:
        log.error("Knowledge base directory is empty (no *.json): %s", p)
        raise FileNotFoundError(f"Knowledge base directory is empty (no *.json): {p}")

    out: list[dict[str, Any]] = []
    for f in json_files:
        raw = f.read_text(encoding="utf-8")
        data = json.loads(raw)
        docs = data.get("documents") or []
        for d in docs:
            doc_id = d.get("doc_id") or d.get("doc_key") or ""
            title = d.get("title") or ""
            content = d.get("content") or ""
            if not doc_id or not content:
                continue
            path_val = d.get("path") or doc_id
            out.append({
                "doc_id": doc_id,
                "title": title,
                "path": path_val,
                "document_type": d.get("document_type") or d.get("doc_type") or "",
                "created_at": d.get("created_at") or "",
                "content": normalize_text(content),
            })
    return out
