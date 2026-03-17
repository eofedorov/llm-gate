from .db import get_cursor


NORM_TABLE = "llm.normalized_issues"
ENRICH_TABLE = "llm.enriched_issues"


def _single_value(cur, sql: str) -> int:
    cur.execute(sql)
    row = cur.fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def quality_checks() -> None:
    """
    Проверки качества пайплайна:
    - количество строк normalized == enriched
    - label NOT NULL во всех enriched_issues
    - отсутствие дубликатов по id
    """
    with get_cursor() as cur:
        count_norm = _single_value(cur, f"SELECT COUNT(*) FROM {NORM_TABLE}")
        count_enriched = _single_value(cur, f"SELECT COUNT(*) FROM {ENRICH_TABLE}")

        if count_norm != count_enriched:
            raise RuntimeError(f"Row count mismatch: normalized={count_norm}, enriched={count_enriched}")

        null_labels = _single_value(cur, f"SELECT COUNT(*) FROM {ENRICH_TABLE} WHERE label IS NULL")
        if null_labels > 0:
            raise RuntimeError(f"Null labels in enriched_issues: {null_labels}")

        dup_ids = _single_value(
            cur,
            f"""
            SELECT COUNT(*) FROM (
                SELECT id, COUNT(*) AS c
                FROM {ENRICH_TABLE}
                GROUP BY id
                HAVING COUNT(*) > 1
            ) t
            """,
        )
        if dup_ids > 0:
            raise RuntimeError(f"Duplicate ids in enriched_issues: {dup_ids}")

