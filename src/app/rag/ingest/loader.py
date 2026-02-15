"""Загрузка документов из директории data/ (все *.json с массивом 'documents') или из одного JSON-файла."""
import json
from pathlib import Path
from typing import Any

from app.rag.formats import normalize_text
from app.settings import Settings

_settings = Settings()
# Путь по умолчанию: корень проекта — родитель src (src/app/rag/ingest -> 4 уровня до src, 5 до корня)
_SRC_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_PROJECT_ROOT = _SRC_ROOT.parent
DEFAULT_KB_PATH = Path(_settings.rag_kb_path) if _settings.rag_kb_path else _PROJECT_ROOT / "data"


def _load_from_file(p: Path) -> list[dict[str, Any]]:
    """Загрузить документы из одного JSON-файла."""
    raw = p.read_text(encoding="utf-8")
    data = json.loads(raw)
    docs = data.get("documents") or []
    out: list[dict[str, Any]] = []
    for d in docs:
        doc_id = d.get("doc_id") or ""
        title = d.get("title") or ""
        content = d.get("content") or ""
        if not doc_id or not content:
            continue
        path_val = d.get("path") or doc_id
        out.append({
            "doc_id": doc_id,
            "title": title,
            "path": path_val,
            "document_type": d.get("document_type") or "",
            "created_at": d.get("created_at") or "",
            "content": normalize_text(content),
        })
    return out


def load_documents(path: Path | str | None = None) -> list[dict[str, Any]]:
    """
    Загрузить документы из path. Если path — директория, загружаются все *.json
    (с массивом 'documents'). Если path — файл, загружается этот файл.
    Возвращает список dict с полями: doc_id, title, path, document_type, created_at, content.
    """
    p = Path(path) if path is not None else DEFAULT_KB_PATH
    if not p.exists():
        return []

    out: list[dict[str, Any]] = []

    if p.is_dir():
        for f in sorted(p.glob("*.json")):
            if f.name == "metadata.json":
                continue
            out.extend(_load_from_file(f))
    else:
        out = _load_from_file(p)

    return out
