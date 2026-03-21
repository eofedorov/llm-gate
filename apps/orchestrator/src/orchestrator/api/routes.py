"""Старые эндпоинты API."""
import logging

from fastapi import APIRouter

from orchestrator.prompts.registry import list_prompts as registry_list_prompts

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/prompts")
def list_prompts():
    """Список доступных промптов и версий из registry."""
    return {"prompts": registry_list_prompts()}
