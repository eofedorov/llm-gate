"""Сбор контекста из retrieval -> runner (render + LLM + валидация + repair) -> пост-обработка AnswerContract."""
import logging

from app.contracts.rag_schemas import AnswerContract
from app.rag.formats import normalize_text
from app.rag.retrieve import retrieve
from app.services import runner
from app.settings import Settings

logger = logging.getLogger(__name__)
_settings = Settings()

INSUFFICIENT_ANSWER = "In the knowledge base there is no answer to this question."


def _build_context_chunks(chunks: list[tuple[str, float, dict]]) -> str:
    """Форматирование полученных чанков для промпта: chunk_id, title, text."""
    parts = []
    for chunk_id, score, meta in chunks:
        title = meta.get("title") or ""
        text = meta.get("text") or ""
        parts.append(f"[{chunk_id}] {title}\n{normalize_text(text)}")
    return "\n\n---\n\n".join(parts)


def ask(
    question: str,
    k: int | None = None,
    filters: dict | None = None,
    strict_mode: bool = False,
    *,
    _call_llm=None,
    _retrieve=None,
) -> AnswerContract:
    """
    Получить top-k чанков -> runner.run (render + LLM + валидация + repair) -> пост-обработка.
    При отсутствии чанков или ошибке runner возвращает status=insufficient_context.
    """
    do_retrieve = _retrieve if _retrieve is not None else retrieve
    k_val = k if k is not None else _settings.rag_default_k

    chunks = do_retrieve(question.strip(), k=k_val, filters=filters or None)
    doc_ids = [m.get("doc_id") for _, _, m in chunks]
    logger.info("[RAG ask] chunks_used=%d doc_ids=%s", len(chunks), doc_ids)

    if not chunks:
        return AnswerContract(
            answer=INSUFFICIENT_ANSWER,
            confidence=0.0,
            sources=[],
            status="insufficient_context",
        )

    context_chunks = _build_context_chunks(chunks)
    prompt_name = "rag_ask_strict" if strict_mode else "rag_ask"

    result = runner.run(
        prompt_name=prompt_name,
        version="v1",
        task=question.strip(),
        input_data="",
        extras={"context_chunks": context_chunks, "question": question.strip()},
        _call_llm=_call_llm,
    )

    if not result.get("ok"):
        return AnswerContract(
            answer=INSUFFICIENT_ANSWER,
            confidence=0.0,
            sources=[],
            status="insufficient_context",
        )

    contract = AnswerContract.model_validate(result["data"])

    # Принудительно insufficient_context при слишком низкой средней relevance
    if contract.sources and contract.status == "ok":
        avg_rel = sum(s.relevance for s in contract.sources) / len(contract.sources)
        if avg_rel < _settings.rag_relevance_threshold:
            logger.info("[RAG ask] avg relevance %.2f < threshold, forcing insufficient_context", avg_rel)
            return AnswerContract(
                answer=INSUFFICIENT_ANSWER,
                confidence=0.0,
                sources=[],
                status="insufficient_context",
            )

    return contract
