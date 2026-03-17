import json
from pathlib import Path
from typing import Any

from .db import get_cursor


DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "sample_issues.json"
RAW_TABLE = "llm.raw_issues"
SOURCE_NAME = "sample_issues"


def _load_issues() -> list[dict[str, Any]]:
    with DATA_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def extract() -> None:
    """Загрузить sample_issues.json в llm.raw_issues с идемпотентным UPSERT."""
    issues = _load_issues()
    if not issues:
        return

    with get_cursor() as cur:
        for item in issues:
            payload = json.dumps(item, ensure_ascii=False)
            created_at = item.get("created_at")
            cur.execute(
                f"""
                INSERT INTO {RAW_TABLE} (source, created_at, payload_json)
                VALUES (%s, %s, %s::jsonb)
                ON CONFLICT (source, (payload_json->>'id'))
                DO UPDATE SET
                    created_at = EXCLUDED.created_at,
                    payload_json = EXCLUDED.payload_json
                """,
                (SOURCE_NAME, created_at, payload),
            )

