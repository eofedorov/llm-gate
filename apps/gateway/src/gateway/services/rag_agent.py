"""
Agent loop: вопрос пользователя -> LLM с tools (MCP) -> до 6 вызовов инструментов -> финальный ответ AnswerContract.
"""
import json
import logging
from typing import Any
from uuid import UUID

from audit import audit_event, audited_span
from common.contracts.rag_schemas import AnswerContract
from gateway.llm import client as llm_client
from gateway.mcp.client.mcp_client import call_tool as mcp_call_tool
from gateway.mcp.client.mcp_client import list_tools as mcp_list_tools
from gateway.prompts.system_prompts import INSUFFICIENT_ANSWER, RAG_AGENT_SYSTEM_PROMPT
from gateway.services.llm_json import parse_llm_response_or_repair

MAX_TOOL_CALLS_PER_REQUEST = 6

logger = logging.getLogger(__name__)


@audited_span("llm.call", kind="llm.call")
def _call_llm_with_tools_audited(messages: list, tools: list) -> Any:
    return llm_client.call_llm_with_tools(messages, tools)


def _format_tool_error(exc: BaseException) -> str:
    if isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        return _format_tool_error(exc.exceptions[0])
    return str(exc)


def ask(
    question: str,
    run_id: UUID | str | None = None,
    mcp_url: str | None = None,
    request: Any = None,
) -> AnswerContract:
    """
    Agent loop: получить tools из MCP -> цикл LLM + tool_calls (до 6 вызовов) -> разобрать финальный ответ в AnswerContract.
    """
    logger.info("[AGENT] ask question=%r", question.strip()[:80] if len(question.strip()) > 80 else question.strip())
    tools = mcp_list_tools(mcp_url)
    if not tools:
        logger.warning("[AGENT] no MCP tools -> insufficient_context")
        audit_event("decision", reason="no_tools", status="insufficient_context")
        return AnswerContract(
            answer=INSUFFICIENT_ANSWER,
            confidence=0.0,
            sources=[],
            status="insufficient_context",
        )

    messages: list[dict] = [
        {"role": "system", "content": RAG_AGENT_SYSTEM_PROMPT},
        {"role": "user", "content": question.strip()},
    ]
    total_tool_calls = 0
    last_finish_reason: str | None = None

    def _set_audit_finish_reason(reason: str | None) -> None:
        if request is not None and hasattr(request, "state"):
            request.state.audit_finish_reason = reason

    while total_tool_calls < MAX_TOOL_CALLS_PER_REQUEST:
        completion = _call_llm_with_tools_audited(messages, tools)
        choice = completion.choices[0] if completion.choices else None
        if choice and getattr(completion, "usage", None):
            u = completion.usage
            last_finish_reason = getattr(choice, "finish_reason", None)
            audit_event(
                "llm.completion",
                total_tokens=getattr(u, "total_tokens", None),
                finish_reason=last_finish_reason,
            )
        if not choice:
            break
        msg = choice.message
        content = getattr(msg, "content", None) if msg else None
        tool_calls = getattr(msg, "tool_calls", None) if msg else []

        if not tool_calls and content:
            parsed, _ = parse_llm_response_or_repair(
                content or "", AnswerContract, llm_client.call_llm
            )
            if parsed is not None:
                logger.info("[AGENT] done status=%s", parsed.status)
                _set_audit_finish_reason(last_finish_reason)
                return parsed
            logger.info("[AGENT] parse/repair failed -> insufficient_context")
            audit_event("decision", reason="parse_failed", status="insufficient_context")
            _set_audit_finish_reason(last_finish_reason)
            return AnswerContract(
                answer=INSUFFICIENT_ANSWER,
                confidence=0.0,
                sources=[],
                status="insufficient_context",
            )

        if not tool_calls:
            break

        assistant_msg: dict = {"role": "assistant", "content": content or ""}
        assistant_msg["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.function.name, "arguments": tc.function.arguments or "{}"},
            }
            for tc in tool_calls
        ]
        messages.append(assistant_msg)

        for tc in tool_calls:
            if total_tool_calls >= MAX_TOOL_CALLS_PER_REQUEST:
                break
            name = tc.function.name
            try:
                args_str = tc.function.arguments or "{}"
                args = json.loads(args_str)
            except json.JSONDecodeError as e:
                logger.error("tool_call arguments JSON decode error name=%s: %s", name, e)
                args = {}
            try:
                logger.info("[AGENT] tool_call name=%s args=%s", name, list(args.keys()) if args else [])
                result = mcp_call_tool(name, args, mcp_url=mcp_url, run_id=run_id)  # pyright: ignore[reportArgumentType]
                result_str = json.dumps(result, ensure_ascii=False)
            except (Exception, BaseExceptionGroup) as e:
                msg = _format_tool_error(e)
                logger.error("[AGENT] tool_call failed name=%s: %s", name, msg)
                result_str = json.dumps({"error": msg}, ensure_ascii=False)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result_str,
            })
            total_tool_calls += 1

    logger.info("[AGENT] max_tool_calls or no valid answer -> insufficient_context")
    audit_event("decision", reason="max_tool_calls", status="insufficient_context")
    _set_audit_finish_reason(last_finish_reason)
    return AnswerContract(
        answer=INSUFFICIENT_ANSWER,
        confidence=0.0,
        sources=[],
        status="insufficient_context",
    )
