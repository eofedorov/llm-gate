import json
import os
from datetime import datetime, timezone
from typing import Any

import httpx

from .db import get_cursor


NORM_TABLE = "llm.normalized_issues"
ENRICH_TABLE = "llm.enriched_issues"
GATEWAY_URL_ENV = "GATEWAY_URL"


def _gateway_url() -> str:
    base = os.getenv(GATEWAY_URL_ENV, "http://localhost:8000")
    return base.rstrip("/")


def _call_run(prompt_name: str, task: str, input_payload: dict[str, Any]) -> dict[str, Any]:
    url = _gateway_url() + f"/run/{prompt_name}"
    body = {"task": task, "input": input_payload}
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(url, json=body)
        resp.raise_for_status()
        return resp.json()


def llm_enrich() -> None:
    """
    Обогатить normalized_issues через LLM и записать в enriched_issues.

    Для каждой записи без обогащения вызываем:
    - POST /run/classify_v1
    - POST /run/extract_v1
    и делаем UPSERT в enriched_issues.
    """
    select_sql = f"""
        SELECT n.id, n.title, n.description, n.created_at, n.author
        FROM {NORM_TABLE} n
        LEFT JOIN {ENRICH_TABLE} e ON e.id = n.id
        WHERE e.id IS NULL
    """

    with get_cursor() as cur:
        cur.execute(select_sql)
        rows = cur.fetchall()
        if not rows:
            return

        for issue_id, title, description, created_at, author in rows:
            input_payload = {
                "id": issue_id,
                "title": title,
                "description": description,
                "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else created_at,
                "author": author,
            }

            classify = _call_run("classify_v1", "Classify engineering issue", input_payload)
            extract = _call_run("extract_v1", "Extract entities and summary", input_payload)

            entities = extract.get("entities") or []
            summary = extract.get("summary") or ""

            label = classify.get("label")
            confidence = float(classify.get("confidence", 0.0))

            requires_backend = False
            requires_frontend = False
            ent_text = json.dumps(entities, ensure_ascii=False)

            cur.execute(
                f"""
                INSERT INTO {ENRICH_TABLE} (
                    id,
                    label,
                    priority,
                    requires_backend,
                    requires_frontend,
                    entities,
                    summary,
                    confidence,
                    processed_at
                )
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s)
                ON CONFLICT (id)
                DO UPDATE SET
                    label = EXCLUDED.label,
                    priority = EXCLUDED.priority,
                    requires_backend = EXCLUDED.requires_backend,
                    requires_frontend = EXCLUDED.requires_frontend,
                    entities = EXCLUDED.entities,
                    summary = EXCLUDED.summary,
                    confidence = EXCLUDED.confidence,
                    processed_at = EXCLUDED.processed_at
                """,
                (
                    issue_id,
                    label,
                    None,
                    requires_backend,
                    requires_frontend,
                    ent_text,
                    summary,
                    confidence,
                    datetime.now(timezone.utc),
                ),
            )

