"""Build context from retrieval -> render RAG prompt -> call LLM -> parse AnswerContract."""
import json
import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.contracts.rag_schemas import AnswerContract
from app.llm import client as llm_client
from app.rag.formats import normalize_text
from app.rag.retrieve import retrieve

logger = logging.getLogger(__name__)

RAG_TEMPLATES_DIR = Path(__file__).resolve().parent / "prompts" / "templates"
RELEVANCE_THRESHOLD = 0.3  # ниже — не резать ответы, у которых модель поставила умеренную relevance
INSUFFICIENT_ANSWER = "In the knowledge base there is no answer to this question."

# Жёсткая схема ответа для промпта (как в render.py), чтобы модель не путала формат sources
RAG_OUTPUT_CONTRACT = """Только этот JSON, без других полей:
{"answer": "<string>", "confidence": <float 0-1>, "sources": [{"chunk_id": "<string>", "doc_title": "<string>", "quote": "<string>", "relevance": <float 0-1>}, ...], "status": "ok" | "insufficient_context"}"""

REPAIR_SYSTEM = "Преобразуй ответ в валидный JSON по указанной схеме. Выведи только JSON, без пояснений до или после."


def _extract_json_from_text(text: str) -> str:
    text = text.strip()
    start = text.find("{")
    if start == -1:
        return text
    end = text.rfind("}")
    if end == -1 or end < start:
        return text
    return text[start : end + 1]


def _parse_contract(raw: str) -> AnswerContract | None:
    """Парсинг и валидация по AnswerContract. Без нормализации — ожидаем валидный JSON."""
    try:
        data = json.loads(raw)
        return AnswerContract.model_validate(data)
    except Exception:
        return None


def _build_context_chunks(chunks: list[tuple[str, float, dict]]) -> str:
    """Format retrieved chunks for the prompt: chunk_id, title, text."""
    parts = []
    for chunk_id, score, meta in chunks:
        title = meta.get("title") or ""
        text = meta.get("text") or ""
        parts.append(f"[{chunk_id}] {title}\n{normalize_text(text)}")
    return "\n\n---\n\n".join(parts)


def ask(
    question: str,
    k: int = 5,
    filters: dict | None = None,
    strict_mode: bool = False,
    *,
    _call_llm=None,
    _retrieve=None,
) -> AnswerContract:
    """
    Retrieve top-k chunks -> render prompt -> LLM -> parse AnswerContract.
    If no chunks or parsing fails, return status=insufficient_context.
    """
    do_retrieve = _retrieve if _retrieve is not None else retrieve
    call_llm = _call_llm if _call_llm is not None else llm_client.call_llm

    chunks = do_retrieve(question.strip(), k=k, filters=filters or None)
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
    template_name = "answer_strict_v1.txt" if strict_mode else "answer_with_citations_v1.txt"
    output_contract = RAG_OUTPUT_CONTRACT

    env = Environment(
        loader=FileSystemLoader(RAG_TEMPLATES_DIR),
        autoescape=select_autoescape(default=False),
    )
    template = env.get_template(template_name)
    user_message = template.render(
        question=question.strip(),
        context_chunks=context_chunks,
        output_contract=output_contract,
    ).strip()

    system_message = "Respond with valid JSON only, following the given schema. No text before or after the JSON."
    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_message},
    ]

    raw_response = call_llm(messages)
    parsed = _extract_json_from_text(raw_response)
    contract = _parse_contract(parsed)

    if contract is None:
        logger.warning("[RAG ask] JSON parse/validation failed, triggering repair. raw_tail=%s", raw_response[-500:] if len(raw_response) > 500 else raw_response)
        repair_messages = [
            {"role": "system", "content": REPAIR_SYSTEM + "\n\nСхема:\n" + output_contract},
            {"role": "user", "content": "Исправь в валидный JSON:\n" + raw_response[:4000]},
        ]
        raw_repair = call_llm(repair_messages)
        parsed_repair = _extract_json_from_text(raw_repair)
        contract = _parse_contract(parsed_repair)
        if contract is None:
            logger.warning("[RAG ask] repair failed, returning insufficient_context")
            return AnswerContract(
                answer=INSUFFICIENT_ANSWER,
                confidence=0.0,
                sources=[],
                status="insufficient_context",
            )
        logger.info("[RAG ask] ok after repair")

    # Optional: force insufficient if mean relevance too low
    if contract.sources and contract.status == "ok":
        avg_rel = sum(s.relevance for s in contract.sources) / len(contract.sources)
        if avg_rel < RELEVANCE_THRESHOLD:
            logger.info("[RAG ask] avg relevance %.2f < threshold, forcing insufficient_context", avg_rel)
            return AnswerContract(
                answer=INSUFFICIENT_ANSWER,
                confidence=0.0,
                sources=[],
                status="insufficient_context",
            )

    return contract
