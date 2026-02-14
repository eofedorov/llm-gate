"""Retrieval: after ingest, search returns relevant chunks."""
import tempfile
from pathlib import Path

import pytest

try:
    from sentence_transformers import SentenceTransformer  # noqa: F401
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False

from app.rag.ingest.indexer import run_ingestion
from app.rag.retrieve import retrieve
from app.rag.store.faiss_store import FaissStore


def test_retrieve_without_index_returns_empty():
    """When no index exists, retrieve returns empty list."""
    # Use a temp dir with no index
    with tempfile.TemporaryDirectory() as tmp:
        store = FaissStore(index_dir=tmp)
        results = retrieve("Redis cache bypass", k=3, store=store)
    assert results == []


@pytest.mark.slow
@pytest.mark.skipif(not HAS_SENTENCE_TRANSFORMERS, reason="sentence-transformers not installed")
def test_retrieve_after_ingest_returns_chunks():
    """Run full ingest then retrieve; should get chunks with metadata."""
    run_ingestion()
    results = retrieve("Redis evictions cart staleness", k=3)
    assert len(results) > 0
    for chunk_id, score, meta in results:
        assert chunk_id.startswith("doc:")
        assert "#chunk:" in chunk_id
        assert "doc_id" in meta
        assert "title" in meta
        assert "text" in meta
