"""Чанкер: чанки имеют метаданные и перекрытие."""
import pytest

from app.rag.ingest.chunker import chunk_text, chunk_document
from app.rag.store.models import make_chunk_id


def test_make_chunk_id():
    assert make_chunk_id("doc-1", 0) == "doc:doc-1#chunk:0"
    assert make_chunk_id("kb-2026-02-runbook-redis-evictions", 12) == "doc:kb-2026-02-runbook-redis-evictions#chunk:12"


def test_chunk_text_empty_returns_empty():
    assert chunk_text("", doc_id="x", title="t") == []
    assert chunk_text("  \n  ", doc_id="x", title="t") == []


def test_chunk_text_single_chunk():
    text = "Short piece."
    chunks = chunk_text(text, doc_id="d1", title="T", chunk_size=512, overlap=64)
    assert len(chunks) == 1
    assert chunks[0].chunk_id == "doc:d1#chunk:0"
    assert chunks[0].doc_id == "d1"
    assert chunks[0].title == "T"
    assert chunks[0].chunk_index == 0
    assert chunks[0].text == "Short piece."


def test_chunk_text_multiple_with_overlap():
    # 100 символов, chunk_size=30, overlap=10 -> следующий start = 30-10=20
    text = "a" * 100
    chunks = chunk_text(text, doc_id="d1", title="T", chunk_size=30, overlap=10)
    assert len(chunks) >= 2
    for i, c in enumerate(chunks):
        assert c.chunk_id == f"doc:d1#chunk:{i}"
        assert c.chunk_index == i
        assert len(c.text) <= 30


def test_chunk_document():
    doc = {
        "doc_id": "test-doc",
        "title": "Test",
        "path": "path/to/doc",
        "document_type": "runbook",
        "created_at": "2026-01-01",
        "content": "First paragraph here.\n\nSecond paragraph there.",
    }
    chunks = chunk_document(doc, chunk_size=20, overlap=5)
    assert len(chunks) >= 1
    assert all(c.doc_id == "test-doc" for c in chunks)
    assert all(c.title == "Test" for c in chunks)
    assert all(c.document_type == "runbook" for c in chunks)
