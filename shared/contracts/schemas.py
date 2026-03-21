"""Pydantic-модели ответа (output contracts). Строгая валидация, extra='forbid'."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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


class ExtractV1Out(BaseModel):
    """Выход контракта extract_v1."""
    model_config = ConfigDict(extra="forbid")

    entities: list[Entity]
    summary: str = Field(max_length=2000)
