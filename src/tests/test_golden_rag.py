"""
Golden set acceptance: 15 questions must retrieve at least one chunk from expected doc;
5 provocation questions must get insufficient_context when retrieve returns empty.
"""
import json
from pathlib import Path

import pytest

try:
    from sentence_transformers import SentenceTransformer  # noqa: F401
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False

from app.rag.ask_service import ask
from app.rag.ingest.indexer import run_ingestion
from app.rag.retrieve import retrieve

GOLDEN_PATH = Path(__file__).resolve().parent / "golden" / "questions.json"


def _load_questions():
    raw = GOLDEN_PATH.read_text(encoding="utf-8")
    return json.loads(raw)


@pytest.fixture(scope="module")
def indexed():
    """Run ingestion once per module so FAISS index exists."""
    run_ingestion()
    return None


@pytest.mark.skipif(not HAS_SENTENCE_TRANSFORMERS, reason="sentence-transformers not installed")
def test_golden_retrieve_ok_questions(indexed):
    """For each of the 15 'ok' questions, retrieval should return at least one chunk from expected doc."""
    questions = _load_questions()
    ok_cases = [q for q in questions if q.get("expected_status") == "ok"]
    assert len(ok_cases) >= 15, "Golden set must have at least 15 ok questions"
    failed = []
    for q in ok_cases:
        results = retrieve(q["question"], k=5)
        expected_ids = set(q.get("expected_doc_ids") or [])
        found_doc_ids = {m.get("doc_id") for _, _, m in results}
        if not expected_ids & found_doc_ids:
            failed.append((q["question"][:50], expected_ids, list(found_doc_ids)[:3]))
    assert not failed, f"Retrieve failed for {len(failed)} questions: {failed[:5]}"


def test_golden_ask_insufficient_context():
    """For provocation questions, when retrieve returns empty, ask returns insufficient_context."""
    questions = _load_questions()
    insufficient = [q for q in questions if q.get("expected_status") == "insufficient_context"]
    assert len(insufficient) >= 5, "Golden set must have at least 5 insufficient_context questions"

    def empty_retrieve(_query, k=5, filters=None):
        return []

    for q in insufficient:
        contract = ask(q["question"], k=5, _retrieve=empty_retrieve)
        assert contract.status == "insufficient_context", f"Expected insufficient_context for: {q['question'][:50]}"
        assert len(contract.sources) == 0
