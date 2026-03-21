"""Контракты (schemas), общие для gateway и mcp_server."""
from contracts.api_schemas import (
    AskRequestBody,
    IngestResponse,
    RunRequest,
    SearchHit,
    UploadStubResponse,
)
from contracts.rag_schemas import AnswerContract, SourceCitation
from contracts.schemas import ClassifyV1Out, Entity, ExtractV1Out

__all__ = [
    "AskRequestBody",
    "AnswerContract",
    "ClassifyV1Out",
    "Entity",
    "ExtractV1Out",
    "IngestResponse",
    "RunRequest",
    "SearchHit",
    "SourceCitation",
    "UploadStubResponse",
]
