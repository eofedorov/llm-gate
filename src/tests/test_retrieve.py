"""Retrieval: после индексации поиск возвращает релевантные чанки."""
import tempfile
from pathlib import Path

import pytest

from app.rag.ingest.indexer import run_ingestion
from app.rag.retrieve import retrieve
from app.rag.store.faiss_store import FaissStore, INDEX_FILE, METADATA_FILE


def test_retrieve_without_index_returns_empty():
    """При отсутствии индекса retrieve возвращает пустой список."""
    with tempfile.TemporaryDirectory() as tmp:
        store = FaissStore(index_dir=tmp)
        results = retrieve("Redis cache bypass", k=3, store=store)
    assert results == []


@pytest.mark.slow
def test_retrieve_after_ingest_returns_chunks():
    """Индексация в tmp → проверка, что индекс и метаданные на диске → retrieve возвращает чанки."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        run_ingestion(index_dir=tmp_path)
        index_file = tmp_path / INDEX_FILE
        meta_file = tmp_path / METADATA_FILE
        assert index_file.exists() and index_file.stat().st_size > 0
        assert meta_file.exists() and meta_file.stat().st_size > 0

        store = FaissStore(index_dir=tmp_path)
        results = retrieve("Redis evictions cart staleness", k=3, store=store)
    assert len(results) > 0
    for chunk_id, score, meta in results:
        assert chunk_id.startswith("doc:")
        assert "#chunk:" in chunk_id
        assert "doc_id" in meta
        assert "title" in meta
        assert "text" in meta
