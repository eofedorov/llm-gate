"""Load documents from data/knowledge_base.json into a list of doc records."""
import json
from pathlib import Path
from typing import Any

from app.rag.formats import normalize_text

# Default path: project root is parent of src (src/app/rag/ingest -> 4 levels up to src, 5 to root)
_SRC_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_PROJECT_ROOT = _SRC_ROOT.parent
DEFAULT_KB_PATH = _PROJECT_ROOT / "data" / "knowledge_base.json"


def load_documents(path: Path | str | None = None) -> list[dict[str, Any]]:
    """
    Load documents from knowledge_base.json.
    Returns list of dicts with: doc_id, title, path, document_type, created_at, content.
    """
    p = Path(path) if path is not None else DEFAULT_KB_PATH
    if not p.exists():
        return []
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
