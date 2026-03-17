import html
import re

from .db import get_cursor


RAW_TABLE = "llm.raw_issues"
NORM_TABLE = "llm.normalized_issues"


def _strip_html(text: str) -> str:
    text = html.unescape(text or "")
    return re.sub(r"<[^>]+>", "", text)


def _norm(text: str) -> str:
    return (text or "").strip()


def _norm_title(text: str) -> str:
    return _norm(text).lower()


def normalize() -> None:
    """
    Нормализовать задачи из raw_issues в normalized_issues.

    Берём записи, для которых ещё нет строки в normalized_issues, парсим payload_json
    и выполняем UPSERT по id.
    """
    select_sql = f"""
        SELECT
            (r.payload_json->>'id')::int AS issue_id,
            r.payload_json
        FROM {RAW_TABLE} r
        LEFT JOIN {NORM_TABLE} n ON (n.id = (r.payload_json->>'id')::int)
        WHERE n.id IS NULL
    """

    with get_cursor() as cur:
        cur.execute(select_sql)
        rows = cur.fetchall()
        if not rows:
            return

        for issue_id, payload in rows:
            assert isinstance(payload, dict)
            title = _norm_title(str(payload.get("title", "")))
            description_raw = str(payload.get("description", ""))
            description = _strip_html(description_raw)
            created_at = payload.get("created_at")
            author = _norm(str(payload.get("author", "")))

            cur.execute(
                f"""
                INSERT INTO {NORM_TABLE} (id, title, description, created_at, author)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (id)
                DO UPDATE SET
                    title = EXCLUDED.title,
                    description = EXCLUDED.description,
                    created_at = EXCLUDED.created_at,
                    author = EXCLUDED.author
                """,
                (issue_id, title, description, created_at, author),
            )

