"""Реестр промптов по имени и версии."""
from pathlib import Path
from typing import Type

from pydantic import BaseModel

from common.contracts.rag_schemas import AnswerContract
from common.contracts.schemas import ClassifyV1Out, ExtractV1Out

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


class PromptSpec:
    """Описание промпта: имя, версия, шаблон, правила, схема вывода."""
    name: str
    version: str
    template_path: Path
    system_rules: str
    output_schema: Type[BaseModel]

    def __init__(
        self,
        name: str,
        version: str,
        template_filename: str,
        system_rules: str,
        output_schema: Type[BaseModel],
    ):
        self.name = name
        self.version = version
        self.template_path = TEMPLATES_DIR / template_filename
        self.system_rules = system_rules
        self.output_schema = output_schema

    @property
    def key(self) -> str:
        return f"{self.name}_{self.version}"


def _registry() -> dict[str, PromptSpec]:
    return {
        "classify_v1": PromptSpec(
            name="classify",
            version="v1",
            template_filename="classify_v1.txt",
            system_rules="Отвечай строго JSON по схеме. Никакого текста до или после JSON.",
            output_schema=ClassifyV1Out,
        ),
        "extract_v1": PromptSpec(
            name="extract",
            version="v1",
            template_filename="extract_v1.txt",
            system_rules="Отвечай строго JSON по схеме. Никакого текста до или после JSON.",
            output_schema=ExtractV1Out,
        ),
        "rag_ask_v1": PromptSpec(
            name="rag_ask",
            version="v1",
            template_filename="rag_ask_v1.txt",
            system_rules="Respond with valid JSON only, following the given schema. No text before or after the JSON.",
            output_schema=AnswerContract,
        ),
        "rag_ask_v2": PromptSpec(
            name="rag_ask",
            version="v2",
            template_filename="rag_ask_v2.txt",
            system_rules="Respond with valid JSON only, following the given schema. No text before or after the JSON.",
            output_schema=AnswerContract,
        ),
    }


REGISTRY: dict[str, PromptSpec] = _registry()


def get_prompt(key: str) -> PromptSpec | None:
    return REGISTRY.get(key)


def get_prompt_by_name_version(name: str, version: str) -> PromptSpec | None:
    return get_prompt(f"{name}_{version}")


def list_prompts() -> list[dict]:
    return [{"name": spec.name, "version": spec.version} for spec in REGISTRY.values()]
