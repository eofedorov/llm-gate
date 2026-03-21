"""SQL-запросы: документы, чанки, аудит runs/tool_calls/retrievals, sql_allowlist, readonly SELECT."""
from typing import Any
from uuid import UUID

from psycopg import Connection
from psycopg.rows import dict_row

_DEFAULT_ROW_LIMIT = 200


def insert_document(
    conn: Connection,
    *,
    doc_key: str,
    title: str,
    doc_type: str = "general",
    language: str = "ru",
    version: str = "v1",
    sha256: str | None = None,
) -> UUID:
    """Вставить документ в llm.kb_documents. Возвращает doc_id."""
    row = conn.execute(
        """
        INSERT INTO llm.kb_documents (doc_key, title, doc_type, language, version, sha256)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING doc_id
        """,
        (doc_key, title, doc_type, language, version, sha256),
    ).fetchone()
    return row[0]


def get_document_by_sha256(conn: Connection, sha256: str) -> dict[str, Any] | None:
    """Найти документ по sha256. Возвращает строку как dict или None."""
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute(
            """
            SELECT doc_id, doc_key, title, doc_type, language, version, sha256, created_at, updated_at, is_active
            FROM llm.kb_documents
            WHERE sha256 = %s AND is_active = TRUE
            LIMIT 1
            """,
            (sha256,),
        ).fetchone()
    return row


def get_document_by_doc_key(conn: Connection, doc_key: str) -> tuple[UUID, str | None] | None:
    """Найти документ по doc_key. Возвращает (doc_id, sha256) или None."""
    with conn.cursor() as cur:
        row = cur.execute(
            "SELECT doc_id, sha256 FROM llm.kb_documents WHERE doc_key = %s AND is_active = TRUE",
            (doc_key,),
        ).fetchone()
    if row is None:
        return None
    return (row[0], row[1])


def update_document_sha256(conn: Connection, doc_id: UUID, sha256: str | None) -> None:
    """Обновить sha256 и updated_at документа."""
    conn.execute(
        "UPDATE llm.kb_documents SET sha256 = %s, updated_at = now() WHERE doc_id = %s",
        (sha256, doc_id),
    )


def delete_chunks_by_doc_id(conn: Connection, doc_id: UUID) -> None:
    """Удалить все чанки документа (перед переиндексацией)."""
    conn.execute("DELETE FROM llm.kb_chunks WHERE doc_id = %s", (doc_id,))


def insert_chunk(
    conn: Connection,
    *,
    doc_id: UUID,
    chunk_index: int,
    section: str | None = None,
    text: str = "",
    text_tokens_est: int = 0,
    embedding_ref: str | None = None,
) -> UUID:
    """Вставить чанк в llm.kb_chunks. Возвращает chunk_id."""
    row = conn.execute(
        """
        INSERT INTO llm.kb_chunks (doc_id, chunk_index, section, text, text_tokens_est, embedding_ref)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING chunk_id
        """,
        (doc_id, chunk_index, section, text, text_tokens_est, embedding_ref),
    ).fetchone()
    return row[0]


def get_chunk_by_id(conn: Connection, chunk_id: UUID) -> dict[str, Any] | None:
    """Получить чанк по chunk_id. Возвращает строку как dict или None."""
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute(
            """
            SELECT c.chunk_id, c.doc_id, c.chunk_index, c.section, c.text, c.text_tokens_est, c.embedding_ref, c.created_at,
                   d.doc_key, d.title, d.doc_type, d.language
            FROM llm.kb_chunks c
            JOIN llm.kb_documents d ON d.doc_id = c.doc_id
            WHERE c.chunk_id = %s
            """,
            (chunk_id,),
        ).fetchone()
    return row


def log_run(
    conn: Connection,
    *,
    run_type: str,
    request_id: str | None = None,
    user_query: str | None = None,
    status: str = "started",
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    tokens_in: int = 0,
    tokens_out: int = 0,
    cost_usd: float = 0.0,
    error_code: str | None = None,
    error_message: str | None = None,
    meta: dict[str, Any] | None = None,
) -> UUID:
    """Вставить запись в llm.runs. Возвращает run_id."""
    import json
    meta_json = json.dumps(meta or {})
    row = conn.execute(
        """
        INSERT INTO llm.runs (run_type, request_id, user_query, status, model, temperature, max_tokens,
            tokens_in, tokens_out, cost_usd, error_code, error_message, meta)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
        RETURNING run_id
        """,
        (run_type, request_id, user_query, status, model, temperature, max_tokens,
         tokens_in, tokens_out, cost_usd, error_code, error_message, meta_json),
    ).fetchone()
    return row[0]


def update_run_finished(
    conn: Connection,
    run_id: UUID,
    *,
    status: str,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    cost_usd: float | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    """Обновить run при завершении: status, finished_at, опционально tokens/cost/error."""
    conn.execute(
        """
        UPDATE llm.runs
        SET finished_at = now(), status = %s,
            tokens_in = COALESCE(%s, tokens_in), tokens_out = COALESCE(%s, tokens_out),
            cost_usd = COALESCE(%s, cost_usd), error_code = %s, error_message = %s
        WHERE run_id = %s
        """,
        (status, tokens_in, tokens_out, cost_usd, error_code, error_message, run_id),
    )


def log_tool_call(
    conn: Connection,
    *,
    run_id: UUID,
    tool_name: str,
    args: dict[str, Any],
    result_meta: dict[str, Any],
    status: str = "ok",
    error_message: str | None = None,
    duration_ms: int | None = None,
) -> None:
    """Вставить запись в llm.tool_calls."""
    import json
    conn.execute(
        """
        INSERT INTO llm.tool_calls (run_id, tool_name, args, result_meta, status, error_message, duration_ms)
        VALUES (%s, %s, %s::jsonb, %s::jsonb, %s, %s, %s)
        """,
        (run_id, tool_name, json.dumps(args), json.dumps(result_meta), status, error_message, duration_ms),
    )


def log_retrieval(
    conn: Connection,
    *,
    run_id: UUID,
    chunk_id: UUID,
    rank: int,
    score: float | None = None,
    used_in_context: bool = True,
) -> None:
    """Вставить запись в llm.run_retrievals."""
    conn.execute(
        """
        INSERT INTO llm.run_retrievals (run_id, chunk_id, rank, score, used_in_context)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (run_id, chunk_id) DO UPDATE SET rank = EXCLUDED.rank, score = EXCLUDED.score
        """,
        (run_id, chunk_id, rank, score, used_in_context),
    )


def get_sql_allowlist(conn: Connection) -> list[tuple[str, str]]:
    """Список разрешённых таблиц для sql_read: (schema_name, table_name), только is_enabled=TRUE."""
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            """
            SELECT schema_name, table_name
            FROM llm.sql_allowlist
            WHERE is_enabled = TRUE
            ORDER BY schema_name, table_name
            """,
        ).fetchall()
    return [(r["schema_name"], r["table_name"]) for r in rows]


def execute_readonly_sql(
    conn: Connection,
    query: str,
    limit: int = _DEFAULT_ROW_LIMIT,
) -> tuple[list[str], list[list[Any]], int]:
    """
    Выполнить только SELECT; результат ограничен limit строками.
    Возвращает (columns, rows, row_count).
    """
    with conn.cursor() as cur:
        cur.execute(query)
        columns = [d.name for d in cur.description] if cur.description else []
        rows = cur.fetchmany(limit)
        row_count = len(rows)
    return columns, [list(r) for r in rows], row_count
