import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from gateway.llm.client import call_llm
from gateway.prompts.registry import get_prompt
from gateway.prompts.render import RenderContext, get_schema_description, render
from gateway.services.llm_json import parse_llm_response_or_repair


logger = logging.getLogger(__name__)
router = APIRouter()


class RunRequest(BaseModel):
    task: str = ""
    input: str | dict
    constraints: dict | None = None


def _build_messages(spec, body: RunRequest) -> list[dict[str, Any]]:
    schema_description = get_schema_description(spec.output_schema)
    context = RenderContext(
        task=body.task,
        input_data=body.input,
        constraints=body.constraints or {},
        output_contract=schema_description,
    )
    system_message, user_message = render(spec, context)
    return [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_message},
    ]


@router.post("/{prompt_name}")
def run_prompt(prompt_name: str, body: RunRequest):
    """Запустить промпт по имени (classify_v1, extract_v1 и т.п.) и вернуть распарсенный контракт."""
    spec = get_prompt(prompt_name)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"Unknown prompt: {prompt_name}")

    messages = _build_messages(spec, body)
    try:
        raw_content = call_llm(messages)
    except Exception as e:
        logger.exception("LLM call failed for prompt=%s", prompt_name)
        raise HTTPException(status_code=502, detail=f"LLM call failed: {e!s}") from e

    model, err = parse_llm_response_or_repair(raw_content, spec.output_schema, call_llm)
    if model is None:
        logger.error("LLM response parsing failed for prompt=%s: %s", prompt_name, err)
        raise HTTPException(status_code=502, detail=f"Invalid LLM response: {err}")

    return model

