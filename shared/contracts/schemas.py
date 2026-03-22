"""Pydantic-модели ответа (output contracts). Строгая валидация, extra='forbid'."""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ClassifyV1Out(BaseModel):
    """Выход контракта classify_v1."""
    model_config = ConfigDict(extra="forbid")

    label: Literal["bug", "feature", "question", "other"]
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str


class Entity(BaseModel):
    """Элемент списка entities для extract_v1."""
    model_config = ConfigDict(extra="forbid")

    type: str
    value: str

    @field_validator("value", mode="before")
    @classmethod
    def coerce_entity_value_to_str(cls, v: Any) -> str:
        """LLM иногда отдаёт несколько значений списком; контракт хранит одну строку."""
        if isinstance(v, str):
            return v
        if isinstance(v, list):
            return ", ".join(str(x) for x in v)
        if v is None:
            return ""
        return str(v)


class ExtractV1Out(BaseModel):
    """Выход контракта extract_v1."""
    model_config = ConfigDict(extra="forbid")

    entities: list[Entity]
    summary: str = Field(max_length=2000)
