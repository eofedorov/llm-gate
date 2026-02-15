"""Запуск индексации: загрузка документов -> чанкинг -> эмбеддинги (sentence-transformers) -> сохранение в FAISS."""
import time
from pathlib import Path

from app.rag.ingest.chunker import chunk_document
from app.rag.ingest.loader import load_documents
from app.rag.store.faiss_store import FaissStore, metadata_from_chunk
from app.rag.store.models import ChunkMeta
from app.settings import Settings

_settings = Settings()


def _get_embedding_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(_settings.rag_embedding_model)


def run_ingestion(
    kb_path: Path | str | None = None,
    index_dir: Path | str | None = None,
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> dict[str, int | float]:
    """
    Загрузить базу знаний -> чанкинг -> эмбеддинги -> сохранить в FAISS.
    Возвращает { docs_indexed, chunks_indexed, duration_ms }.
    """
    start = time.perf_counter()
    cs = chunk_size if chunk_size is not None else _settings.rag_chunk_size
    ov = overlap if overlap is not None else _settings.rag_chunk_overlap
    docs = load_documents(kb_path)
    if not docs:
        return {"docs_indexed": 0, "chunks_indexed": 0, "duration_ms": 0.0}

    all_chunks: list[ChunkMeta] = []
    for doc in docs:
        all_chunks.extend(
            chunk_document(doc, chunk_size=cs, overlap=ov)
        )

    if not all_chunks:
        return {"docs_indexed": len(docs), "chunks_indexed": 0, "duration_ms": 0.0}

    model = _get_embedding_model()
    texts = [c.text for c in all_chunks]
    vectors = model.encode(texts, show_progress_bar=False).tolist()

    store = FaissStore(index_dir=index_dir)
    metadata = [metadata_from_chunk(c) for c in all_chunks]
    store.save(vectors, metadata)

    elapsed_ms = (time.perf_counter() - start) * 1000
    return {
        "docs_indexed": len(docs),
        "chunks_indexed": len(all_chunks),
        "duration_ms": round(elapsed_ms, 2),
    }
