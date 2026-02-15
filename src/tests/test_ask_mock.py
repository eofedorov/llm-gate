"""Ask service: замоканный LLM возвращает валидный AnswerContract; при отсутствии контекста — insufficient."""
import pytest

from app.contracts.rag_schemas import AnswerContract
from app.rag.ask_service import ask


def test_ask_empty_retrieve_returns_insufficient():
    """При пустом retrieve ask возвращает insufficient_context без вызова LLM."""
    def empty_retrieve(_q, k=5, filters=None):
        return []

    contract = ask("What is Redis?", k=5, _retrieve=empty_retrieve)
    assert contract.status == "insufficient_context"
    assert len(contract.sources) == 0
    assert "no answer" in contract.answer.lower() or "knowledge" in contract.answer.lower()


def test_ask_mock_llm_valid_json_returns_contract():
    """При чанках от retrieve и валидном AnswerContract JSON от LLM получаем распарсенный контракт."""
    def fake_retrieve(q, k=5, filters=None):
        return [
            ("doc:kb-2026-02-runbook-redis-evictions#chunk:0", 0.9, {
                "chunk_id": "doc:kb-2026-02-runbook-redis-evictions#chunk:0",
                "doc_id": "kb-2026-02-runbook-redis-evictions",
                "title": "Runbook: Redis Evictions",
                "path": "",
                "document_type": "runbook",
                "created_at": "",
                "section": "",
                "chunk_index": 0,
                "text": "Redis eviction causes cart staleness. Use CART_CACHE_BYPASS=true.",
            }),
        ]

    valid_json = '''{
      "answer": "Enable cache bypass with CART_CACHE_BYPASS=true.",
      "confidence": 0.85,
      "sources": [
        {"chunk_id": "doc:kb-2026-02-runbook-redis-evictions#chunk:0", "doc_title": "Runbook: Redis Evictions", "quote": "CART_CACHE_BYPASS=true", "relevance": 0.9}
      ],
      "status": "ok"
    }'''

    def mock_llm(messages):
        return valid_json

    contract = ask("How to fix Redis cart issues?", k=5, _retrieve=fake_retrieve, _call_llm=mock_llm)
    assert contract.status == "ok"
    assert len(contract.sources) == 1
    assert contract.sources[0].chunk_id == "doc:kb-2026-02-runbook-redis-evictions#chunk:0"
    assert contract.confidence >= 0 and contract.confidence <= 1


def test_ask_mock_llm_invalid_json_returns_insufficient():
    """При невалидном JSON от LLM ask возвращает insufficient_context."""
    def fake_retrieve(q, k=5, filters=None):
        return [("doc:x#chunk:0", 0.8, {"chunk_id": "doc:x#chunk:0", "doc_id": "x", "title": "X", "text": "y"})]

    def mock_llm(messages):
        return "This is not JSON at all."

    contract = ask("Anything?", k=5, _retrieve=fake_retrieve, _call_llm=mock_llm)
    assert contract.status == "insufficient_context"
    assert len(contract.sources) == 0
