"""
RAG agent: вопрос пользователя -> Cursor SDK agent с MCP tools -> AnswerContract.
"""
import logging
from typing import Any
from uuid import UUID

from audit import audit_event, audited_span
from contracts.rag_schemas import AnswerContract
from orchestrator.llm import client as llm_client
from orchestrator.llm import cursor_sdk_client
from orchestrator.prompts.system_prompts import INSUFFICIENT_ANSWER, RAG_AGENT_SYSTEM_PROMPT
from orchestrator.services.llm_json import parse_llm_response_or_repair
from orchestrator.settings import Settings

logger = logging.getLogger(__name__)
_settings = Settings()


@audited_span("llm.call", kind="llm.call")
def _call_rag_agent_audited(question: str, *, mcp_url: str | None = None) -> str:
    return cursor_sdk_client.call_rag(
        question=question,
        system_prompt=RAG_AGENT_SYSTEM_PROMPT,
        mcp_server_url=mcp_url or _settings.mcp_server_url,
    )


def _insufficient(reason: str) -> AnswerContract:
    audit_event("decision", reason=reason, status="insufficient_context")
    return AnswerContract(
        answer=INSUFFICIENT_ANSWER,
        confidence=0.0,
        sources=[],
        status="insufficient_context",
    )


def ask(
    question: str,
    run_id: UUID | str | None = None,
    mcp_url: str | None = None,
    request: Any = None,
) -> AnswerContract:
    logger.info("[AGENT] ask question=%r", question.strip()[:80] if len(question.strip()) > 80 else question.strip())
    if run_id is not None:
        audit_event("rag.run", run_id=str(run_id))

    effective_mcp_url = mcp_url or _settings.mcp_server_url
    if not effective_mcp_url:
        logger.warning("[AGENT] no MCP URL -> insufficient_context")
        return _insufficient("no_mcp_url")

    def _set_audit_finish_reason(reason: str | None) -> None:
        if request is not None and hasattr(request, "state"):
            request.state.audit_finish_reason = reason

    try:
        raw_content = _call_rag_agent_audited(question.strip(), mcp_url=effective_mcp_url)
    except Exception as exc:
        logger.exception("[AGENT] Cursor SDK RAG call failed")
        audit_event("decision", reason="cursor_sdk_error", status="insufficient_context", error=str(exc))
        _set_audit_finish_reason("error")
        return _insufficient("cursor_sdk_error")

    parsed, _ = parse_llm_response_or_repair(raw_content or "", AnswerContract, llm_client.call_llm)
    if parsed is not None:
        logger.info("[AGENT] done status=%s", parsed.status)
        _set_audit_finish_reason("finished")
        return parsed

    logger.info("[AGENT] parse/repair failed -> insufficient_context")
    _set_audit_finish_reason("parse_failed")
    return _insufficient("parse_failed")
