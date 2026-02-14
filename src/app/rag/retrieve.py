"""Retrieval: query -> embed -> top-k chunks with score and metadata."""
from typing import Any

from app.rag.ingest.indexer import EMBEDDING_MODEL
from app.rag.store.faiss_store import FaissStore


def _get_embedding_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(EMBEDDING_MODEL)


# Module-level cache for the model
_model = None


def _model_singleton():
    global _model
    if _model is None:
        _model = _get_embedding_model()
    return _model


def retrieve(
    query: str,
    k: int = 5,
    filters: dict[str, Any] | None = None,
    store: FaissStore | None = None,
) -> list[tuple[str, float, dict[str, Any]]]:
    """
    Encode query, search FAISS, return list of (chunk_id, score, meta).
    meta includes doc_id, title, path, text, etc.
    """
    if not query or not query.strip():
        return []
    s = store if store is not None else FaissStore()
    if not s.load():
        return []
    model = _model_singleton()
    qv = model.encode([query.strip()], show_progress_bar=False).tolist()[0]
    return s.search(qv, k=k, filters=filters)
