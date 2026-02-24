"""SQLite: инициализация, WAL mode, таблица events."""
import json
import sqlite3
from pathlib import Path

from audit_service.settings import Settings

EVENTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    trace_id TEXT NOT NULL,
    service TEXT NOT NULL,
    env TEXT NOT NULL DEFAULT 'dev',
    event_type TEXT NOT NULL,
    span_id TEXT NOT NULL,
    parent_span_id TEXT,
    severity TEXT NOT NULL DEFAULT 'info',
    attrs_json TEXT NOT NULL DEFAULT '{}',
    duration_ms INTEGER,
    status TEXT,
    tool_name TEXT
);

CREATE INDEX IF NOT EXISTS ix_events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS ix_events_trace_id_ts ON events(trace_id, ts);
CREATE INDEX IF NOT EXISTS ix_events_event_type_ts ON events(event_type, ts);
CREATE INDEX IF NOT EXISTS ix_events_service_ts ON events(service, ts);
"""


def get_connection(db_path: str) -> sqlite3.Connection:
    """Возвращает соединение с включённым WAL и row_factory для dict."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(settings: Settings) -> None:
    """Создаёт файл БД и таблицы, включает WAL."""
    path = Path(settings.audit_db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection(settings.audit_db_path)
    try:
        conn.executescript(EVENTS_SCHEMA)
        conn.commit()
    finally:
        conn.close()
