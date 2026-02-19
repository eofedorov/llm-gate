"""Индексация: загрузка документов -> проверка sha256 (идемпотентность) -> Postgres -> чанкинг -> эмбеддинги -> Qdrant."""
import hashlib
import logging
import time
from pathlib import Path
from typing import Any

from app.db.connection import get_pool
from app.db.queries import (
    delete_chunks_by_doc_id,
    get_document_by_doc_key,
    insert_chunk,
    insert_document,
    update_document_sha256,
)
from app.rag.ingest.chunker import chunk_document
from app.rag.ingest.loader import load_documents
from app.rag.store.qdrant_store import QdrantStore
from app.settings import Settings

_settings = Settings()
log = logging.getLogger(__name__)


def _sha256_content(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _get_embedding_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(_settings.rag_embedding_model)


def _index_one_document(
    conn: Any,
    doc: dict,
    store: QdrantStore,
    model: Any,
    chunk_size: int,
    overlap: int,
) -> tuple[int, int]:
    """
    Индексировать один документ: sha256, Postgres (doc/chunks), эмбеддинги, upsert в Qdrant.
    Возвращает (1, n_chunks) если документ проиндексирован, (0, 0) если пропущен.
    """
    doc_key = doc.get("path") or doc.get("doc_id") or ""
    content = doc.get("content") or ""
    if not doc_key:
        log.debug("[INGESTION] skip doc: empty doc_key")
        return (0, 0)
    new_sha = _sha256_content(content)
    existing = get_document_by_doc_key(conn, doc_key)
    if existing is not None:
        doc_id, existing_sha = existing
        if existing_sha == new_sha:
            log.debug("[INGESTION] skip doc: unchanged sha doc_key=%s", doc_key[:50])
            return (0, 0)
        update_document_sha256(conn, doc_id, new_sha)
        delete_chunks_by_doc_id(conn, doc_id)
        store.delete_by_doc_id(str(doc_id))
    else:
        doc_id = insert_document(
            conn,
            doc_key=doc_key,
            title=doc.get("title") or "",
            doc_type=doc.get("document_type") or "general",
            language="ru",
            sha256=new_sha,
        )
    chunks = chunk_document(doc, chunk_size=chunk_size, overlap=overlap)
    if not chunks:
        return (1, 0)
    texts = [c.text for c in chunks]
    vectors = model.encode(texts, show_progress_bar=False).tolist()
    title = doc.get("title") or ""
    doc_type = doc.get("document_type") or "general"
    language = doc.get("language") or "ru"
    points: list[tuple[str, list[float], dict]] = []
    for chunk, vec in zip(chunks, vectors):
        chunk_id_uuid = insert_chunk(
            conn,
            doc_id=doc_id,
            chunk_index=chunk.chunk_index,
            section=chunk.section or None,
            text=chunk.text,
            embedding_ref=None,
        )
        payload = {
            "doc_id": str(doc_id),
            "doc_key": doc_key,
            "title": title,
            "doc_type": doc_type,
            "language": language,
            "chunk_id": str(chunk_id_uuid),
            "chunk_index": chunk.chunk_index,
            "section": chunk.section or "",
            "text": chunk.text,
        }
        points.append((str(chunk_id_uuid), vec, payload))
    store.upsert(points)
    log.debug("[INGESTION] indexed doc_key=%s chunks=%d", doc_key[:50], len(points))
    return (1, len(points))


def run_ingestion(
    index_dir: Path | str | None = None,
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> dict[str, int | float]:
    """
    Загрузить базу знаний (путь из env) -> по sha256 пропустить неизменённые
    -> Postgres (documents + chunks) -> эмбеддинги -> upsert в Qdrant.
    При обновлении документа старые точки в Qdrant удаляются.
    Возвращает { docs_indexed, chunks_indexed, duration_ms }.
    """
    log.info("[INGESTION] start")
    start = time.perf_counter()
    cs = chunk_size if chunk_size is not None else _settings.rag_chunk_size
    ov = overlap if overlap is not None else _settings.rag_chunk_overlap
    docs = load_documents()
    log.info("[INGESTION] loaded docs=%d chunk_size=%d overlap=%d", len(docs), cs, ov)
    store = QdrantStore()
    store.ensure_collection()
    model = _get_embedding_model()
    docs_indexed = 0
    chunks_indexed = 0
    pool = get_pool()
    with pool.connection() as conn:
        for doc in docs:
            d, c = _index_one_document(conn, doc, store, model, cs, ov)
            docs_indexed += d
            chunks_indexed += c
    elapsed_ms = (time.perf_counter() - start) * 1000
    log.info(
        "[INGESTION] done docs_indexed=%d chunks_indexed=%d duration_ms=%.2f",
        docs_indexed, chunks_indexed, round(elapsed_ms, 2),
    )
    return {
        "docs_indexed": docs_indexed,
        "chunks_indexed": chunks_indexed,
        "duration_ms": round(elapsed_ms, 2),
    }
